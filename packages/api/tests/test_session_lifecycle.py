from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from app.runners import session_lifecycle
from app.services import session_files
from app.services import running_agent_service
from app.services.role_runtime_service import load_role_runtime_config
from rail.bootstrap import bootstrap_future_project


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


def test_workspace_review_flow_runs_setup_and_verification(tmp_path: Path):
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
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-1",
            session={"role": "coding"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    diff_text = (session_root / "diff.md").read_text(encoding="utf-8")
    verification_text = (session_root / "verification.md").read_text(encoding="utf-8")

    assert state["verification_status"] == "passed"
    assert state["review_status"] == "review"
    assert "README.md" in diff_text
    assert "status: `passed`" in verification_text


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
    (workspace_root / "artifacts" / "report.md").write_text("# Report\n", encoding="utf-8")
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


def test_create_runner_session_rejects_write_run_in_assisted_mode(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Approval Project")

    async def _fake_load_project(project_id: str | None, project_slug: str | None):
        return {
            "_id": project_id or "project-1",
            "slug": project_slug or "approval-project",
            "localRepoPath": str(tmp_path),
        }

    async def _fake_find_active_worker(project_id: str):
        return None

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(running_agent_service, "find_active_worker", _fake_find_active_worker)

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

    async def _fake_find_active_worker(project_id: str):
        return None

    async def _fake_create_running_agent(**kwargs):
        return "sess-approved"

    async def _fake_update_running_agent(*args, **kwargs):
        return None

    monkeypatch.setattr(session_lifecycle, "_load_project", _fake_load_project)
    monkeypatch.setattr(running_agent_service, "find_active_worker", _fake_find_active_worker)
    monkeypatch.setattr(running_agent_service, "create_running_agent", _fake_create_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _fake_update_running_agent)
    monkeypatch.setattr(session_lifecycle, "_materialize_workspace", lambda **kwargs: asyncio.sleep(0, result={"mode": "directory"}))
    monkeypatch.setattr(session_lifecycle, "_run_workspace_setup", lambda **kwargs: asyncio.sleep(0, result={"status": "passed"}))
    monkeypatch.setattr(session_lifecycle, "_build_project_context", lambda *args, **kwargs: asyncio.sleep(0, result=""))

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
