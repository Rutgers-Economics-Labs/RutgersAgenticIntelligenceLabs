from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.runners import session_lifecycle
from app.runners.claude_code import ClaudeCodeRunner
from app.services import session_files
from app.services import running_agent_service
from app.services import project_artifacts_service
from app.services.role_runtime_service import load_role_runtime_config
from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Codex Test")
    _git(root, "config", "user.email", "codex@example.com")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")


def test_workspace_review_flow_runs_setup_and_verification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Workspace Project")
    setup_script = tmp_path / "scripts" / "setup-workspace.sh"
    setup_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'workspace ready\\n' > \"$RAIL_WORKSPACE_ROOT/setup-ran.txt\"\n",
        encoding="utf-8",
    )
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "test -f \"$RAIL_WORKSPACE_ROOT/setup-ran.txt\"\n"
        "echo 'verification ok'\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    async def _ensure_workspace_rail_cli(project_root: Path, workspace_root: Path):
        return {"status": "passed", "returncode": 0, "stdout": "rail ok", "stderr": ""}

    monkeypatch.setattr(session_lifecycle, "_ensure_workspace_rail_cli", _ensure_workspace_rail_cli)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-1")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-1",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    setup_result = asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-1",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    assert setup_result["status"] == "passed"
    assert (workspace_root / "setup-ran.txt").exists()

    readme = workspace_root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nworkspace change\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )
    async def _passing_auditors(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }
    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _passing_auditors)

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-1",
            session={"role": "coding"},
            project={"_id": "proj-workspace", "slug": "workspace-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    diff_text = (session_root / "diff.md").read_text(encoding="utf-8")
    verification_text = (session_root / "verification.md").read_text(encoding="utf-8")
    audit_payload = json.loads((tmp_path / "research_plan" / "audits" / "sess-1.json").read_text(encoding="utf-8"))
    audit_text = (tmp_path / "research_plan" / "audits" / "sess-1.md").read_text(encoding="utf-8")

    assert state["verification_status"] == "passed"
    assert state["review_status"] == "review"
    assert "README.md" in diff_text
    assert "status: `passed`" in verification_text
    assert audit_payload["session"]["id"] == "sess-1"
    assert audit_payload["session"]["verificationStatus"] == "passed"
    assert audit_payload["planner"]["taskCounts"] == {}
    assert audit_payload["integrity"]["action"] == "artifact_generation"
    assert "# Post-Run Audit" in audit_text


def test_materialize_workspace_prefers_local_branch_over_origin_when_local_exists(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Workspace Local Branch Project")
    tracked = tmp_path / "topics" / "data" / "processed" / "longitudinal_panel.csv"
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("a,b\n1,2\n", encoding="utf-8")
    _init_repo(tmp_path)

    _git(tmp_path, "branch", "-M", "main")
    _git(tmp_path, "clone", "--bare", str(tmp_path), str(tmp_path.parent / "remote.git"))
    _git(tmp_path, "remote", "add", "origin", str(tmp_path.parent / "remote.git"))
    _git(tmp_path, "push", "-u", "origin", "main")

    # Add a local-only file after the remote is already initialized.
    tracked.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    _git(tmp_path, "add", "topics/data/processed/longitudinal_panel.csv")
    _git(tmp_path, "commit", "-m", "local only panel update")

    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "health",
        "sess-local-pref",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    assert (workspace_root / "topics" / "data" / "processed" / "longitudinal_panel.csv").exists()
    assert "3,4" in (workspace_root / "topics" / "data" / "processed" / "longitudinal_panel.csv").read_text(encoding="utf-8")


def test_materialize_workspace_overlays_untracked_local_files_into_workspace(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Workspace Overlay Project")
    _init_repo(tmp_path)

    panel = tmp_path / "topics" / "data" / "processed" / "longitudinal_panel.csv"
    panel.parent.mkdir(parents=True, exist_ok=True)
    panel.write_text("a,b\n1,2\n", encoding="utf-8")

    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "health",
        "sess-untracked-overlay",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    workspace_panel = workspace_root / "topics" / "data" / "processed" / "longitudinal_panel.csv"
    assert workspace_panel.exists()
    assert workspace_panel.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_finalize_workspace_review_anchors_verification_status_when_session_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Regression guard for the workspace_verification "pending forever" bug.

    When a session terminates `failed` or `cancelled`, _run_workspace_verification
    is skipped (correctly — there's nothing to verify). But before this fix,
    `verification_status` was never transitioned from its bootstrap value of
    None, so _normalize_completion_summary downgraded it to "pending" and the
    integrity/closeout auditors blocked promotion forever on a verification
    run that would never happen.

    With the fix, _finalize_workspace_review explicitly anchors
    `verification_status` to "failed" in that path so the audit certificate
    carries a terminal status the auditors can act on.
    """
    bootstrap_future_project(tmp_path, name="Failed Session Verification Anchor")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-fail")
    workspace_root, workspace_branch, _ = session_lifecycle._prepare_workspace(
        tmp_path, "data", "sess-fail",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    session_files.update_state(
        session_root,
        status="failed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    # Before the fix, verification_status starts as None and stays None.
    pre = session_files.read_state(session_root)
    assert pre.get("verification_status") is None

    async def _mock_write_post_run_audit(**kwargs):
        return {"auditors": {}}

    monkeypatch.setattr(session_lifecycle, "write_post_run_audit", _mock_write_post_run_audit)

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-fail",
            session={"role": "data"},
            project={"slug": "failed-session-verification-anchor", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    assert state["verification_status"] == "failed", (
        "failed sessions must anchor verification_status to a terminal value, "
        "not leave it None for _normalize_completion_summary to downgrade to 'pending'"
    )


def test_finalize_workspace_review_writes_post_run_audit_without_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="No Workspace Audit Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-no-workspace")
    session_files.update_state(
        session_root,
        status="completed",
        review_status="review",
        completion_summary={
            "status": "completed",
            "artifacts_created": ["research_plan/current_plan.md"],
        },
    )

    async def _mock_write_post_run_audit(**kwargs):
        audit_path = tmp_path / "research_plan" / "audits" / f"{kwargs['session_id']}.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps({"session": {"id": kwargs["session_id"]}}), encoding="utf-8")
        return {"auditors": {}}

    monkeypatch.setattr(session_lifecycle, "write_post_run_audit", _mock_write_post_run_audit)

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-no-workspace",
            session={"role": "planner", "taskId": "task-1"},
            project={"slug": "no-workspace-audit", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    audit_path = tmp_path / "research_plan" / "audits" / "sess-no-workspace.json"
    assert audit_path.is_file()


def test_finalize_workspace_review_writes_blocker_audit_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Audit Snapshot Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-audit")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-audit",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    artifact_path = workspace_root / "artifacts" / "draft.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Draft\n\nNo structured sections.\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _fake_publish_completed_session_outputs(**kwargs):
        session_files.update_state(
            session_root,
            publish_status="published",
            publish_strategy="test",
            publish_commit_sha="abc123",
        )

    async def _fake_task_record(project: dict[str, Any], task_id: str):
        return {
            "_id": task_id,
            "title": "Write research artifact",
            "agentRole": "research",
            "repoPaths": ["artifacts/draft.md"],
        }

    async def _fake_update_task(*args, **kwargs):
        return None

    async def _fake_run_workspace_verification(**kwargs):
        session_files.update_state(
            session_root,
            verification_status="passed",
            verification_runs=[{"run_id": "verify-1", "status": "passed"}],
        )
        return {"status": "passed"}

    monkeypatch.setattr(session_lifecycle, "_publish_completed_session_outputs", _fake_publish_completed_session_outputs)
    monkeypatch.setattr(session_lifecycle, "_task_record", _fake_task_record)
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _fake_update_task)
    monkeypatch.setattr(session_lifecycle, "_run_workspace_verification", _fake_run_workspace_verification)

    project = {"_id": "proj-1", "slug": "audit-snapshot-project", "defaultBranch": "main", "localRepoPath": str(tmp_path)}
    board = asyncio.run(session_lifecycle.planner_service.ensure_main_board(project))
    asyncio.run(
        session_lifecycle.planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title="Follow-up blocked task",
            description="Needs contract repair",
            agent_role="research",
            status="blocked",
        )
    )
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-audit",
            session={"role": "research", "taskId": "task-1"},
            project=project,
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    audit_payload = json.loads((tmp_path / "research_plan" / "audits" / "sess-audit.json").read_text(encoding="utf-8"))
    assert audit_payload["session"]["publishStatus"] == "published"
    assert audit_payload["session"]["reviewStatus"] == "needs_changes"
    assert "Role workflow contract failed" in audit_payload["currentBlocker"]
    assert audit_payload["planner"]["taskCounts"]["blocked"] >= 1


def test_workspace_setup_ensures_rail_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Workspace CLI Project")
    setup_script = tmp_path / "scripts" / "setup-workspace.sh"
    setup_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'workspace ready'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-cli")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-cli",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    async def _ensure_workspace_rail_cli(project_root: Path, workspace_root: Path):
        return {"status": "passed", "returncode": 0, "stdout": "rail ok", "stderr": ""}

    monkeypatch.setattr(session_lifecycle, "_ensure_workspace_rail_cli", _ensure_workspace_rail_cli)

    setup_result = asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-cli",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )

    state = session_files.read_state(session_root)
    assert setup_result["status"] == "passed"
    assert state["setup_status"] == "passed"
    assert "RAIL CLI installed." in state["setup_stdout_tail"]


def test_overlay_active_hydration_artifacts_into_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Hydrated Workspace Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-hydrated")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-hydrated",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    artifact_root = tmp_path / "tmp-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    onto_db = artifact_root / "onto.db"
    onto_duckdb = artifact_root / "onto.duckdb"
    onto_db.write_bytes(b"onto-db-bytes\n")
    onto_duckdb.write_bytes(b"onto-duckdb-bytes\n")

    async def _fake_hydration_status(*, project: dict, pipeline_slug: str | None = None, hydration_mode: str = "full"):
        return {
            "state": "hydrated_on_this_device",
            "pipelineSlug": "soccer-pipeline",
            "hydrationMode": "full",
            "reusableArtifact": {
                "_id": "artifact-1",
                "commitSha": "abc123",
                "manifestFingerprint": "fp-1",
                "ontologyArtifactPath": str(onto_db),
                "duckdbArtifactPath": str(onto_duckdb),
            },
        }

    stale_root = tmp_path / "stale-project-artifacts"
    stale_root.mkdir(parents=True, exist_ok=True)
    stale_db = stale_root / "onto.db"
    stale_duckdb = stale_root / "onto.duckdb"
    stale_db.write_bytes(b"stale-onto-db\n")
    stale_duckdb.write_bytes(b"stale-onto-duckdb\n")

    async def _fake_resolve(project_id: str):
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_id,
            db_path=str(stale_db),
            owl_path=None,
            duckdb_path=str(stale_duckdb),
            embeddings_path=str(artifact_root / "embeddings.db"),
        )

    monkeypatch.setattr(session_lifecycle.hydration_registry_service, "get_hydration_status", _fake_hydration_status)
    monkeypatch.setattr(session_lifecycle.project_artifacts_service, "resolve", _fake_resolve)

    result = asyncio.run(
        session_lifecycle._overlay_active_hydration_artifacts_into_workspace(
            project={"_id": "project-1", "slug": "hydrated-workspace"},
            workspace_root=workspace_root,
            session_root=session_root,
        )
    )

    state = session_files.read_state(session_root)
    workspace_onto_db = workspace_root / ".ontology" / "onto.db"
    workspace_duckdb = workspace_root / ".ontology" / "onto.duckdb"
    metadata_path = workspace_root / ".ontology" / ".rail_hydration.json"

    assert result["status"] == "mirrored"
    assert workspace_onto_db.read_bytes() == onto_db.read_bytes()
    assert workspace_duckdb.read_bytes() == onto_duckdb.read_bytes()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["pipelineSlug"] == "soccer-pipeline"
    assert metadata["commitSha"] == "abc123"
    assert metadata["mirroredFrom"]["duckdbArtifactPath"] == str(onto_duckdb)
    assert state["workspace_hydration_status"] == "mirrored"
    assert state["workspace_hydration_pipeline"] == "soccer-pipeline"


def test_registering_workspace_hydration_artifact_promotes_active_project_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Hydration Promotion Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-promote")
    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    (ontology_root / ".rail_hydration.json").write_text(
        json.dumps({"pipeline_slug": "soccer-pipeline", "hydration_mode": "full"}),
        encoding="utf-8",
    )
    (ontology_root / "onto.db").write_bytes(b"db")
    (ontology_root / "onto.duckdb").write_bytes(b"duck")
    (ontology_root / "populated_ontology.owl").write_text("owl", encoding="utf-8")

    register_calls: list[dict[str, object]] = []
    promote_calls: list[dict[str, object]] = []

    async def _fake_register_hydration_artifact(**kwargs):
        register_calls.append(kwargs)
        return "artifact-123"

    async def _fake_promote_project_hydration_artifact(**kwargs):
        promote_calls.append(kwargs)
        return None

    monkeypatch.setattr(
        "app.services.hydration_registry_service.register_hydration_artifact",
        _fake_register_hydration_artifact,
    )
    monkeypatch.setattr(
        "app.services.hydration_registry_service.promote_project_hydration_artifact",
        _fake_promote_project_hydration_artifact,
    )

    asyncio.run(
        session_lifecycle._maybe_register_workspace_hydration_artifact(
            project={
                "_id": "project-1",
                "slug": "hydration-promotion-project",
                "localRepoPath": str(tmp_path),
                "manifestPath": "rail.yaml",
            },
            project_root=tmp_path,
            session_root=session_root,
            changed_files=[".ontology/onto.duckdb", ".ontology/.rail_hydration.json"],
            role="data",
        )
    )

    assert len(register_calls) == 1
    assert register_calls[0]["pipeline_slug"] == "soccer-pipeline"
    assert len(promote_calls) == 1
    assert promote_calls[0]["project"]["_id"] == "project-1"
    assert promote_calls[0]["ontology_artifact_path"] == str(ontology_root / "onto.db")
    assert promote_calls[0]["duckdb_artifact_path"] == str(ontology_root / "onto.duckdb")

    events = session_files.list_events(session_root)
    assert any(
        "promoted it as the active project ontology" in (event.get("content") or "")
        for event in events
    )


def test_materialize_workspace_prefers_remote_default_branch_when_available(tmp_path: Path):
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))

    local = tmp_path / "local"
    local.mkdir()
    bootstrap_future_project(local, name="Remote Workspace Project")
    _init_repo(local)
    _git(local, "remote", "add", "origin", str(origin))
    _git(local, "push", "-u", "origin", "main")

    remote_clone = tmp_path / "remote-clone"
    _git(tmp_path, "clone", str(origin), str(remote_clone))
    _git(remote_clone, "config", "user.name", "Codex Test")
    _git(remote_clone, "config", "user.email", "codex@example.com")
    report = remote_clone / "artifacts" / "ontology_backed_baseline_findings.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Hydrated baseline\n", encoding="utf-8")
    _git(remote_clone, "add", "artifacts/ontology_backed_baseline_findings.md")
    _git(remote_clone, "commit", "-m", "remote baseline report")
    _git(remote_clone, "push", "origin", "main")

    session_root = session_files.ensure_session_root(local, "planner", "sess-remote")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        local,
        "planner",
        "sess-remote",
    )
    result = asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=local,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    assert result["status"] == "ready"
    assert result["base_ref"] == "origin/main"
    assert (workspace_root / "artifacts" / "ontology_backed_baseline_findings.md").exists()


def test_materialize_workspace_reconciles_duplicate_planner_task_files(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Workspace Planner Cleanup")
    _init_repo(tmp_path)

    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    legacy = task_dir / "source-inventory-short.md"
    canonical = task_dir / "source-inventory-canonical.md"
    legacy.write_text(
        """---
title: Source inventory
status: awaiting_approval
assigned_role: research
---

## Description

Legacy file.
""",
        encoding="utf-8",
    )
    canonical.write_text(
        """---
task_id: source-inventory-canonical
title: Source inventory
status: awaiting_approval
assigned_role: research
---

## Description

Canonical file.
""",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "research_plan/tasks/source-inventory-short.md", "research_plan/tasks/source-inventory-canonical.md")
    _git(tmp_path, "commit", "-m", "seed duplicate planner task files")

    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-cleanup",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    workspace_tasks = sorted((workspace_root / "research_plan" / "tasks").glob("*.md"))
    source_inventory_files = [path.name for path in workspace_tasks if "source-inventory" in path.name]

    assert "source-inventory-short.md" not in source_inventory_files
    assert len(source_inventory_files) == 1


def test_role_aliases_resolve_repo_configs(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Alias Project")

    config = load_role_runtime_config(
        {
            "_id": "project-1",
            "slug": "alias-project",
            "localRepoPath": str(tmp_path),
        },
        "researcher",
    )

    assert config.role == "research"
    assert config.config_path.name == "research.yaml"


def test_finalize_workspace_review_normalizes_completion_summary_and_mirrors_state(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Completion Project")
    setup_script = tmp_path / "scripts" / "setup-workspace.sh"
    setup_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n", encoding="utf-8")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-2")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-2",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-2",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )

    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "report.md").write_text(
        "# Report\n\n## Facts\nEmployment rose.\n\n## Interpretation\nThe recovery accelerated after 2021.\n\n## Open Questions\nConfirm whether 2024 data is final.\n",
        encoding="utf-8",
    )
    (workspace_root / "topics" / "analysis.csv").write_text("value\n1\n", encoding="utf-8")
    assumptions_path = workspace_root / "research_plan" / "state" / "assumptions.json"
    assumptions_path.write_text(
        json.dumps(
            [
                {
                    "assumption_key": "window-2020-2024",
                    "title": "Window",
                    "value": "Use 2020-2024",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    sources_path = workspace_root / "research_plan" / "state" / "sources.json"
    sources_path.write_text(
        json.dumps(
            [
                {
                    "source_key": "bls-laus",
                    "source_type": "dataset",
                    "title": "BLS LAUS",
                    "url_or_path": "https://www.bls.gov/lau/",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    claims_path = workspace_root / "research_plan" / "state" / "claims.json"
    claims_path.write_text(
        json.dumps(
            [
                {
                    "claim_key": "claim-001",
                    "claim_text": "Employment recovered after 2021.",
                    "artifact_path": "artifacts/report.md",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    session_files.append_event(
        session_root,
        "completed",
        status="completed",
        open_questions=["Confirm whether 2024 data is final."],
        recommended_next_tasks=["Review the draft report for publication readiness."],
    )
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-2",
            session={"role": "research", "taskId": "task-123"},
            project={"slug": "completion-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    summary_text = (session_root / "summary.md").read_text(encoding="utf-8")
    todos_text = (session_root / "todos.md").read_text(encoding="utf-8")
    assumptions = json.loads((tmp_path / "research_plan" / "state" / "assumptions.json").read_text(encoding="utf-8"))
    verification_runs = json.loads((tmp_path / "research_plan" / "state" / "verification_runs.json").read_text(encoding="utf-8"))
    lineage = json.loads((tmp_path / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))

    assert state["completion_summary"]["assumptions_added"] == ["window-2020-2024"]
    assert state["completion_summary"]["sources_used"] == ["bls-laus"]
    assert state["completion_summary"]["claims_created"] == ["claim-001"]
    assert "artifacts/report.md" in state["completion_summary"]["artifacts_created"]
    assert "topics/analysis.csv" in state["completion_summary"]["datasets_created"]
    assert state["review_status"] == "review"
    assert "## Completion Summary" in summary_text
    assert "Confirm whether 2024 data is final." in todos_text
    assert assumptions[0]["assumption_key"] == "window-2020-2024"
    assert verification_runs[0]["task_id"] == "task-123"
    assert any(item["artifact_path"] == "artifacts/report.md" for item in lineage)
    report_entry = next(item for item in lineage if item["artifact_path"] == "artifacts/report.md")
    assert report_entry["verification_commands"] == ["scripts/run-verification.sh"]
    dataset_entry = next(item for item in lineage if item["artifact_path"] == "topics/analysis.csv")
    assert dataset_entry["verification_commands"] == ["scripts/run-verification.sh"]
    assert dataset_entry["assumptions"] == ["research_plan/state/assumptions.json#window-2020-2024"]
    assert dataset_entry["sources"] == ["research_plan/state/sources.json#bls-laus"]
    assert verification_runs[0]["scope"] == "research"


def test_sync_completion_summary_to_integrity_indexes_links_datasets_to_changed_source_configs(
    tmp_path: Path,
):
    bootstrap_future_project(tmp_path, name="Source Sync Project")
    source_path = tmp_path / ".ontology" / "sources" / "sample-source.yaml"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "name: Sample Source\n"
        "type: csv\n"
        "path: .ontology/sources/sample.csv\n"
        "description: Sample source\n"
        "fields:\n"
        "  - source: value\n"
        "    alias: value\n",
        encoding="utf-8",
    )

    session_lifecycle._sync_completion_summary_to_integrity_indexes(
        project_root=tmp_path,
        workspace_root=tmp_path,
        summary={
            "artifacts_created": [],
            "datasets_created": ["topics/output.csv"],
            "sources_used": [],
            "assumptions_added": [],
            "claims_created": [],
            "verification_results": [],
        },
        session_id="sess-source-sync",
        task_id="task-source-sync",
        role="data",
        verification_command="scripts/run-verification.sh",
        changed_files=[".ontology/sources/sample-source.yaml", "topics/output.csv"],
    )

    sources = json.loads((tmp_path / "research_plan" / "state" / "sources.json").read_text(encoding="utf-8"))
    lineage = json.loads((tmp_path / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))

    assert any(item["source_key"] == "sample-source" for item in sources)
    dataset_entry = next(item for item in lineage if item["artifact_path"] == "topics/output.csv")
    assert dataset_entry["sources"] == ["research_plan/state/sources.json#sample-source"]
    assert dataset_entry["verification_commands"] == ["scripts/run-verification.sh"]


def test_create_runner_session_rejects_write_run_in_assisted_mode(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Approval Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "approval-project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )

    with pytest.raises(PermissionError, match="Assisted mode requires approval"):
        asyncio.run(
            session_lifecycle.create_runner_session(
                project_id="project-1",
                project_slug="approval-project",
                task_id="task-1",
                runner_name="codex_cli",
                role="research",
                task_description="Collect source notes",
                repo_url="https://github.com/example/repo",
                branch="main",
                local_repo_path=str(tmp_path),
                allowed_paths=["topics", "artifacts"],
                acceptance_criteria=[],
            )
        )


def test_create_runner_session_allows_write_run_after_policy_approval(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Approval Project")
    _init_repo(tmp_path)

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "approval-project",
            "localRepoPath": str(tmp_path),
        }

    async def _fake_create_running_agent(**kwargs):
        return "sess-approved"

    async def _fake_update_running_agent(*args, **kwargs):
        return None

    async def _passing_auditors(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(running_agent_service, "create_running_agent", _fake_create_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _fake_update_running_agent)
    monkeypatch.setattr(session_lifecycle, "_materialize_workspace", lambda **kwargs: asyncio.sleep(0, result={"mode": "directory"}))
    monkeypatch.setattr(session_lifecycle, "_run_workspace_setup", lambda **kwargs: asyncio.sleep(0, result={"status": "passed"}))
    monkeypatch.setattr(session_lifecycle, "_build_project_context", lambda *args, **kwargs: asyncio.sleep(0, result=""))
    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _passing_auditors)

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-1", "status": "running"}

    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="approval-project",
            task_id="task-1",
            runner_name="codex_cli",
            role="research",
            task_description="Collect source notes",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=["topics", "artifacts"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"


def test_local_claude_runner_end_to_end_writes_and_certifies_session_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Local Claude E2E Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "local-claude-e2e-project",
            "localRepoPath": str(tmp_path),
            "defaultBranch": "main",
        }

    store: dict[str, dict[str, Any]] = {}

    async def _create_running_agent(**kwargs):
        session_id = kwargs.get("session_id") or "sess-e2e"
        store[session_id] = {
            "_id": session_id,
            "projectId": kwargs.get("project_id"),
            "projectSlug": kwargs.get("project_slug"),
            "role": kwargs.get("role"),
            "runner": kwargs.get("runner_name") or kwargs.get("runtime_kind"),
            "status": kwargs.get("status", "queued"),
            "taskId": kwargs.get("task_id"),
            "title": kwargs.get("title"),
            "externalSessionId": None,
        }
        return session_id

    async def _update_running_agent(session_id: str, **fields):
        store[session_id].update(fields)
        return dict(store[session_id])

    async def _get_running_agent(session_id: str):
        return dict(store[session_id]) if session_id in store else None

    async def _finalize_running_agent(session_id: str, *, status: str, ended_at=None):
        if session_id in store:
            store[session_id]["status"] = status
            store[session_id]["endedAt"] = ended_at
        return None

    async def _list_project_running_agents(*args, **kwargs):
        return []

    async def _passing_auditors(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    async def _noop_update_task(task_id: str, *, project: dict, **fields):
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(running_agent_service, "create_running_agent", _create_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _update_running_agent)
    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(running_agent_service, "finalize_running_agent", _finalize_running_agent)
    monkeypatch.setattr(running_agent_service, "list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _passing_auditors)
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _noop_update_task)
    monkeypatch.setattr(
        session_lifecycle,
        "_run_workspace_setup",
        lambda **kwargs: asyncio.sleep(0, result={"status": "passed", "stdout": "", "stderr": ""}),
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_claude = fake_bin / "claude"
    fake_claude.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, re, sys\n"
        "prompt = ' '.join(sys.argv[1:])\n"
        "work_order_id = os.environ.get('RAIL_WORK_ORDER_ID')\n"
        "work_order_path = os.environ.get('RAIL_WORK_ORDER_PATH')\n"
        "task_type = 'analysis'\n"
        "if work_order_path and os.path.exists(work_order_path):\n"
        "    with open(work_order_path, 'r', encoding='utf-8') as handle:\n"
        "        task_type = json.load(handle).get('task_type', task_type)\n"
        "match = re.search(r'research_plan/sessions/[^\\s]+/session_result\\.json', prompt)\n"
        "if not match:\n"
        "    raise SystemExit('missing session_result path in prompt')\n"
        "relative = match.group(0)\n"
        "target = os.path.join(os.getcwd(), relative)\n"
        "os.makedirs(os.path.dirname(target), exist_ok=True)\n"
        "with open(target, 'w', encoding='utf-8') as handle:\n"
        "    json.dump({\n"
        "        'session_id': os.path.basename(os.path.dirname(target)),\n"
        "        'work_order_id': work_order_id,\n"
        "        'status': 'completed',\n"
        "        'summary': 'Verified ontology health and recorded the result.',\n"
        "        'task_type': task_type,\n"
        "        'runner_name': 'claude_code',\n"
        "        'files_changed': [relative, 'research_plan/state/claim_candidates.json'],\n"
        "        'blockers': [\n"
        "            {\n"
        "                'category': 'insufficient_data_declared',\n"
        "                'summary': 'No new claim candidates were needed for this verification-only smoke test.'\n"
        "            }\n"
        "        ]\n"
        "    }, handle)\n"
        "state_path = os.path.join(os.getcwd(), 'research_plan', 'state', 'claim_candidates.json')\n"
        "os.makedirs(os.path.dirname(state_path), exist_ok=True)\n"
        "with open(state_path, 'w', encoding='utf-8') as handle:\n"
        "    json.dump([{'claim_id': 'claim-e2e', 'status': 'candidate'}], handle)\n"
        "print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'completed local smoke test'}]}}))\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")
    monkeypatch.setattr(
        session_lifecycle,
        "resolve_runner_for_project",
        lambda *args, **kwargs: ClaudeCodeRunner(command=str(fake_claude)),
    )

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="local-claude-e2e-project",
            task_id="task-e2e",
            runner_name="claude_code",
            role="planner",
            task_description="Verify ontology health and write the session result.",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=["research_plan", "artifacts"],
            acceptance_criteria=["writes a session_result.json", "updates claim candidates"],
            policy_approval_granted=True,
        )
    )

    terminal = asyncio.run(
        session_lifecycle.poll_session_until_done(
            result["convex_session_id"],
            project_id="project-1",
            max_polls=30,
            poll_interval_seconds=1,
        )
    )

    state = session_files.read_state(Path(result["sessionPath"]))
    session_result_path = (
        Path(state["workspace_path"])
        / "research_plan"
        / "sessions"
        / "planner"
        / result["convex_session_id"]
        / "session_result.json"
    )

    assert terminal["status"] == "completed"
    assert state["status"] == "completed"
    assert state["session_result_certified"] is True
    assert state["review_status"] == "review"
    assert state["verification_status"] == "passed"
    assert session_result_path.exists()


def test_runner_launch_allows_existing_planner_task_even_when_task_graph_is_saturated():
    auditors = {
        "session": {"status": "ready", "blockers": []},
        "planner": {
            "status": "ready",
            "blockers": [],
            "taskSaturationCount": 24,
        },
        "ontology": {"status": "ready", "blockers": []},
        "integrity": {"status": "ready", "blockers": []},
    }

    assert (
        session_lifecycle._runner_launch_blocked_by_auditors(
            "planner",
            "Verify hydrated ontology health before research",
            "verify-hydrated-ontology-health-before-research",
            auditors,
        )
        is None
    )
    assert "Planner task graph saturated" in str(
        session_lifecycle._runner_launch_blocked_by_auditors(
            "planner",
            "Open-ended planning pass",
            None,
            auditors,
        )
    )


def test_create_runner_session_resolves_default_runner_from_project_policy(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Default Runner Project")
    _init_repo(tmp_path)

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "default-runner-project",
            "localRepoPath": str(tmp_path),
        }

    async def _fake_create_running_agent(**kwargs):
        return "sess-default-runner"

    async def _fake_update_running_agent(*args, **kwargs):
        return None

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(running_agent_service, "create_running_agent", _fake_create_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _fake_update_running_agent)
    monkeypatch.setattr(session_lifecycle, "_materialize_workspace", lambda **kwargs: asyncio.sleep(0, result={"mode": "directory"}))
    monkeypatch.setattr(session_lifecycle, "_run_workspace_setup", lambda **kwargs: asyncio.sleep(0, result={"status": "passed"}))
    monkeypatch.setattr(session_lifecycle, "_build_project_context", lambda *args, **kwargs: asyncio.sleep(0, result=""))

    seen_runner_names: list[str] = []

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    def _resolve_runner(name: str, *args, **kwargs):
        seen_runner_names.append(name)
        return _FakeRunner()

    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", _resolve_runner)

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="default-runner-project",
            task_id="task-1",
            runner_name="default",
            role="planner",
            task_description="Reopen research from hydrated ontology",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=["research_plan", "topics", "artifacts"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"
    assert seen_runner_names == ["codex_cli"]


def test_normalize_runner_name_for_project_rejects_unknown_runner():
    with pytest.raises(ValueError, match="Unsupported runner name: writerbot"):
        session_lifecycle._normalize_runner_name_for_project("writerbot")


def test_create_runner_session_rejects_parallel_launch_when_nonconcurrent(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Sequential Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "sequential-project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(
            0,
            result=[
                {
                    "_id": "sess-planner-1",
                    "role": "planner",
                    "status": "running",
                }
            ],
        ),
    )

    with pytest.raises(RuntimeError, match="Sequential execution enforced: planner session sess-planner-1 is still active"):
        asyncio.run(
            session_lifecycle.create_runner_session(
                project_id="project-1",
                project_slug="sequential-project",
                task_id="task-2",
                runner_name="codex_cli",
                role="planner",
                task_description="Produce synthesis",
                repo_url="https://github.com/example/repo",
                branch="main",
                local_repo_path=str(tmp_path),
                allowed_paths=["research_plan", "artifacts"],
                acceptance_criteria=[],
                policy_approval_granted=True,
            )
        )


def test_create_runner_session_repairs_stale_active_sessions_before_nonconcurrent_block(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Sequential Project")
    stale_root = session_files.ensure_session_root(tmp_path, "planner", "sess-planner-1")
    session_files.update_state(stale_root, status="completed")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "sequential-project",
            "localRepoPath": str(tmp_path),
        }

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    finalized: list[dict[str, Any]] = []
    list_calls = {"n": 0}

    async def _list_active_sessions(*args, **kwargs):
        list_calls["n"] += 1
        if list_calls["n"] == 1:
            return [
                {
                    "_id": "sess-planner-1",
                    "role": "planner",
                    "status": "running",
                }
            ]
        return []

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        _list_active_sessions,
    )
    monkeypatch.setattr(
        running_agent_service,
        "finalize_running_agent",
        lambda session_id, *, status, ended_at=None: asyncio.sleep(
            0,
            result=finalized.append({"session_id": session_id, "status": status}),
        ),
    )
    monkeypatch.setattr(
        running_agent_service,
        "create_running_agent",
        lambda **kwargs: asyncio.sleep(0, result="sess-new-1"),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_materialize_workspace",
        lambda **kwargs: asyncio.sleep(0, result={"mode": "linked-worktree"}),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_run_workspace_setup",
        lambda **kwargs: asyncio.sleep(0, result={"status": "passed", "stdout": "", "stderr": ""}),
    )
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())

    async def _passing_auditors(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _passing_auditors)

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="sequential-project",
            task_id="task-2",
            runner_name="codex_cli",
            role="planner",
            task_description="Produce synthesis",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=["research_plan", "artifacts"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"
    assert finalized == [{"session_id": "sess-planner-1", "status": "completed"}]


def test_create_runner_session_blocks_research_launch_when_ontology_auditor_is_blocked(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Ontology Gate Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "ontology-gate-project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    with pytest.raises(RuntimeError, match="Ontology hydration state is `not_hydrated`\\."):
        asyncio.run(
            session_lifecycle.create_runner_session(
                project_id="project-1",
                project_slug="ontology-gate-project",
                task_id="task-2",
                runner_name="codex_cli",
                role="research",
                task_description="Write narrative findings",
                repo_url="https://github.com/example/repo",
                branch="main",
                local_repo_path=str(tmp_path),
                allowed_paths=["research_plan", "artifacts"],
                acceptance_criteria=[],
                policy_approval_granted=True,
            )
        )


def test_create_runner_session_allows_repair_launch_when_ontology_auditor_is_blocked(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Ontology Gate Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "ontology-gate-project",
            "localRepoPath": str(tmp_path),
        }

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        running_agent_service,
        "create_running_agent",
        lambda **kwargs: asyncio.sleep(0, result="sess-new-1"),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_materialize_workspace",
        lambda **kwargs: asyncio.sleep(0, result={"mode": "linked-worktree"}),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_run_workspace_setup",
        lambda **kwargs: asyncio.sleep(0, result={"status": "passed", "stdout": "", "stderr": ""}),
    )
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="ontology-gate-project",
            task_id="task-2",
            runner_name="codex_cli",
            role="data",
            task_description="Repair pipeline and hydrate ontology",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=[".ontology", "research_plan"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"


def test_create_runner_session_allows_control_plane_repair_launch_when_planner_auditor_is_blocked(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Control Plane Gate Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "control-plane-gate-project",
            "localRepoPath": str(tmp_path),
        }

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        running_agent_service,
        "create_running_agent",
        lambda **kwargs: asyncio.sleep(0, result="sess-new-1"),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_materialize_workspace",
        lambda **kwargs: asyncio.sleep(0, result={"mode": "linked-worktree"}),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_run_workspace_setup",
        lambda **kwargs: asyncio.sleep(0, result={"status": "passed", "stdout": "", "stderr": ""}),
    )
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "blocked", "blockers": ["1 task/session state mismatch(es) detected."]},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "blocked", "blockers": ["Failed verification runs must be resolved before promotion."]},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="control-plane-gate-project",
            task_id="task-2",
            runner_name="codex_cli",
            role="health",
            task_description="Reconcile control-plane drift and stale sessions",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=["research_plan", ".ontology"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"


def test_create_runner_session_reconciles_planner_state_before_auditor_gate(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Launch Reconcile Project")
    task_root = tmp_path / "research_plan" / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    (task_root / "task-2.md").write_text(
        """---
task_id: task-2
title: Repair pipeline and hydrate ontology
status: ready
assigned_role: data
runner: codex_cli
approval_state: granted
related_files:
  - .ontology
latest_run_summary: Reopened by Autopilot because hydration state is `not_hydrated`.
---

## Description

Repair pipeline and hydrate ontology.
""",
        encoding="utf-8",
    )

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "launch-reconcile-project",
            "localRepoPath": str(tmp_path),
        }

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    reconcile_calls: list[str] = []
    captured_tasks: list[dict] = []

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(
        running_agent_service,
        "list_project_running_agents",
        lambda *args, **kwargs: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        running_agent_service,
        "create_running_agent",
        lambda **kwargs: asyncio.sleep(0, result="sess-new-1"),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_materialize_workspace",
        lambda **kwargs: asyncio.sleep(0, result={"mode": "linked-worktree"}),
    )
    monkeypatch.setattr(
        session_lifecycle,
        "_run_workspace_setup",
        lambda **kwargs: asyncio.sleep(0, result={"status": "passed", "stdout": "", "stderr": ""}),
    )
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())
    monkeypatch.setattr(
        session_lifecycle.planner_service,
        "reconcile_task_files",
        lambda project: reconcile_calls.append("files") or asyncio.sleep(0, result={"removed": []}),
    )
    monkeypatch.setattr(
        session_lifecycle.planner_service,
        "reconcile_task_session_states",
        lambda project: reconcile_calls.append("sessions") or asyncio.sleep(0, result={"updated": []}),
    )

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        captured_tasks.extend(tasks or [])
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    result = asyncio.run(
        session_lifecycle.create_runner_session(
            project_id="project-1",
            project_slug="launch-reconcile-project",
            task_id="task-2",
            runner_name="codex_cli",
            role="data",
            task_description="Repair pipeline and hydrate ontology",
            repo_url="https://github.com/example/repo",
            branch="main",
            local_repo_path=str(tmp_path),
            allowed_paths=[".ontology", "research_plan"],
            acceptance_criteria=[],
            policy_approval_granted=True,
        )
    )

    assert result["status"] == "running"
    assert reconcile_calls == ["files", "sessions"]
    assert captured_tasks and captured_tasks[0]["_id"] == "task-2"


def test_cancel_runner_session_uses_file_backed_state_when_runtime_row_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Cancel Project")
    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-cancel")
    session_files.update_state(
        session_root,
        role="planner",
        runner="codex_cli",
        status="running",
        external_session_id="external-cancel-1",
    )

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "cancel-project",
            "localRepoPath": str(tmp_path),
        }

    cancel_calls: list[str] = []

    class _FakeRunner:
        async def cancel(self, external_id: str):
            cancel_calls.append(external_id)

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(running_agent_service, "get_running_agent", lambda session_id: asyncio.sleep(0, result=None))
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())
    monkeypatch.setattr(running_agent_service, "finalize_running_agent", lambda *args, **kwargs: asyncio.sleep(0, result=None))

    result = asyncio.run(
        session_lifecycle.cancel_runner_session(
            "sess-cancel",
            project_id="project-1",
        )
    )

    state = session_files.read_state(session_root)
    assert result["status"] == "cancelled"
    assert cancel_calls == ["external-cancel-1"]
    assert state["status"] == "cancelled"


def test_finalize_workspace_review_records_connector_publish_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Publish Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-publish")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-publish",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-publish",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "memo.md").write_text("# Memo\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _publish(*args, **kwargs):
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "deadbeef",
            "branch": "main",
            "changed": True,
            "files": [{"path": "artifacts/memo.md", "changed": True}],
            "skipped_files": [],
        }

    publish_results: list[dict] = []

    async def _record_success(project_id: str, result: dict[str, object]) -> None:
        publish_results.append({"project_id": project_id, **result})

    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)
    monkeypatch.setattr(session_lifecycle, "record_publish_failure", lambda *args, **kwargs: asyncio.sleep(0))

    project = {
        "_id": "project-1",
        "slug": "publish-project",
        "defaultBranch": "main",
        "github": "Rutgers-Economics-Labs/RAIL-doge-government-payments-and-savings-ana",
    }
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-publish",
            session={"role": "research", "taskId": "task-123"},
            project=project,
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    summary = (session_root / "summary.md").read_text(encoding="utf-8")

    assert state["publish_status"] == "published"
    assert state["publish_commit_sha"] == "deadbeef"
    assert state["publish_changed_files"] == ["artifacts/memo.md"]
    assert "publish_commit_sha: `deadbeef`" in summary
    assert publish_results[0]["project_id"] == "project-1"


def test_finalize_workspace_review_verifies_published_repo_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Published Verification Project")
    _init_repo(tmp_path)

    rel_path = Path(".ontology/sources/registry.yaml")
    project_file = tmp_path / rel_path
    project_file.parent.mkdir(parents=True, exist_ok=True)
    project_file.write_text("name: registry\n", encoding="utf-8")

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-published-verify")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-published-verify",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    workspace_file = workspace_root / rel_path
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text(
        "name: registry\n"
        "type: csv\n"
        "path: .ontology/sources/registry.csv\n"
        "fields:\n"
        "  - source: slug\n"
        "    alias: slug\n",
        encoding="utf-8",
    )
    session_files.update_state(
        session_root,
        status="completed",
        role="data",
        task_id="task-verify-after-publish",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _list_changed_files(_workspace_root: Path) -> list[str]:
        return [rel_path.as_posix()]

    async def _publish_completed_session_outputs(**kwargs):
        shutil.copy2(workspace_file, project_file)
        session_files.update_state(
            kwargs["session_root"],
            publish_status="published",
            publish_strategy="github_app_commit",
            publish_commit_sha="abc123",
            publish_changed_files=[rel_path.as_posix()],
        )

    async def _run_workspace_verification(**kwargs):
        text = project_file.read_text(encoding="utf-8")
        passed = "type: csv" in text and "path:" in text and "fields:" in text
        session_files.update_state(
            kwargs["session_root"],
            verification_status="passed" if passed else "failed",
            verification_exit_code=0 if passed else 1,
            verification_stdout_tail="verification ok" if passed else "verification failed",
            verification_stderr_tail="",
        )
        return {
            "status": "passed" if passed else "failed",
            "returncode": 0 if passed else 1,
            "stdout": "verification ok" if passed else "verification failed",
            "stderr": "",
        }

    async def _normalize_completion_summary(**kwargs):
        return {
            "status": "completed",
            "artifacts_created": [],
            "assumptions_added": [],
            "assumptions_changed": [],
            "blockers": [],
            "claims_created": [],
            "datasets_created": [],
            "open_questions": [],
            "recommended_next_tasks": [],
            "sources_used": [],
            "verification_results": [],
        }

    async def _task_record(*args, **kwargs):
        return None

    monkeypatch.setattr(session_lifecycle, "_list_changed_files", _list_changed_files)
    monkeypatch.setattr(session_lifecycle, "_publish_completed_session_outputs", _publish_completed_session_outputs)
    monkeypatch.setattr(session_lifecycle, "_run_workspace_verification", _run_workspace_verification)
    monkeypatch.setattr(session_lifecycle, "_normalize_completion_summary", _normalize_completion_summary)
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "_copy_workspace_state_indexes", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_lifecycle, "_sync_completion_summary_to_integrity_indexes", lambda *args, **kwargs: None)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda _root: {"data": {"status": "ready"}})
    monkeypatch.setattr(session_lifecycle, "record_publish_failure", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(session_lifecycle, "record_publish_success", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", lambda *args, **kwargs: asyncio.sleep(0))

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-published-verify",
            session={"role": "data", "taskId": "task-verify-after-publish"},
            project={"slug": "published-verification-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    assert state["publish_status"] == "published"
    assert state["verification_status"] == "passed"
    assert state["review_status"] == "review"


def test_publish_completed_session_outputs_uses_file_backed_slug_task_id_for_allowed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Publish Scope Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-scope")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-scope",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    source_rel = ".ontology/sources/example.yaml"
    source_path = workspace_root / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("name: example\n", encoding="utf-8")
    session_files.update_state(session_root, task_id="replace-placeholder-ontology-source-configs-with-real-soccer-data-definitions")

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": [".ontology/sources"]}

    async def _publish(project: dict, *, repo_root: Path, changed_paths: list[str], commit_message: str, allowed_paths=None):
        publish_calls.append({
            "changed_paths": changed_paths,
            "allowed_paths": allowed_paths,
            "commit_message": commit_message,
        })
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "feedbeef",
            "branch": "main",
            "changed": True,
            "files": [{"path": source_rel, "changed": True}],
            "skipped_files": [],
        }

    async def _record_success(*args, **kwargs):
        return None

    publish_calls: list[dict[str, object]] = []
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)

    asyncio.run(
        session_lifecycle._publish_completed_session_outputs(
            project={"_id": "project-9", "slug": "publish-scope-project", "defaultBranch": "main", "github": "Rutgers-Economics-Labs/example"},
            session={"role": "data"},
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            changed_files=[source_rel],
        )
    )

    assert publish_calls[0]["allowed_paths"] == [".ontology/sources"]
    assert publish_calls[0]["changed_paths"] == [source_rel]
    assert (tmp_path / source_rel).read_text(encoding="utf-8") == "name: example\n"


def test_publish_completed_session_outputs_locally_mirrors_files_without_github_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Local Mirror Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "health", "sess-local-mirror")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "health",
        "sess-local-mirror",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    artifact_rel = "artifacts/reproducibility/trusted_artifacts_manifest.md"
    artifact_path = workspace_root / artifact_rel
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Trusted Artifacts\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        task_id="repair-reproducibility-metadata-for-trusted-artifacts",
    )

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": ["artifacts", "topics", "research_plan/state"]}

    record_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def _record_success(*args, **kwargs):
        record_calls.append((args, kwargs))

    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)

    result = asyncio.run(
        session_lifecycle._publish_completed_session_outputs(
            project={"_id": "project-11", "slug": "local-mirror-project", "defaultBranch": "main"},
            session={"role": "health"},
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            changed_files=[artifact_rel],
        )
    )

    state = session_files.read_state(session_root)

    assert result["published"] is True
    assert result["strategy"] == "local_workspace_mirror"
    assert result["changed"] is True
    assert result["files"] == [{"path": artifact_rel, "changed": True}]
    assert (tmp_path / artifact_rel).read_text(encoding="utf-8") == "# Trusted Artifacts\n"
    assert state["publish_status"] == "published"
    assert state["publish_strategy"] == "local_workspace_mirror"
    assert state["publish_changed_files"] == [artifact_rel]
    assert record_calls == []


def test_publish_completed_session_outputs_copies_binary_files_and_registers_hydration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Publish Binary Project")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-binary")
    workspace_root, workspace_branch, _workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-binary",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    duckdb_rel = ".ontology/onto.duckdb"
    meta_rel = ".ontology/.rail_hydration.json"
    duckdb_path = workspace_root / duckdb_rel
    meta_path = workspace_root / meta_rel
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    duckdb_path.write_bytes(b"\x80DUCK")
    meta_path.write_text(json.dumps({"pipeline_slug": "default", "hydration_mode": "full"}), encoding="utf-8")
    session_files.update_state(session_root, task_id="hydrate-soccer-ontology-and-register-active-artifacts")

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": [".ontology"]}

    async def _publish(project: dict, *, repo_root: Path, changed_paths: list[str], commit_message: str, allowed_paths=None):
        publish_calls.append({
            "changed_paths": changed_paths,
            "allowed_paths": allowed_paths,
        })
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "cafebabe",
            "branch": "main",
            "changed": True,
            "files": [{"path": duckdb_rel, "changed": True}, {"path": meta_rel, "changed": True}],
            "skipped_files": [],
        }

    async def _record_success(*args, **kwargs):
        return None

    async def _register_hydration_artifact(**kwargs):
        registered.append(kwargs)
        return "artifact-123"

    publish_calls: list[dict[str, object]] = []
    registered: list[dict[str, object]] = []
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)
    monkeypatch.setattr("app.services.hydration_registry_service.register_hydration_artifact", _register_hydration_artifact)

    asyncio.run(
        session_lifecycle._publish_completed_session_outputs(
            project={"_id": "project-10", "slug": "publish-binary-project", "defaultBranch": "main", "github": "Rutgers-Economics-Labs/example"},
            session={"role": "data"},
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            changed_files=[duckdb_rel, meta_rel],
        )
    )

    assert publish_calls[0]["allowed_paths"] == [".ontology"]
    assert (tmp_path / duckdb_rel).read_bytes() == b"\x80DUCK"
    assert registered[0]["duckdb_artifact_path"] == str(tmp_path / duckdb_rel)


def test_finalize_workspace_review_allows_hydration_metadata_dataset_with_synced_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Hydration Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-hydration-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-hydration-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-hydration-contract",
            role="data",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )

    (workspace_root / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    (workspace_root / ".ontology" / "pipelines").mkdir(parents=True, exist_ok=True)
    (workspace_root / ".ontology" / "sources" / "sample.yaml").write_text("name: Sample\n", encoding="utf-8")
    (workspace_root / ".ontology" / "pipelines" / "default.yaml").write_text("steps:\n  - api: sample\n", encoding="utf-8")
    (workspace_root / ".ontology" / "onto.duckdb").write_bytes(b"DUCK")
    (workspace_root / ".ontology" / ".rail_hydration.json").write_text(
        json.dumps({"pipeline_slug": "default", "hydration_mode": "full"}, indent=2),
        encoding="utf-8",
    )

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
        task_id="hydrate-soccer-ontology-and-register-active-artifacts",
    )

    async def _publish(project: dict, *, repo_root: Path, changed_paths: list[str], commit_message: str, allowed_paths=None):
        return {
            "published": False,
            "strategy": "github_app_commit",
            "commit_sha": "headsha",
            "branch": "main",
            "changed": False,
            "files": [],
            "skipped_files": changed_paths,
        }

    async def _register_hydration_artifact(**kwargs):
        return "artifact-123"

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    task_updates: list[dict[str, object]] = []
    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr("app.services.hydration_registry_service.register_hydration_artifact", _register_hydration_artifact)
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-hydration-contract",
            session={"role": "data", "taskId": "task-hydration"},
            project={"_id": "project-h", "slug": "hydration-contract-project", "defaultBranch": "main", "github": "Rutgers-Economics-Labs/example"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert not any(".rail_hydration.json" in item and "datasetsMissingProvenance" in item for item in blockers)
    assert not any(".rail_hydration.json" in item and "datasetsMissingFreshness" in item for item in blockers)


def test_finalize_workspace_review_blocks_task_on_publish_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Blocked Publish Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-fail")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-fail",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-fail",
            role="data",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "research").mkdir(parents=True, exist_ok=True)
    (workspace_root / "research" / "notes.md").write_text("# Notes\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _raise_publish(*args, **kwargs):
        raise RuntimeError("connector auth failed")

    async def _record_failure(project_id: str, message: str) -> None:
        failures.append((project_id, message))

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _decision(*args, **kwargs):
        decisions.append(kwargs)
        return None

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": ["research"]}

    task_updates: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    failures: list[tuple[str, str]] = []

    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _raise_publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_failure", _record_failure)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "raise_decision_event", _decision)
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)

    project = {
        "_id": "project-2",
        "slug": "blocked-publish-project",
        "defaultBranch": "main",
        "github": "Rutgers-Economics-Labs/RAIL-doge-government-payments-and-savings-ana",
    }
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-fail",
            session={"role": "data", "taskId": "task-publish"},
            project=project,
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)

    assert state["publish_status"] == "failed"
    assert state["review_status"] == "needs_changes"
    assert failures == [("project-2", "connector auth failed")]
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "publish_failure"
    assert decisions[0]["event_type"] == "publish_failed"


def test_finalize_workspace_review_marks_task_done_when_verification_failures_are_outside_task_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Scoped Repair Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo 'VERIFICATION FAILED'\n"
        "echo 'Phase: ontology-ingestion'\n"
        "echo 'Repo root:' \"$PWD\"\n"
        "echo '- Placeholder or review-only ontology source: .ontology/sources/source-a.yaml (example.com)'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-scoped")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "planner",
        "sess-scoped",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-scoped",
            role="planner",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _publish(*args, **kwargs):
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "cafebabe",
            "branch": "main",
            "changed": False,
            "files": [],
            "skipped_files": [],
        }

    async def _record_success(*args, **kwargs):
        return None

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": ["scripts"]}

    task_updates: list[dict[str, object]] = []
    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)
    monkeypatch.setattr(session_lifecycle, "record_publish_failure", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_args, **_kwargs: {})

    project = {
        "_id": "project-3",
        "slug": "scoped-repair-project",
        "defaultBranch": "main",
        "github": "Rutgers-Economics-Labs/RAIL-scoped-repair-project",
    }
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-scoped",
            session={"role": "planner", "taskId": "repair-task"},
            project=project,
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    assert state["verification_status"] == "failed"
    assert state["review_status"] == "review"
    assert task_updates[-1]["status"] == "done"
    assert "outside this task scope" in str(task_updates[-1]["latestRunSummary"])


def test_finalize_workspace_review_keeps_worker_task_in_review_when_audit_still_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Blocked Audit Worker Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "echo 'VERIFICATION FAILED'\n"
        "echo '- Missing processed longitudinal panel dataset: topics/data/processed/longitudinal_panel.csv'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-blocked-audit")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-blocked-audit",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-blocked-audit",
            role="data",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    data_note = workspace_root / "topics" / "data_provenance.md"
    data_note.parent.mkdir(parents=True, exist_ok=True)
    data_note.write_text("# Data provenance\n\nSeeded inputs.\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    async def _publish(*args, **kwargs):
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "deadbeef",
            "branch": "main",
            "changed": False,
            "files": [],
            "skipped_files": [],
        }

    async def _record_success(*args, **kwargs):
        return None

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _task_record(project: dict, task_id: str | None):
        return {"_id": task_id, "repoPaths": [".ontology"]}

    task_updates: list[dict[str, object]] = []
    monkeypatch.setattr(session_lifecycle, "publish_repo_files", _publish)
    monkeypatch.setattr(session_lifecycle, "record_publish_success", _record_success)
    monkeypatch.setattr(session_lifecycle, "record_publish_failure", lambda *args, **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "_task_record", _task_record)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_args, **_kwargs: {})

    project = {
        "_id": "project-4",
        "slug": "blocked-audit-worker-project",
        "defaultBranch": "main",
        "github": "Rutgers-Economics-Labs/RAIL-blocked-audit-worker-project",
        "localRepoPath": str(tmp_path),
    }
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-blocked-audit",
            session={"role": "data", "taskId": "repair-task"},
            project=project,
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    assert state["verification_status"] == "failed"
    assert state["review_status"] == "review"
    assert task_updates[-1]["status"] == "review"
    assert "awaiting a reviewed post-run audit" in str(task_updates[-1]["latestRunSummary"])


def test_relay_terminal_status_uses_session_file_task_id_for_slug_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Relay Task Project")
    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-relay")
    session_files.update_state(session_root, task_id="repair-verification-automation-for-ontology-ingestion-handoffs")

    updates: list[dict[str, object]] = []
    syncs: list[str] = []

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "project-relay"
        return {
            "_id": "project-relay",
            "slug": "relay-task-project",
            "localRepoPath": str(tmp_path),
        }

    async def _update_task(task_id: str, *, project: dict, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id}

    async def _sync(project: dict):
        syncs.append(project["slug"])

    monkeypatch.setattr(session_lifecycle.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle.planner_service, "sync_planner_files", _sync)

    event = session_lifecycle.RunnerEvent(
        session_id="sess-relay",
        event_type=session_lifecycle.RunnerEventType.COMPLETED,
        normalized_payload={"message": "completed cleanly"},
    )
    asyncio.run(
        session_lifecycle._relay_terminal_status(
            {
                "_id": "sess-relay",
                "projectId": "project-relay",
                "projectSlug": "relay-task-project",
                "role": "planner",
            },
            event,
        )
    )

    assert updates[0]["task_id"] == "repair-verification-automation-for-ontology-ingestion-handoffs"
    assert updates[0]["status"] == "review"
    assert syncs == ["relay-task-project"]


def test_relay_approval_requested_uses_repo_first_project_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Relay Approval Project")

    approvals_requested: list[dict[str, object]] = []

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "project-approval"
        return {
            "_id": "project-approval",
            "slug": "relay-approval-project",
            "localRepoPath": str(tmp_path),
        }

    async def _list_approvals(project: dict):
        assert project["slug"] == "relay-approval-project"
        return []

    async def _create_approval(*, project: dict, task_id: str, agent_session_id: str, **kwargs):
        approvals_requested.append(
            {
                "project": project["slug"],
                "task_id": task_id,
                "agent_session_id": agent_session_id,
                **kwargs,
            }
        )
        return {"_id": "approval-1"}

    async def _sync(project: dict):
        approvals_requested.append({"synced": project["slug"]})

    monkeypatch.setattr(session_lifecycle.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(session_lifecycle.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(session_lifecycle.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(session_lifecycle.planner_service, "sync_planner_files", _sync)

    event = session_lifecycle.RunnerEvent(
        session_id="sess-approval",
        event_type=session_lifecycle.RunnerEventType.APPROVAL_REQUESTED,
        normalized_payload={"prompt": "Need permission", "activity_key": "run_task"},
    )
    asyncio.run(
        session_lifecycle._relay_approval_requested(
            "sess-approval",
            {
                "_id": "sess-approval",
                "projectId": "project-approval",
                "projectSlug": "relay-approval-project",
                "role": "coding",
                "taskId": "approval-task",
            },
            event,
        )
    )

    assert approvals_requested[0]["project"] == "relay-approval-project"
    assert approvals_requested[0]["task_id"] == "approval-task"
    assert approvals_requested[0]["agent_session_id"] == "sess-approval"
    assert approvals_requested[1] == {"synced": "relay-approval-project"}


def test_finalize_workspace_review_blocks_coding_task_when_lineage_contract_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "report.md").write_text("# Report\n\nNew analysis output.\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract",
            session={"role": "coding", "taskId": "task-contract"},
            project={"_id": "project-3", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `coding`." in item for item in blockers)
    assert any("artifactsMissingLineage: artifacts/report.md" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_blocks_coding_task_when_verification_commands_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract-commands")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract-commands",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract-commands",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "report.md").write_text("# Report\n\nNew analysis output.\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract-commands",
            session={"role": "coding", "taskId": "task-contract-commands"},
            project={"_id": "project-3b", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `coding`." in item for item in blockers)
    assert any("artifactsMissingVerificationCommands: artifacts/report.md" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_blocks_coding_task_when_verification_runs_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract-runs")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract-runs",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract-runs",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": [],
            }
        ]
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "report.md").write_text("# Report\n\nNew analysis output.\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract-runs",
            session={"role": "coding", "taskId": "task-contract-runs"},
            project={"_id": "project-3c", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `coding`." in item for item in blockers)
    assert any("artifactsMissingVerification: artifacts/report.md" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_infers_coding_lineage_from_companion_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract-inferred")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract-inferred",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract-inferred",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts" / "analysis_targets").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "analysis_targets" / "README.md").write_text(
        "# Analysis Targets\n",
        encoding="utf-8",
    )
    helper_script = workspace_root / "artifacts" / "analysis_targets" / "run_analysis_target.sh"
    helper_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho list\n", encoding="utf-8")
    methodology = workspace_root / "research_plan" / "methodology.md"
    methodology.write_text("# Methodology\n", encoding="utf-8")
    # Also write to project root so _normalize_artifact_record_for_write keeps them
    (tmp_path / "artifacts" / "analysis_targets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "analysis_targets" / "README.md").write_text("# Analysis Targets\n", encoding="utf-8")
    (tmp_path / "artifacts" / "analysis_targets" / "run_analysis_target.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho list\n", encoding="utf-8"
    )
    (tmp_path / "research_plan" / "methodology.md").write_text("# Methodology\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_a, **_kw: {})

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract-inferred",
            session={"role": "coding", "taskId": "task-contract-inferred"},
            project={"_id": "project-3d", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    lineage = json.loads((tmp_path / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))
    readme_entry = next(item for item in lineage if item["artifact_path"] == "artifacts/analysis_targets/README.md")

    assert state["review_status"] == "review"
    assert not any("workflow contract failed" in item.lower() for item in state["completion_summary"]["blockers"])
    assert "artifacts/analysis_targets/run_analysis_target.sh" in readme_entry["scripts"]
    assert "research_plan/methodology.md" in readme_entry["inputs"]
    assert task_updates[-1]["status"] == "review"


def test_finalize_workspace_review_enriches_existing_placeholder_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract-placeholder")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract-placeholder",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract-placeholder",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts" / "analysis_targets").mkdir(parents=True, exist_ok=True)
    readme = workspace_root / "artifacts" / "analysis_targets" / "README.md"
    readme.write_text("# Analysis Targets\n", encoding="utf-8")
    helper_script = workspace_root / "artifacts" / "analysis_targets" / "run_analysis_target.sh"
    helper_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho list\n", encoding="utf-8")
    methodology = workspace_root / "research_plan" / "methodology.md"
    methodology.write_text("# Methodology\n", encoding="utf-8")
    # Also write to project root so _normalize_artifact_record_for_write keeps them
    (tmp_path / "artifacts" / "analysis_targets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "analysis_targets" / "README.md").write_text("# Analysis Targets\n", encoding="utf-8")
    (tmp_path / "artifacts" / "analysis_targets" / "run_analysis_target.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho list\n", encoding="utf-8"
    )
    (tmp_path / "research_plan" / "methodology.md").write_text("# Methodology\n", encoding="utf-8")
    # Seed verification_runs FIRST, then write placeholder lineage to project root.
    # (workspace_lineage=None causes the sync to fall through to existing_lineage.verification_runs.)
    project_repo = ResearchIntegrityRepo(tmp_path)
    project_repo.upsert_verification_run(
        {
            "run_id": "seed-run",
            "status": "passed",
            "artifact_paths": ["artifacts/analysis_targets/README.md"],
        }
    )
    project_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/analysis_targets/README.md",
                "artifact_type": "report",
                "title": "README.md",
                "promotion_state": "draft",
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#seed-run"],
            }
        ]
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_a, **_kw: {})

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract-placeholder",
            session={"role": "coding", "taskId": "task-contract-placeholder"},
            project={"_id": "project-3e", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    lineage = json.loads((tmp_path / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))
    readme_entry = next(item for item in lineage if item["artifact_path"] == "artifacts/analysis_targets/README.md")

    assert state["review_status"] == "review"
    assert readme_entry["scripts"] == ["artifacts/analysis_targets/run_analysis_target.sh"]
    assert "research_plan/methodology.md" in readme_entry["inputs"]
    assert "research_plan/state/verification_runs.json#seed-run" in readme_entry["verification_runs"]
    assert task_updates[-1]["status"] == "review"


def test_finalize_workspace_review_preserves_unrelated_project_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Workflow Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)
    project_repo = ResearchIntegrityRepo(tmp_path)
    project_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/existing.md",
                "artifact_type": "report",
                "title": "existing.md",
                "promotion_state": "partially_verified",
                "inputs": ["topics/existing.md"],
                "scripts": ["scripts/existing.sh"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#existing-run"],
            }
        ]
    )

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-contract-preserve")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-contract-preserve",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-contract-preserve",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts" / "analysis_targets").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "analysis_targets" / "README.md").write_text(
        "# Analysis Targets\n",
        encoding="utf-8",
    )
    (workspace_root / "artifacts" / "analysis_targets" / "run_analysis_target.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho list\n",
        encoding="utf-8",
    )
    (workspace_root / "research_plan" / "methodology.md").write_text("# Methodology\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_a, **_kw: {})

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-contract-preserve",
            session={"role": "coding", "taskId": "task-contract-preserve"},
            project={"_id": "project-3f", "slug": "workflow-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    lineage = json.loads((tmp_path / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))

    assert {item["artifact_path"] for item in lineage} >= {
        "artifacts/existing.md",
        "artifacts/analysis_targets/README.md",
    }
    assert task_updates[-1]["status"] == "review"


def test_finalize_workspace_review_blocks_research_task_without_structured_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Research Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-research-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-research-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-research-contract",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics" / "brief.md").write_text("# Brief\n\nA single blended narrative.\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-research-contract",
            session={"role": "research", "taskId": "task-research-contract"},
            project={"_id": "project-4", "slug": "research-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Research markdown outputs must include `Facts`, `Interpretation`, and `Open Questions` sections." in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_blocks_data_task_without_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Data Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-data-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-data-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-data-contract",
            role="data",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Analysis Dataset",
                "promotion_state": "draft",
                "sources": [],
            }
        ]
    )
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics" / "analysis.csv").write_text("value\n1\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-data-contract",
            session={"role": "data", "taskId": "task-data-contract"},
            project={"_id": "project-4b", "slug": "data-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `data`." in item for item in blockers)
    assert any("datasetsMissingProvenance: topics/analysis.csv" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_blocks_data_task_without_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Data Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-data-freshness")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "data",
        "sess-data-freshness",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-data-freshness",
            role="data",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "unknown",
            }
        ]
    )
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Analysis Dataset",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#bls-laus"],
            }
        ]
    )
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics" / "analysis.csv").write_text("value\n1\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-data-freshness",
            session={"role": "data", "taskId": "task-data-freshness"},
            project={"_id": "project-4c", "slug": "data-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `data`." in item for item in blockers)
    assert any("datasetsMissingFreshness: topics/analysis.csv" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_blocks_health_task_with_integrity_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Health Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "health", "sess-health-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "health",
        "sess-health-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-health-contract",
            role="health",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "An unsupported claim.",
                "status": "needs_evidence",
            }
        ]
    )
    workspace_repo.write_sources(
        [
            {
                "source_key": "source-001",
                "title": "Stale source",
                "source_type": "document",
                "url_or_path": "sources/stale-source.md",
                "freshness_status": "stale",
                "acquired_at": "2026-01-01T00:00:00Z",
                "origin": "manual_import",
                "access_method": "local_file",
            }
        ]
    )
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report missing reproducibility lineage",
                "promotion_state": "draft",
            }
        ]
    )
    workspace_repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "failed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    _health_workflow = {
        "health": {
            "status": "blocked",
            "missingEvidenceClaims": ["claim-001"],
            "staleSources": ["source-001"],
            "inadmissibleSources": [],
            "reproducibilityGaps": ["artifacts/report.md"],
            "failedVerificationRuns": ["run-001"],
            "requirements": [],
        }
    }
    _health_blocker_bits = [
        "missingEvidenceClaims: claim-001",
        "staleSources: source-001",
        "reproducibilityGaps: artifacts/report.md",
        "failedVerificationRuns: run-001",
    ]

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)
    monkeypatch.setattr(session_lifecycle, "summarize_agent_workflow_health", lambda *_a, **_kw: _health_workflow)
    monkeypatch.setattr(session_lifecycle, "_relevant_workflow_blockers", lambda **_kw: _health_blocker_bits)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-health-contract",
            session={"role": "health", "taskId": "task-health-contract"},
            project={"_id": "project-4c", "slug": "health-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `health`." in item for item in blockers)
    assert any("missingEvidenceClaims: claim-001" in item for item in blockers)
    assert any("staleSources: source-001" in item for item in blockers)
    assert any("reproducibilityGaps: artifacts/report.md" in item for item in blockers)
    assert any("failedVerificationRuns: run-001" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_allows_research_task_with_structured_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Research Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-research-structured")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-research-structured",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-research-structured",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics" / "brief.md").write_text(
        "# Findings\n\n## Facts\nObserved values rose.\n\n## Interpretation\nThis may reflect demand growth.\n\n## Open Questions\nIs 2024 fully revised?\n",
        encoding="utf-8",
    )
    (workspace_root / "research_plan" / "state" / "claims.json").write_text(
        json.dumps(
            [
                {
                    "claim_key": "claim-001",
                    "claim_text": "Observed values rose after 2021.",
                    "artifact_path": "topics/brief.md",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-research-structured",
            session={"role": "research", "taskId": "task-research-structured"},
            project={"_id": "project-5", "slug": "research-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)

    assert state["review_status"] == "review"
    assert not any("workflow contract failed" in item.lower() for item in state["completion_summary"]["blockers"])
    assert task_updates[-1]["status"] == "review"


def test_finalize_workspace_review_blocks_research_task_without_claim_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Research Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-research-no-claims")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-research-no-claims",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-research-no-claims",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "topics").mkdir(parents=True, exist_ok=True)
    (workspace_root / "topics" / "brief.md").write_text(
        "# Findings\n\n## Facts\nObserved values rose.\n\n## Interpretation\nThis may reflect demand growth.\n\n## Open Questions\nIs 2024 fully revised?\n",
        encoding="utf-8",
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-research-no-claims",
            session={"role": "research", "taskId": "task-research-no-claims"},
            project={"_id": "project-5b", "slug": "research-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `research`." in item for item in blockers)
    assert any("must produce at least one claim candidate" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_accepts_research_findings_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Research Findings Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-research-findings")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "research",
        "sess-research-findings",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-research-findings",
            role="research",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    findings_dir = workspace_root / "research" / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    (findings_dir / "source_inventory.md").write_text(
        "# Findings\n\n## Facts\nObserved values rose.\n\n## Interpretation\nThis may reflect demand growth.\n\n## Open Questions\nIs 2024 fully revised?\n",
        encoding="utf-8",
    )
    (workspace_root / "research_plan" / "state" / "claims.json").write_text(
        json.dumps(
            [
                {
                    "claim_key": "claim-001",
                    "claim_text": "Observed values rose after 2021.",
                    "artifact_path": "research/findings/source_inventory.md",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-research-findings",
            session={"role": "research", "taskId": "task-research-findings"},
            project={"_id": "project-5c", "slug": "research-findings-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)

    assert state["review_status"] == "review"
    assert not any("workflow contract failed" in item.lower() for item in state["completion_summary"]["blockers"])
    assert task_updates[-1]["status"] == "review"


def test_process_is_running_treats_zombies_as_not_running(monkeypatch: pytest.MonkeyPatch):
    from subprocess import CompletedProcess
    from app.runners import session_lifecycle

    monkeypatch.setattr(session_lifecycle.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(
        session_lifecycle.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args=args, returncode=0, stdout="Z\n", stderr=""),
    )

    assert session_lifecycle._process_is_running(12345) is False


def test_should_retry_false_publish_failure_when_commit_and_verification_exist():
    assert session_lifecycle._should_retry_false_publish_failure(
        {
            "status": "completed",
            "publish_status": "failed",
            "publish_commit_sha": "abc123",
            "verification_status": "passed",
            "review_status": "needs_changes",
        }
    ) is True

    assert session_lifecycle._should_retry_false_publish_failure(
        {
            "status": "completed",
            "publish_status": "failed",
            "publish_commit_sha": "",
            "verification_status": "passed",
            "review_status": "needs_changes",
        }
    ) is False


def test_relevant_workflow_blockers_filters_to_task_outputs():
    blockers = session_lifecycle._relevant_workflow_blockers(
        role_health={
            "status": "blocked",
            "datasetsMissingProvenance": [
                ".ontology/.rail_hydration.json",
                ".ontology/onto.duckdb",
                ".ontology/sources/catalog.csv",
            ],
            "datasetsMissingFreshness": [
                ".ontology/.rail_hydration.json",
                ".ontology/sources/catalog.csv",
            ],
        },
        changed_files=[".ontology/.rail_hydration.json", ".ontology/sources/catalog.csv", "topics/source_notes.md"],
        summary={
            "datasets_created": [".ontology/.rail_hydration.json", ".ontology/sources/catalog.csv"],
            "artifacts_created": ["topics/source_notes.md"],
        },
    )

    assert blockers == [
        "datasetsMissingProvenance: .ontology/sources/catalog.csv",
        "datasetsMissingFreshness: .ontology/sources/catalog.csv",
    ]


def test_finalize_workspace_review_blocks_artifact_task_without_evidence_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Artifact Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "artifact", "sess-artifact-contract")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "artifact",
        "sess-artifact-contract",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-artifact-contract",
            role="artifact",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "memo.md").write_text("# Memo\n\nNarrative without explicit evidence links.\n", encoding="utf-8")

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-artifact-contract",
            session={"role": "artifact", "taskId": "task-artifact-contract"},
            project={"_id": "project-6", "slug": "artifact-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Artifact markdown outputs must include an `Evidence Links` section" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_finalize_workspace_review_allows_artifact_task_with_evidence_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Artifact Contract Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "artifact", "sess-artifact-structured")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "artifact",
        "sess-artifact-structured",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-artifact-structured",
            role="artifact",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "memo.md").write_text(
        "# Memo\n\n## Evidence Links\n- research_plan/state/claims.json#claim-001\n- research_plan/state/sources.json#source-001\n",
        encoding="utf-8",
    )
    # Phase 2 protocol: promotion-class sessions must emit session_result.json.
    session_result_dir = workspace_root / "research_plan" / "sessions" / "artifact" / "sess-artifact-structured"
    session_result_dir.mkdir(parents=True, exist_ok=True)
    (session_result_dir / "session_result.json").write_text(
        json.dumps(
            {
                "session_id": "sess-artifact-structured",
                "status": "completed",
                "summary": "Wrote memo with evidence links.",
                "task_type": "artifact_writing",
                "runner_name": "test_runner",
                "files_changed": ["artifacts/memo.md"],
            }
        ),
        encoding="utf-8",
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-artifact-structured",
            session={"role": "artifact", "taskId": "task-artifact-structured"},
            project={"_id": "project-7", "slug": "artifact-contract-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)

    assert state["review_status"] == "review"
    assert not any("workflow contract failed" in item.lower() for item in state["completion_summary"]["blockers"])
    assert task_updates[-1]["status"] == "review"


def test_finalize_workspace_review_blocks_artifact_task_with_unsupported_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bootstrap_future_project(tmp_path, name="Artifact Unsupported Claim Project")
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho 'verification ok'\n", encoding="utf-8")
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "artifact", "sess-artifact-unsupported")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "artifact",
        "sess-artifact-unsupported",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )
    asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-artifact-unsupported",
            role="artifact",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (workspace_root / "artifacts" / "memo.md").write_text(
        "# Memo\n\n## Evidence Links\n- research_plan/state/claims.json#claim-unsupported\n- research_plan/state/sources.json#source-001\n",
        encoding="utf-8",
    )
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_claims(
        [
            {
                "claim_key": "claim-unsupported",
                "claim_text": "A narrative claim that still needs evidence.",
                "status": "needs_evidence",
            }
        ]
    )
    workspace_repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/memo.md",
                "artifact_type": "report",
                "title": "Unsupported memo",
                "promotion_state": "draft",
                "claims": ["research_plan/state/claims.json#claim-unsupported"],
            }
        ]
    )

    task_updates: list[dict[str, object]] = []

    async def _update_task(task_id: str, *, project: dict, **fields):
        task_updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    monkeypatch.setattr(session_lifecycle.planner_service, "update_task", _update_task)

    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-artifact-unsupported",
            session={"role": "artifact", "taskId": "task-artifact-unsupported"},
            project={"_id": "project-7b", "slug": "artifact-unsupported-project", "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    blockers = state["completion_summary"]["blockers"]

    assert state["review_status"] == "needs_changes"
    assert any("Role workflow contract failed for `artifact`." in item for item in blockers)
    assert any("artifactsWithUnsupportedClaims: artifacts/memo.md" in item for item in blockers)
    assert task_updates[0]["status"] == "blocked"
    assert task_updates[0]["blockerCategory"] == "workflow_contract"


def test_get_runner_session_forces_final_ingest_for_terminal_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-terminal")
    session_files.update_state(
        root,
        status="running",
        review_status="pending",
        workspace_path=str(tmp_path / "workspace"),
        workspace_branch="coding-sess-terminal",
    )

    async def _get_running_agent(session_id: str):
        return {
            "_id": session_id,
            "status": "running",
            "runner": "codex_cli",
            "role": "coding",
            "externalSessionId": "external-1",
            "sessionPath": str(root),
            "projectId": "project-1",
        }

    async def _update_running_agent(session_id: str, **fields):
        return None

    class _FakeRunner:
        async def get_session(self, external_id: str):
            return {"status": "completed", "normalized_status": "completed"}

    ingest_calls: list[str] = []

    async def _ingest(session_id: str, *, project_id: str | None = None):
        ingest_calls.append(session_id)
        session_files.update_state(
            root,
            status="completed",
            publish_status="published",
            publish_strategy="github_app_commit",
            publish_commit_sha="abc123",
            verification_status="passed",
        )
        return []

    async def _fake_local_ingest(*, convex_session_id, session, root):
        return {"status": "completed", "normalized_status": "completed"}

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _update_running_agent)
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())
    monkeypatch.setattr(session_lifecycle, "_ingest_local_cli_runner_events", _fake_local_ingest)
    monkeypatch.setattr(session_lifecycle, "ingest_session_events", _ingest)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-terminal",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert ingest_calls == ["sess-terminal"]
    assert result["fileState"]["publish_status"] == "published"
    assert result["fileState"]["publish_commit_sha"] == "abc123"


def test_session_task_id_falls_back_to_session_file_state(tmp_path: Path):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-task-fallback")
    session_files.update_state(session_root, task_id="design-ontology-backed-ingestion-plan-for-soccer-ecosystem-data")

    assert (
        session_lifecycle._session_task_id(
            {"_id": "sess-task-fallback", "role": "data"},
            session_root,
        )
        == "design-ontology-backed-ingestion-plan-for-soccer-ecosystem-data"
    )


def test_load_project_prefers_repo_first_slug_resolution(monkeypatch: pytest.MonkeyPatch):
    project = {
        "_id": "local:demo-project",
        "slug": "demo-project",
        "localRepoPath": "/tmp/demo-project",
    }

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return dict(project)

    async def _query(path: str, payload: dict):
        raise AssertionError(f"_load_project should not query convex when repo-first resolution succeeds: {path}")

    monkeypatch.setattr(session_lifecycle.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(session_lifecycle.convex, "query", _query)

    loaded = asyncio.run(session_lifecycle._load_project(None, "demo-project"))

    assert loaded == project


def test_load_project_prefers_repo_first_id_resolution(monkeypatch: pytest.MonkeyPatch):
    project = {
        "_id": "project-123",
        "slug": "demo-project",
        "localRepoPath": "/tmp/demo-project",
    }

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "project-123"
        return dict(project)

    async def _query(path: str, payload: dict):
        raise AssertionError(f"_load_project should not query convex when repo-first id resolution succeeds: {path}")

    monkeypatch.setattr(session_lifecycle.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(session_lifecycle.convex, "query", _query)

    loaded = asyncio.run(session_lifecycle._load_project("project-123", "demo-project"))

    assert loaded == project


def test_get_runner_session_falls_back_to_file_backed_session_when_runtime_row_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "research", "sess-file-backed")
    session_files.update_state(
        session_root,
        status="completed",
        role="research",
        runner="codex_cli",
        external_session_id="codex_cli_deadbeef",
        review_status="review",
    )

    async def _get_running_agent(session_id: str):
        return None

    async def _load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": "project-1",
            "slug": "soccer-project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(session_lifecycle, "_load_project", _load_project)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-file-backed",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert result["_id"] == "sess-file-backed"
    assert result["status"] == "completed"
    assert result["fileState"]["review_status"] == "review"


def test_finalize_workspace_review_reconciles_repo_truth_for_terminal_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-reconcile")
    session_files.update_state(
        session_root,
        status="completed",
        role="planner",
        review_status="pending",
        workspace_path=None,
    )

    reconcile_calls: list[str] = []

    async def _write_post_run_audit(**kwargs):
        return None

    async def _reconcile_project_truth(project):
        reconcile_calls.append(project["slug"])

    monkeypatch.setattr(session_lifecycle, "write_post_run_audit", _write_post_run_audit)
    monkeypatch.setattr(
        session_lifecycle,
        "_reconcile_project_truth_after_terminal_session",
        _reconcile_project_truth,
    )

    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-reconcile",
            session={"role": "planner", "taskId": "task-reconcile"},
            project={"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path), "defaultBranch": "main"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    assert reconcile_calls == ["soccer-project"]


def test_get_runner_session_finalizes_file_backed_completed_session_when_review_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-finalize")
    session_files.update_state(
        session_root,
        status="completed",
        role="data",
        runner="codex_cli",
        review_status="pending",
        verification_status=None,
        publish_status="not_started",
        task_id="create-platform-api-configs-for-priority-soccer-data-sources",
    )

    async def _get_running_agent(session_id: str):
        return None

    async def _load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": "project-1",
            "slug": "soccer-project",
            "localRepoPath": str(tmp_path),
            "defaultBranch": "main",
        }

    finalize_calls: list[dict[str, object]] = []

    async def _finalize_workspace_review(**kwargs):
        finalize_calls.append(kwargs)
        session_files.update_state(
            kwargs["session_root"],
            review_status="review",
            verification_status="passed",
            publish_status="published",
        )

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(session_lifecycle, "_load_project", _load_project)
    monkeypatch.setattr(session_lifecycle, "_finalize_workspace_review", _finalize_workspace_review)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-finalize",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert len(finalize_calls) == 1
    assert finalize_calls[0]["session"]["taskId"] == "create-platform-api-configs-for-priority-soccer-data-sources"
    assert result["fileState"]["review_status"] == "review"
    assert result["fileState"]["verification_status"] == "passed"
    assert result["fileState"]["publish_status"] == "published"


def test_get_runner_session_retries_post_publish_verification_for_stale_failed_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-retry-publish-verify")
    session_files.update_state(
        session_root,
        status="completed",
        role="data",
        runner="codex_cli",
        review_status="needs_changes",
        verification_status="failed",
        publish_status="published",
        task_id="create-platform-api-configs-for-priority-soccer-data-sources",
    )

    async def _get_running_agent(session_id: str):
        return None

    async def _load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": "project-1",
            "slug": "soccer-project",
            "localRepoPath": str(tmp_path),
            "defaultBranch": "main",
        }

    finalize_calls: list[dict[str, object]] = []

    async def _finalize_workspace_review(**kwargs):
        finalize_calls.append(kwargs)
        session_files.update_state(
            kwargs["session_root"],
            review_status="review",
            verification_status="passed",
            publish_status="published",
        )

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(session_lifecycle, "_load_project", _load_project)
    monkeypatch.setattr(session_lifecycle, "_finalize_workspace_review", _finalize_workspace_review)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-retry-publish-verify",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert len(finalize_calls) == 1
    assert result["fileState"]["review_status"] == "review"
    assert result["fileState"]["verification_status"] == "passed"


def test_get_runner_session_retries_stale_workflow_contract_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-retry-workflow-review")
    session_files.update_state(
        session_root,
        status="completed",
        role="data",
        runner="codex_cli",
        review_status="needs_changes",
        verification_status="passed",
        publish_status="published",
        completion_summary={
            "blockers": ["Role workflow contract failed for `data`. datasetsMissingProvenance: topics/data.csv"],
        },
        task_id="create-platform-api-configs-for-priority-soccer-data-sources",
    )

    async def _get_running_agent(session_id: str):
        return None

    async def _load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": "project-1",
            "slug": "soccer-project",
            "localRepoPath": str(tmp_path),
            "defaultBranch": "main",
        }

    finalize_calls: list[dict[str, object]] = []

    async def _finalize_workspace_review(**kwargs):
        finalize_calls.append(kwargs)
        session_files.update_state(
            kwargs["session_root"],
            review_status="review",
            verification_status="passed",
            publish_status="published",
            completion_summary={"blockers": []},
        )

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(session_lifecycle, "_load_project", _load_project)
    monkeypatch.setattr(session_lifecycle, "_finalize_workspace_review", _finalize_workspace_review)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-retry-workflow-review",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert len(finalize_calls) == 1
    assert result["fileState"]["review_status"] == "review"


def test_get_runner_session_retries_stale_needs_changes_without_blockers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-retry-stale-review")
    session_files.update_state(
        session_root,
        status="completed",
        role="data",
        runner="codex_cli",
        review_status="needs_changes",
        verification_status="passed",
        publish_status="published",
        completion_summary={"blockers": []},
        task_id="create-platform-api-configs-for-priority-soccer-data-sources",
    )

    async def _get_running_agent(session_id: str):
        return None

    async def _load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": "project-1",
            "slug": "soccer-project",
            "localRepoPath": str(tmp_path),
            "defaultBranch": "main",
        }

    finalize_calls: list[dict[str, object]] = []

    async def _finalize_workspace_review(**kwargs):
        finalize_calls.append(kwargs)
        session_files.update_state(
            kwargs["session_root"],
            review_status="review",
            verification_status="passed",
            publish_status="published",
            completion_summary={"blockers": []},
        )

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(session_lifecycle, "_load_project", _load_project)
    monkeypatch.setattr(session_lifecycle, "_finalize_workspace_review", _finalize_workspace_review)

    result = asyncio.run(
        session_lifecycle.get_runner_session(
            "sess-retry-stale-review",
            sync_from_runner=True,
            project_id="project-1",
        )
    )

    assert len(finalize_calls) == 1
    assert result["fileState"]["review_status"] == "review"


def test_ingest_local_cli_runner_events_marks_exited_process_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    session_root = session_files.ensure_session_root(tmp_path, "data", "sess-exited")
    session_files.update_state(
        session_root,
        status="running",
        role="data",
        runner="codex_cli",
        review_status="pending",
    )
    runtime = session_root / ".runner"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "stdout.log").write_text("", encoding="utf-8")
    (runtime / "stderr.log").write_text("", encoding="utf-8")
    (runtime / "exit_code.txt").write_text("0\n", encoding="utf-8")
    (runtime / "pid.txt").write_text("424242\n", encoding="utf-8")

    class _FakeRunner(session_lifecycle.LocalCLIRunner):
        runner_name = "codex_cli"
        command = "true"

    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())
    monkeypatch.setattr(session_lifecycle, "_relay_runner_event", lambda *args, **kwargs: asyncio.sleep(0, result=None))
    monkeypatch.setattr(session_lifecycle, "_process_is_running", lambda pid: False)

    result = asyncio.run(
        session_lifecycle._ingest_local_cli_runner_events(
            convex_session_id="sess-exited",
            session={
                "_id": "sess-exited",
                "runner": "codex_cli",
                "externalSessionId": "codex_cli_dead",
                "status": "running",
            },
            root=session_root,
        )
    )

    state = session_files.read_state(session_root)
    assert result["status"] == "completed"
    assert result["normalized_status"] == "completed"
    assert state["status"] == "completed"
    assert state["review_status"] == "review"
    assert state["runner_returncode"] == 0
