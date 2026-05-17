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
            project={"slug": "workspace-project", "defaultBranch": "main"},
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
    assert dataset_entry["sources"] == ["research_plan/state/sources.json#bls-laus"]
    assert verification_runs[0]["scope"] == "research"


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
    scripts_dir = workspace_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "run-verification.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
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
            "changed": True,
            "files": [{"path": "scripts/run-verification.sh", "changed": True}],
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


def test_relay_terminal_status_uses_session_file_task_id_for_slug_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bootstrap_future_project(tmp_path, name="Relay Task Project")
    session_root = session_files.ensure_session_root(tmp_path, "planner", "sess-relay")
    session_files.update_state(session_root, task_id="repair-verification-automation-for-ontology-ingestion-handoffs")

    updates: list[dict[str, object]] = []
    syncs: list[str] = []

    async def _fake_query(name: str, payload: dict[str, object]):
        assert name == "projects:getById"
        return {
            "_id": payload["projectId"],
            "slug": "relay-task-project",
            "localRepoPath": str(tmp_path),
        }

    async def _update_task(task_id: str, *, project: dict, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id}

    async def _sync(project: dict):
        syncs.append(project["slug"])

    monkeypatch.setattr(session_lifecycle.convex, "query", _fake_query)
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
    assert task_updates[-1]["status"] == "done"


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
    workspace_repo = ResearchIntegrityRepo(workspace_root)
    workspace_repo.write_artifact_lineage(
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
    assert task_updates[-1]["status"] == "done"


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
    assert task_updates[-1]["status"] == "done"


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
    assert task_updates[-1]["status"] == "done"


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
    assert task_updates[-1]["status"] == "done"


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
    assert task_updates[-1]["status"] == "done"


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

    monkeypatch.setattr(running_agent_service, "get_running_agent", _get_running_agent)
    monkeypatch.setattr(running_agent_service, "update_running_agent", _update_running_agent)
    monkeypatch.setattr(session_lifecycle, "resolve_runner_for_project", lambda *args, **kwargs: _FakeRunner())
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
