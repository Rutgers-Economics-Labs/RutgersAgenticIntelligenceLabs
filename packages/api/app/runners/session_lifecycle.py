"""
Runner session lifecycle service.

This module provides the planner-owned runtime bridge for both API-backed and
local CLI-backed workers. Durable session state is mirrored into repo files:

  - research_plan/sessions/<role>/<session-id>/session.ndjson
  - research_plan/sessions/<role>/<session-id>/commands.ndjson
  - research_plan/sessions/<role>/<session-id>/state.json
  - research_plan/sessions/<role>/<session-id>/summary.md

The runtime DB remains a lightweight live-control plane through
``running_agent_service``.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType, TaskPayload
from app.runners.factory import RunnerFactory
from app.services.integrity_service import get_integrity_repo
from app.services import planner_service, running_agent_service, session_files
from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy
from app.services.convex_client import convex
from app.services.integrity_service import evaluate_integrity_gate
from app.services.role_runtime_service import load_role_runtime_config
from rail.manifest import load_manifest


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
STATUS_MAP = {
    RunnerEventType.COMPLETED.value: "completed",
    RunnerEventType.FAILED.value: "failed",
    RunnerEventType.CANCELLED.value: "cancelled",
    RunnerEventType.QUESTION_ASKED.value: "awaiting_input",
    RunnerEventType.APPROVAL_REQUESTED.value: "awaiting_approval",
}
EVENT_TYPE_MAP = {
    RunnerEventType.SESSION_CREATED.value: "session_started",
    RunnerEventType.STATUS_CHANGED.value: "status_changed",
    RunnerEventType.PLAN_PROPOSED.value: "status_changed",
    RunnerEventType.APPROVAL_REQUESTED.value: "approval_requested",
    RunnerEventType.QUESTION_ASKED.value: "question_asked",
    RunnerEventType.PROGRESS.value: "assistant_message",
    RunnerEventType.BASH_COMMAND_STARTED.value: "tool_call",
    RunnerEventType.BASH_COMMAND_COMPLETED.value: "tool_result",
    RunnerEventType.FILE_CHANGE_DETECTED.value: "file_change_detected",
    RunnerEventType.VERIFICATION_STARTED.value: "verification_started",
    RunnerEventType.VERIFICATION_COMPLETED.value: "verification_completed",
    RunnerEventType.COMPLETED.value: "completed",
    RunnerEventType.FAILED.value: "failed",
    RunnerEventType.CANCELLED.value: "cancelled",
}
STATE_INDEX_FILE_NAMES = (
    "assumptions.json",
    "sources.json",
    "claims.json",
    "artifact_lineage.json",
    "verification_runs.json",
)
DATASET_SUFFIXES = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}
ARTIFACT_SUFFIXES = {".md", ".pdf", ".png", ".svg", ".jpg", ".jpeg", ".html", ".htm", ".pptx", ".docx"}


async def resolve_jules_api_key(project_id: str | None, agent_role: str = "data") -> str:
    from app.core.config import settings

    if project_id:
        try:
            from app.services.secret_service import resolve_secrets_for_role

            secrets = await resolve_secrets_for_role(project_id, agent_role)
            project_key = secrets.get("JULES_API_KEY") or ""
            if project_key:
                return project_key
        except Exception:
            pass

    global_key = (settings.jules_api_key or "").strip()
    if not global_key:
        raise RuntimeError(
            "No Jules API key available. Set JULES_API_KEY in the environment "
            "or store it as a project secret named 'JULES_API_KEY'."
        )
    return global_key


def resolve_runner_for_project(runner_name: str = "jules", *, api_key: str | None = None, source: str | None = None) -> Any:
    if runner_name == "jules":
        from app.core.config import settings
        from app.runners.jules import JulesRunner

        if not api_key:
            raise RuntimeError("Jules runner requires an API key")
        return JulesRunner(
            api_key=api_key,
            api_url=settings.jules_api_url,
            source=source or settings.jules_source,
        )

    return RunnerFactory.get(runner_name)


def _project_root(project_record: dict[str, Any]) -> Path | None:
    path = project_record.get("localRepoPath")
    return Path(path).resolve() if path else None


def _scrub_secrets(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: "***REDACTED***" if any(t in str(k).lower() for t in ("key", "secret", "token", "password")) else _scrub_secrets(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_scrub_secrets(item) for item in data]
    return data


def _event_payload(event: RunnerEvent) -> dict[str, Any]:
    payload = _scrub_secrets(dict(event.normalized_payload or {}))
    if payload.get("line"):
        payload.setdefault("content", payload.get("line"))
    if payload.get("message"):
        payload.setdefault("content", payload.get("message"))
    if payload.get("prompt"):
        payload.setdefault("content", payload.get("prompt"))
    if payload.get("command"):
        payload.setdefault("name", "bash")
    payload["runner_event_type"] = event.event_type.value
    payload["debug_visibility"] = event.debug_visibility
    return payload


def _workspace_config(project_root: Path) -> dict[str, Any]:
    try:
        manifest = load_manifest(project_root)
        return manifest.workspaces.model_dump()
    except Exception:
        return {
            "mode": "isolated",
            "root": ".rail/workspaces",
            "setup_script": "scripts/setup-workspace.sh",
            "verification_script": "scripts/run-verification.sh",
            "archive_script": "scripts/archive-workspace.sh",
            "nonconcurrent_run": True,
            "checkpoint_mode": "git-ref",
        }


def _prepare_workspace(project_root: Path, role: str, session_id: str) -> tuple[Path, str, dict[str, Any]]:
    config = _workspace_config(project_root)
    relative_root = config.get("root") or ".rail/workspaces"
    workspace_root = (project_root / relative_root / role / session_id).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    branch = f"{role}-{session_id}"
    return workspace_root, branch, config


def _workspace_env(
    *,
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    session_id: str,
    role: str,
    base_branch: str,
    workspace_branch: str,
) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "RAIL_PROJECT_ROOT": str(project_root),
            "RAIL_WORKSPACE_ROOT": str(workspace_root),
            "RAIL_SESSION_ROOT": str(session_root),
            "RAIL_SESSION_ID": session_id,
            "RAIL_ROLE": role,
            "RAIL_BASE_BRANCH": base_branch,
            "RAIL_WORKSPACE_BRANCH": workspace_branch,
        }
    )
    return env


def _relative_to(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for value in values:
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _copy_workspace_state_indexes(project_root: Path, workspace_root: Path) -> None:
    project_state_root = project_root / "research_plan" / "state"
    workspace_state_root = workspace_root / "research_plan" / "state"
    project_state_root.mkdir(parents=True, exist_ok=True)
    for file_name in STATE_INDEX_FILE_NAMES:
        source = workspace_state_root / file_name
        if not source.exists():
            continue
        target = project_state_root / file_name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _diff_index_keys(
    *,
    project_root: Path,
    workspace_root: Path,
    file_name: str,
    key_field: str,
) -> tuple[list[str], list[str]]:
    before = {
        str(item.get(key_field)): item
        for item in _load_json_array(project_root / "research_plan" / "state" / file_name)
        if item.get(key_field)
    }
    after = {
        str(item.get(key_field)): item
        for item in _load_json_array(workspace_root / "research_plan" / "state" / file_name)
        if item.get(key_field)
    }
    added = [key for key in after if key not in before]
    changed = [key for key, value in after.items() if key in before and before[key] != value]
    return added, changed


async def _list_changed_files(workspace_root: Path) -> list[str]:
    if not (workspace_root / ".git").exists():
        return []
    result = await _run_process(
        ["git", "-C", str(workspace_root), "status", "--short"],
        cwd=workspace_root,
    )
    if result["returncode"] != 0:
        return []
    changed: list[str] = []
    for line in result["stdout"].splitlines():
        if not line.strip():
            continue
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if path:
            candidate = workspace_root / path
            if candidate.is_dir():
                changed.extend(
                    _relative_to(workspace_root, item)
                    for item in candidate.rglob("*")
                    if item.is_file()
                )
            else:
                changed.append(path)
    return changed


def _collect_runner_summary_from_events(session_root: Path, status: str) -> dict[str, Any]:
    merged = session_files.empty_completion_summary(status=status)
    for event in session_files.list_events(session_root):
        for field in ("status", *session_files.COMPLETION_SUMMARY_FIELDS):
            if field not in event:
                continue
            if field == "status":
                merged["status"] = event.get("status") or merged["status"]
                continue
            values = event.get(field)
            if values in (None, "", [], {}):
                continue
            if not isinstance(values, list):
                values = [values]
            merged[field].extend(values)
    for field in session_files.COMPLETION_SUMMARY_FIELDS:
        merged[field] = _dedupe(merged[field])
    return merged


async def _normalize_completion_summary(
    *,
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    session_id: str,
    task_id: str | None,
    status: str,
    role: str,
) -> dict[str, Any]:
    summary = _collect_runner_summary_from_events(session_root, status)
    assumptions_added, assumptions_changed = _diff_index_keys(
        project_root=project_root,
        workspace_root=workspace_root,
        file_name="assumptions.json",
        key_field="assumption_key",
    )
    source_added, source_changed = _diff_index_keys(
        project_root=project_root,
        workspace_root=workspace_root,
        file_name="sources.json",
        key_field="source_key",
    )
    claim_added, _claim_changed = _diff_index_keys(
        project_root=project_root,
        workspace_root=workspace_root,
        file_name="claims.json",
        key_field="claim_key",
    )
    changed_files = await _list_changed_files(workspace_root)
    datasets_created = [
        path
        for path in changed_files
        if Path(path).suffix.lower() in DATASET_SUFFIXES and not path.startswith("research_plan/state/")
    ]
    artifacts_created = [
        path
        for path in changed_files
        if path.startswith("artifacts/") or (Path(path).suffix.lower() in ARTIFACT_SUFFIXES and path.startswith("topics/"))
    ]
    summary["assumptions_added"].extend(assumptions_added)
    summary["assumptions_changed"].extend(assumptions_changed)
    summary["sources_used"].extend(source_added)
    summary["sources_used"].extend(source_changed)
    summary["datasets_created"].extend(datasets_created)
    summary["artifacts_created"].extend(artifacts_created)
    summary["claims_created"].extend(claim_added)

    verification_status = session_files.read_state(session_root).get("verification_status")
    verification_result = {
        "run_id": f"{session_id}-verification",
        "status": "passed" if verification_status == "passed" else "failed" if verification_status == "failed" else "pending",
        "task_id": task_id,
        "agent_session_id": session_id,
        "artifact_paths": _dedupe(artifacts_created + datasets_created),
        "checks": [
            {
                "name": "workspace_verification",
                "status": verification_status or "pending",
                "role": role,
            }
        ],
        "blockers": [],
    }
    if verification_result["status"] == "failed":
        verification_result["blockers"].append("Deterministic verification failed.")
    summary["verification_results"].append(verification_result)
    if verification_result["blockers"]:
        summary["blockers"].extend(verification_result["blockers"])
    if status in {"failed", "cancelled"}:
        summary["blockers"].append(f"Worker session ended with status `{status}`.")
    if verification_result["status"] == "failed":
        summary["recommended_next_tasks"].append("Fix verification failures and rerun the worker task.")
    if summary["open_questions"]:
        summary["recommended_next_tasks"].append("Resolve open research questions before promotion.")

    for field in session_files.COMPLETION_SUMMARY_FIELDS:
        summary[field] = _dedupe(summary[field])
    summary["status"] = status
    return summary


def _sync_completion_summary_to_integrity_indexes(
    *,
    project_root: Path,
    summary: dict[str, Any],
    session_id: str,
    task_id: str | None,
) -> None:
    repo = get_integrity_repo(project_root)
    existing_artifacts = {item.artifact_path for item in repo.load_artifact_lineage()}
    for artifact_path in summary.get("artifacts_created") or []:
        if artifact_path in existing_artifacts:
            continue
        suffix = Path(artifact_path).suffix.lower()
        artifact_type = "dataset" if suffix in DATASET_SUFFIXES else "report" if suffix == ".md" else "artifact"
        repo.upsert_artifact_lineage(
            {
                "artifact_path": artifact_path,
                "artifact_type": artifact_type,
                "title": Path(artifact_path).name,
                "promotion_state": "draft",
                "verification_runs": [f"research_plan/state/verification_runs.json#{session_id}-verification"],
            }
        )
        existing_artifacts.add(artifact_path)
    for dataset_path in summary.get("datasets_created") or []:
        if dataset_path in existing_artifacts:
            continue
        repo.upsert_artifact_lineage(
            {
                "artifact_path": dataset_path,
                "artifact_type": "dataset",
                "title": Path(dataset_path).name,
                "promotion_state": "draft",
                "verification_runs": [f"research_plan/state/verification_runs.json#{session_id}-verification"],
            }
        )
        existing_artifacts.add(dataset_path)
    for result in summary.get("verification_results") or []:
        repo.upsert_verification_run(
            {
                "run_id": result.get("run_id") or f"{session_id}-verification",
                "task_id": task_id,
                "agent_session_id": session_id,
                "status": result.get("status") or "pending",
                "checks": result.get("checks") or [],
                "artifact_paths": result.get("artifact_paths") or [],
                "blockers": result.get("blockers") or [],
            }
        )
        if result.get("status") == "passed":
            repo.clear_artifact_stale(result.get("artifact_paths") or [], promotion_state="partially_verified")


async def _run_process(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        env=env,
        stdout=PIPE,
        stderr=PIPE,
    )
    stdout, stderr = await proc.communicate()
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }


def _tail_output(text: str, limit: int = 1200) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


async def _materialize_workspace(
    *,
    project_root: Path,
    workspace_root: Path,
    base_branch: str,
    workspace_branch: str,
) -> dict[str, Any]:
    if (workspace_root / ".git").exists():
        return {"status": "ready", "mode": "existing"}

    git_dir = project_root / ".git"
    if not git_dir.exists():
        return {"status": "ready", "mode": "directory"}

    result = await _run_process(
        [
            "git",
            "-C",
            str(project_root),
            "worktree",
            "add",
            "--force",
            "-b",
            workspace_branch,
            str(workspace_root),
            base_branch,
        ],
        cwd=project_root,
    )
    if result["returncode"] != 0 and "already exists" in result["stderr"].lower():
        result = await _run_process(
            [
                "git",
                "-C",
                str(project_root),
                "worktree",
                "add",
                "--force",
                str(workspace_root),
                base_branch,
            ],
            cwd=project_root,
        )
    if result["returncode"] != 0:
        raise RuntimeError(result["stderr"].strip() or result["stdout"].strip() or "git worktree add failed")
    return {"status": "ready", "mode": "git-worktree", "stdout": result["stdout"], "stderr": result["stderr"]}


async def _run_workspace_hook(
    *,
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    session_id: str,
    role: str,
    base_branch: str,
    workspace_branch: str,
    script_relative_path: str | None,
    state_prefix: str,
    start_event_type: str,
    complete_event_type: str,
) -> dict[str, Any]:
    if not script_relative_path:
        session_files.update_state(session_root, **{f"{state_prefix}_status": "skipped"})
        session_files.append_event(
            session_root,
            complete_event_type,
            content=f"{state_prefix} skipped: no script configured.",
            status=session_files.read_state(session_root).get("status"),
        )
        return {"status": "skipped", "returncode": 0, "stdout": "", "stderr": ""}

    script_path = (project_root / script_relative_path).resolve()
    if not script_path.exists():
        session_files.update_state(
            session_root,
            **{
                f"{state_prefix}_status": "skipped",
                f"{state_prefix}_script": script_relative_path,
            },
        )
        session_files.append_event(
            session_root,
            complete_event_type,
            content=f"{state_prefix} skipped: `{script_relative_path}` not found.",
            status=session_files.read_state(session_root).get("status"),
        )
        return {"status": "skipped", "returncode": 0, "stdout": "", "stderr": ""}

    session_files.append_event(
        session_root,
        start_event_type,
        content=f"Running `{script_relative_path}`",
        status=session_files.read_state(session_root).get("status"),
    )
    env = _workspace_env(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=session_id,
        role=role,
        base_branch=base_branch,
        workspace_branch=workspace_branch,
    )
    result = await _run_process(["bash", str(script_path)], cwd=workspace_root, env=env)
    status = "passed" if result["returncode"] == 0 else "failed"
    session_files.update_state(
        session_root,
        **{
            f"{state_prefix}_status": status,
            f"{state_prefix}_script": script_relative_path,
            f"{state_prefix}_exit_code": result["returncode"],
            f"{state_prefix}_stdout_tail": _tail_output(result["stdout"]),
            f"{state_prefix}_stderr_tail": _tail_output(result["stderr"]),
        },
    )
    content = result["stderr"].strip() or result["stdout"].strip() or f"{state_prefix} {status}."
    session_files.append_event(
        session_root,
        complete_event_type,
        content=content[:500],
        status=session_files.read_state(session_root).get("status"),
        exit_code=result["returncode"],
    )
    return {"status": status, **result}


async def _run_workspace_setup(
    *,
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    session_id: str,
    role: str,
    base_branch: str,
    workspace_branch: str,
    workspace_config: dict[str, Any],
) -> dict[str, Any]:
    return await _run_workspace_hook(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=session_id,
        role=role,
        base_branch=base_branch,
        workspace_branch=workspace_branch,
        script_relative_path=workspace_config.get("setup_script"),
        state_prefix="setup",
        start_event_type="workspace_setup_started",
        complete_event_type="workspace_setup_completed",
    )


async def _run_workspace_verification(
    *,
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    session_id: str,
    role: str,
    base_branch: str,
    workspace_branch: str,
    workspace_config: dict[str, Any],
) -> dict[str, Any]:
    return await _run_workspace_hook(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=session_id,
        role=role,
        base_branch=base_branch,
        workspace_branch=workspace_branch,
        script_relative_path=workspace_config.get("verification_script"),
        state_prefix="verification",
        start_event_type="verification_started",
        complete_event_type="verification_completed",
    )


async def archive_session_workspace(convex_session_id: str) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")
    session_path = session.get("sessionPath")
    if not session_path:
        raise RuntimeError("Session has no sessionPath")
    session_root = Path(session_path)
    state = session_files.read_state(session_root)
    workspace_path = state.get("workspace_path")
    if not workspace_path:
        raise RuntimeError("Session has no workspace_path")
    project = await _load_project(session.get("projectId"), session.get("projectSlug"))
    project_root = _project_root(project or {})
    if project_root is None:
        raise RuntimeError("Session has no project root")
    workspace_root = Path(workspace_path)
    workspace_branch = state.get("workspace_branch") or session.get("role") or "workspace"
    base_branch = project.get("defaultBranch") if project else "main"
    result = await _run_workspace_hook(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=convex_session_id,
        role=session.get("role") or "agent",
        base_branch=base_branch,
        workspace_branch=workspace_branch,
        script_relative_path=_workspace_config(project_root).get("archive_script"),
        state_prefix="archive",
        start_event_type="workspace_archive_started",
        complete_event_type="workspace_archive_completed",
    )
    session_files.refresh_summary(session_root)
    return result


async def _finalize_workspace_review(
    *,
    convex_session_id: str,
    session: dict[str, Any],
    project_root: Path,
    session_root: Path,
    base_branch: str,
) -> None:
    state = session_files.read_state(session_root)
    workspace_path = state.get("workspace_path")
    if not workspace_path:
        session_files.refresh_summary(session_root)
        return
    workspace_root = Path(workspace_path)
    workspace_branch = state.get("workspace_branch") or f"{session.get('role') or 'agent'}-{convex_session_id}"
    review_status = state.get("review_status") or "pending"
    terminal_status = state.get("status")
    config = _workspace_config(project_root)

    if terminal_status == "completed" and state.get("verification_status") not in {"passed", "failed", "skipped"}:
        verification = await _run_workspace_verification(
            project_root=project_root,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id=convex_session_id,
            role=session.get("role") or "agent",
            base_branch=base_branch,
            workspace_branch=workspace_branch,
            workspace_config=config,
        )
        review_status = "review" if verification["status"] in {"passed", "skipped"} else "needs_changes"
    elif terminal_status in {"failed", "cancelled"}:
        review_status = "needs_changes"

    summary = await _normalize_completion_summary(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=convex_session_id,
        task_id=session.get("taskId"),
        status=terminal_status or "unknown",
        role=session.get("role") or "agent",
    )
    _copy_workspace_state_indexes(project_root, workspace_root)
    _sync_completion_summary_to_integrity_indexes(
        project_root=project_root,
        summary=summary,
        session_id=convex_session_id,
        task_id=session.get("taskId"),
    )
    session_files.update_state(session_root, review_status=review_status)
    session_files.update_state(session_root, completion_summary=summary)
    session_files.refresh_summary(session_root)





def _sync_file_status(root: Path, status: str) -> None:
    session_files.update_state(root, status=status)
    session_files.refresh_summary(root)


async def _load_project(project_id: str | None, project_slug: str | None) -> dict[str, Any] | None:
    if project_id:
        return await convex.query("projects:getById", {"projectId": project_id})
    if project_slug:
        return await convex.query("projects:getBySlug", {"slug": project_slug})
    return None


async def _build_project_context(
    project: dict[str, Any] | None,
    project_root: Path,
    workspace_root: Path,
) -> str:
    """Assemble rich project context for CLI runner prompts.

    Includes: ontology classes, DuckDB schema DDL, data source configs,
    research plan summary, and a shallow repo tree so the agent can
    orient itself without needing additional discovery steps.
    """
    parts: list[str] = [
        "## Platform Tools & Capabilities",
        "- For semantic search across the repository or documents, use `lgrep` via `run_bash`. It is much more effective than keyword-based `grep` or `find` for finding complex patterns and research context.",
        "- The `rail` CLI and package (from the private `rail-py` library) are installed and available. Use `rail search`, `rail query`, and `rail hydrate` via `run_bash` for platform operations.",
        "- Claude Code is also permitted for local assistance when useful. If the `claude` CLI is available, you may use it to inspect, reason about, or implement project work; keep all edits inside the allowed paths for this task.",
        ""
    ]

    if not project:
        return ""

    # 1. Project description
    desc = project.get("description")
    if desc:
        parts.append(f"Project description: {desc}")

    # 2. Ontology classes (from Owlready2 if hydrated)
    try:
        db_path = project.get("activeOntologyDbPath")
        if db_path and Path(db_path).is_file():
            from app.services import ontology_service
            classes = await ontology_service._run(ontology_service.list_classes)
            if classes:
                parts.append(f"Ontology classes: {', '.join(classes[:40])}")
    except Exception:
        pass

    # 3. DuckDB schema DDL (compact)
    try:
        duck_path = project.get("activeOntologyDuckdbPath")
        if duck_path and Path(duck_path).is_file():
            from app.services import sql_service
            sql_service.set_path(duck_path)
            ddl = sql_service.get_schema_ddl()
            if ddl:
                parts.append(f"DuckDB schema:\n{ddl[:2000]}")
    except Exception:
        pass

    # 4. Data source configs (yaml filenames and types)
    sources_dir = project_root / ".ontology" / "sources"
    if sources_dir.is_dir():
        source_files = sorted(sources_dir.glob("*.yaml"))[:20]
        if source_files:
            source_names = [f.stem for f in source_files]
            parts.append(f"Data sources: {', '.join(source_names)}")

    # 5. Pipeline config
    pipelines_dir = project_root / ".ontology" / "pipelines"
    if pipelines_dir.is_dir():
        pipeline_files = sorted(pipelines_dir.glob("*.yaml"))[:5]
        if pipeline_files:
            parts.append(f"Pipelines: {', '.join(f.stem for f in pipeline_files)}")

    # 6. Research plan overview (first 800 chars of current_plan.md)
    plan_path = project_root / "research_plan" / "current_plan.md"
    if plan_path.is_file():
        try:
            plan_text = plan_path.read_text(encoding="utf-8")[:800].strip()
            if plan_text:
                parts.append(f"Research plan:\n{plan_text}")
        except Exception:
            pass

    # 7. Shallow repo tree (workspace, depth 2)
    try:
        tree_lines: list[str] = []
        for child in sorted(workspace_root.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                sub = sorted([f.name for f in child.iterdir() if not f.name.startswith(".")])[:8]
                tree_lines.append(f"  {child.name}/  ({', '.join(sub)}{'…' if len(list(child.iterdir())) > 8 else ''})")
            else:
                tree_lines.append(f"  {child.name}")
        if tree_lines:
            parts.append(f"Repo structure:\n" + "\n".join(tree_lines[:30]))
    except Exception:
        pass

    return "\n\n".join(parts)


async def create_runner_session(
    *,
    project_id: str | None,
    project_slug: str | None,
    task_id: str | None,
    runner_name: str = "jules",
    role: str,
    task_description: str,
    repo_url: str,
    branch: str = "main",
    local_repo_path: str | None = None,
    allowed_paths: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_role_for_secrets: str | None = None,
    policy_approval_granted: bool = False,
) -> dict[str, Any]:
    secret_role = agent_role_for_secrets or role

    if project_id:
        active_worker = await running_agent_service.find_active_worker(project_id)
        if active_worker:
            raise RuntimeError(
                f"Sequential execution enforced: worker session {active_worker['_id']} is still active"
            )

    project = await _load_project(project_id, project_slug)
    project_root = _project_root(project or {})
    if project_root is None and local_repo_path:
        project_root = Path(local_repo_path).resolve()
    if project_root is None:
        raise RuntimeError("Runner sessions require a local repo path")

    if project:
        role_config = load_role_runtime_config(project, role)
        integrity_gate = evaluate_integrity_gate(
            role_config.project_root,
            role_config.manifest,
            action=activity_key_for_role(role_config.role),
        )
        decision = evaluate_autonomy_policy(
            role_config.manifest,
            action=activity_key_for_role(role_config.role),
            write_capable=bool(allowed_paths or role_config.policy.paths.write),
            integrity_blocked=integrity_gate["blocked"],
        )
        if decision.blocked:
            detail = "; ".join(integrity_gate["reasons"]) if integrity_gate["reasons"] else decision.reason
            raise RuntimeError(detail)
        if decision.requires_human_approval and not policy_approval_granted:
            raise PermissionError(decision.reason)

    # Deriving Jules source from repo_url (e.g. sources/github/OWNER/REPO)
    jules_source = None
    if runner_name == "jules":
        from app.core.config import settings
        jules_source = settings.jules_source # Default
        if "github.com/" in repo_url:
            clean_url = repo_url.split("github.com/")[-1].replace(".git", "")
            jules_source = f"sources/github/{clean_url}"

    # Sync to GitHub before launching cloud runner (Jules)
    if runner_name == "jules" and project:
        from app.services import planner_service
        await planner_service.git_sync(project, f"chore: sync for {role} session")

    api_key = await resolve_jules_api_key(project_id, secret_role) if runner_name == "jules" else None
    runner = resolve_runner_for_project(runner_name, api_key=api_key, source=jules_source)
    allowed_secrets: dict[str, str] = {}
    if project_id:
        try:
            from app.services.secret_service import resolve_secrets_for_role

            allowed_secrets = await resolve_secrets_for_role(project_id, secret_role)
        except Exception:
            allowed_secrets = {}

    title = f"[{role}] {task_description[:60]}"
    running_session_id = await running_agent_service.create_running_agent(
        project_id=project_id,
        project_slug=project_slug,
        task_id=task_id,
        runtime_kind=runner_name,
        role=role,
        title=title,
        external_session_id=None,
        session_path=None,
        status="queued",
    )
    session_root = session_files.ensure_session_root(project_root, role, running_session_id)
    workspace_root, workspace_branch, workspace_config = _prepare_workspace(project_root, role, running_session_id)
    materialized = await _materialize_workspace(
        project_root=project_root,
        workspace_root=workspace_root,
        base_branch=branch,
        workspace_branch=workspace_branch,
    )
    session_files.update_state(
        session_root,
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
        diff_path=str(session_root / "diff.md"),
        todos_path=str(session_root / "todos.md"),
        verification_path=str(session_root / "verification.md"),
        checkpoint_mode=workspace_config.get("checkpoint_mode"),
        workspace_materialization=materialized.get("mode"),
    )
    session_files.append_event(
        session_root,
        "session_started",
        content=task_description,
        runner=runner_name,
        role=role,
        task_id=task_id,
        status="queued",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
    )
    setup_result = await _run_workspace_setup(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=running_session_id,
        role=role,
        base_branch=branch,
        workspace_branch=workspace_branch,
        workspace_config=workspace_config,
    )
    if setup_result["status"] == "failed":
        _sync_file_status(session_root, "failed")
        session_files.update_state(session_root, review_status="needs_changes")
        await running_agent_service.update_running_agent(running_session_id, sessionPath=str(session_root))
        await running_agent_service.finalize_running_agent(
            running_session_id,
            status="failed",
            ended_at=int(time.time() * 1000),
        )
        raise RuntimeError(
            setup_result["stderr"].strip()
            or setup_result["stdout"].strip()
            or "Workspace setup failed"
        )
    await running_agent_service.update_running_agent(running_session_id, sessionPath=str(session_root))

    # Build rich project context for CLI runners
    project_context = await _build_project_context(project, project_root, workspace_root)

    task_payload = TaskPayload(
        project_slug=project_slug or (project.get("slug") if project else "unknown"),
        role=role,
        task_id=task_id or running_session_id,
        repo_url=repo_url,
        branch=branch,
        local_repo_path=str(workspace_root),
        task_description=task_description,
        allowed_paths=allowed_paths or [],
        allowed_secrets=allowed_secrets,
        acceptance_criteria=acceptance_criteria or [],
        project_context=project_context,
        session_root=str(session_root),
    )
    try:
        result = await runner.create_session(task_payload)
    except Exception as exc:
        _sync_file_status(session_root, "failed")
        session_files.append_event(
            session_root,
            "failed",
            content=str(exc),
            status="failed",
        )
        session_files.update_state(session_root, review_status="needs_changes")
        await running_agent_service.finalize_running_agent(
            running_session_id,
            status="failed",
            ended_at=int(time.time() * 1000),
        )
        raise RuntimeError(f"Runner session creation failed: {exc}") from exc

    external_id = result["session_id"]
    await running_agent_service.update_running_agent(
        running_session_id,
        status="running",
        externalSessionId=external_id,
    )
    session_files.append_event(
        session_root,
        "status_changed",
        content=f"Worker session started with {runner_name}",
        runner=runner_name,
        external_session_id=external_id,
        status="running",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
    )


    return {
        "convex_session_id": running_session_id,
        "external_session_id": external_id,
        "status": result.get("status", "running"),
        "url": result.get("url"),
        "runner": runner_name,
        "sessionPath": str(session_root),
    }


async def get_runner_session(
    convex_session_id: str,
    *,
    sync_from_runner: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    result: dict[str, Any] = dict(session)
    session_path = session.get("sessionPath")
    root = Path(session_path) if session_path else None
    if root and root.exists():
        result["fileState"] = session_files.read_state(root)
        result["summaryPath"] = str(root / "summary.md")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    if sync_from_runner and external_id:
        try:
            api_key = (
                await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
                if runner_name == "jules"
                else None
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            runner_info = await runner.get_session(external_id)
            normalized = runner_info.get("normalized_status", "")
            new_status = STATUS_MAP.get(normalized, runner_info.get("status", "running"))
            await running_agent_service.update_running_agent(
                convex_session_id,
                status=new_status,
            )
            if root and root.exists():
                _sync_file_status(root, new_status)
            result["runnerInfo"] = runner_info
            result["status"] = new_status
            result["pr_url"] = runner_info.get("pr_url")
        except Exception as exc:
            result["syncError"] = str(exc)
    return result


async def poll_session_until_done(
    convex_session_id: str,
    *,
    project_id: str | None = None,
    max_polls: int = 120,
    poll_interval_seconds: int = 15,
) -> dict[str, Any]:
    for _ in range(max_polls):
        await asyncio.sleep(poll_interval_seconds)
        try:
            await ingest_session_events(convex_session_id, project_id=project_id)
        except Exception:
            pass
        result = await get_runner_session(
            convex_session_id,
            sync_from_runner=True,
            project_id=project_id,
        )
        if result.get("status") in TERMINAL_STATUSES:
            return result

    raise TimeoutError(
        f"Session {convex_session_id} did not complete after {max_polls * poll_interval_seconds}s"
    )


async def cancel_runner_session(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    if external_id:
        try:
            api_key = (
                await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
                if runner_name == "jules"
                else None
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            await runner.cancel(external_id)
        except Exception:
            pass

    session_path = session.get("sessionPath")
    if session_path:
        root = Path(session_path)
        if root.exists():
            session_files.append_event(
                root,
                "cancelled",
                content="Session cancelled by user.",
                status="cancelled",
            )
            _sync_file_status(root, "cancelled")

    await running_agent_service.finalize_running_agent(
        convex_session_id,
        status="cancelled",
        ended_at=int(time.time() * 1000),
    )
    return {"convex_session_id": convex_session_id, "status": "cancelled"}


async def ingest_session_events(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    external_id = session.get("externalSessionId")
    if not external_id:
        return []

    runner_name = session.get("runner", "jules")
    api_key = (
        await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
        if runner_name == "jules"
        else None
    )
    runner = resolve_runner_for_project(runner_name, api_key=api_key)
    events = await runner.list_events(external_id)
    session_path = session.get("sessionPath")
    root = Path(session_path) if session_path else None
    state = session_files.read_state(root) if root and root.exists() else {}
    cursor = int(state.get("runner_event_cursor", 0))
    new_events = events[cursor:]

    ingested: list[dict[str, Any]] = []
    for event in new_events:

        if root and root.exists():
            file_event_type = EVENT_TYPE_MAP.get(event.event_type.value, "status_changed")
            payload = _event_payload(event)
            status = STATUS_MAP.get(event.event_type.value)
            if status:
                payload["status"] = status
            session_files.append_event(root, file_event_type, **payload)
            if status:
                _sync_file_status(root, status)
                if status == "completed":
                    session_files.update_state(root, review_status="review")
                elif status in {"failed", "cancelled"}:
                    session_files.update_state(root, review_status="needs_changes")
        await _relay_runner_event(convex_session_id, session, event)
        ingested.append(
            {
                "event_type": event.event_type.value,
                "debug_visibility": event.debug_visibility,
            }
        )

    if root and root.exists():
        session_files.update_state(root, runner_event_cursor=cursor + len(new_events))
        state = session_files.read_state(root)
        if state.get("status") in TERMINAL_STATUSES:
            project = await _load_project(session.get("projectId"), session.get("projectSlug"))
            project_root = _project_root(project or {})
            if project_root is not None:
                await _finalize_workspace_review(
                    convex_session_id=convex_session_id,
                    session=session,
                    project_root=project_root,
                    session_root=root,
                    base_branch=(project or {}).get("defaultBranch") or "main",
                )
                state = session_files.read_state(root)
            await running_agent_service.finalize_running_agent(
                convex_session_id,
                status=state["status"],
                ended_at=int(time.time() * 1000),
            )

    return ingested


async def append_session_command(
    convex_session_id: str,
    *,
    command_type: str,
    content: str | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")
    session_path = session.get("sessionPath")
    if not session_path:
        raise RuntimeError("Session has no sessionPath")
    root = Path(session_path)
    command = session_files.append_command(
        root,
        command_type,
        content=content,
        payload=payload or {},
        idempotency_key=idempotency_key,
    )
    if command.get("processed") or command.get("duplicate"):
        return command
    external_id = session.get("externalSessionId")
    if external_id:
        runner_name = session.get("runner", "jules")
        api_key = (
            await resolve_jules_api_key(session.get("projectId"), session.get("role") or "data")
            if runner_name == "jules"
            else None
        )
        runner = resolve_runner_for_project(runner_name, api_key=api_key)
        if command_type == "inject_message" and content:
            await runner.send_message(external_id, content)
        elif command_type == "approve":
            await runner.approve(external_id, payload or {"message": content or "approved"})
        elif command_type == "cancel":
            await runner.cancel(external_id)
        session_files.mark_command_processed(root, int(command["id"]))
    return command


async def _relay_runner_event(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    if event.event_type == RunnerEventType.APPROVAL_REQUESTED:
        await _relay_approval_requested(convex_session_id, session_record, event)
    elif event.event_type == RunnerEventType.QUESTION_ASKED:
        await _relay_question_asked(convex_session_id, session_record, event)
    elif event.event_type in {RunnerEventType.COMPLETED, RunnerEventType.FAILED, RunnerEventType.CANCELLED}:
        await _relay_terminal_status(session_record, event)


async def _relay_approval_requested(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    project_id = session_record.get("projectId")
    if not project_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return

    existing = await planner_service.list_approvals(project)
    for approval in existing:
        if approval.get("agentSessionId") == convex_session_id and approval.get("status") == "pending":
            return

    await planner_service.create_approval(
        project=project,
        task_id=session_record.get("taskId"),
        agent_session_id=convex_session_id,
        approval_type=event.normalized_payload.get("activity_key") or "run_task",
        status="pending",
        requested_by_role=session_record.get("role") or "agent",
        resolution_note=event.normalized_payload.get("prompt") or event.normalized_payload.get("message"),
    )
    await planner_service.sync_planner_files(project)


async def _relay_question_asked(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    project_id = session_record.get("projectId")
    if not project_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return
    question_text = (
        event.normalized_payload.get("prompt")
        or event.normalized_payload.get("message")
        or "The agent has a question."
    )
    await planner_service.append_planner_message(
        project=project,
        role="assistant",
        content=f"[Question from {session_record.get('role') or 'agent'}] {question_text}",
        message_type="question",
        session_id=convex_session_id,
    )
    from app.services.decision_service import raise_decision_event

    await raise_decision_event(
        project,
        source="runner",
        event_type="awaiting_input",
        severity="needs_planner",
        summary=f"Worker {convex_session_id} asked for input: {question_text}",
        evidence_refs=[f"runner_session:{convex_session_id}"],
        recommended_actions=[
            "Answer worker if policy-safe",
            "Ask user for sensitive or ambiguous input",
            "Cancel or reroute worker",
        ],
    )


async def _relay_terminal_status(session_record: dict[str, Any], event: RunnerEvent) -> None:
    project_id = session_record.get("projectId")
    task_id = session_record.get("taskId")
    if not project_id or not task_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return
    status = STATUS_MAP.get(event.event_type.value, "done")
    task_status = {
        "completed": "review",
        "failed": "blocked",
        "cancelled": "cancelled",
    }.get(status, "review")
    summary = (
        event.normalized_payload.get("message")
        or event.normalized_payload.get("stderr")
        or f"Session ended with status {status}."
    )
    await planner_service.update_task(
        str(task_id),
        project=project,
        status=task_status,
        latestRunSummary=summary,
    )
    if status in {"failed", "cancelled"}:
        from app.services.decision_service import raise_decision_event

        await raise_decision_event(
            project,
            source="runner",
            event_type=f"task_{status}",
            severity="needs_planner",
            summary=f"Worker for task {task_id} ended with status {status}: {summary}",
            evidence_refs=[f"task:{task_id}"],
            recommended_actions=[
                "Diagnose run output",
                "Requeue task if still required",
                "Ask user before changing methodology",
            ],
        )
    await planner_service.sync_planner_files(project)

async def flush_live_events(session_root: Path) -> None:
    """
    Flushes any pending live events and refreshes the summary.
    Live planners write directly via session_files.append_event, so this mainly 
    ensures the summary.md is up to date with the latest appended NDJSON lines.
    """
    if session_root.exists():
        session_files.refresh_summary(session_root)

async def process_pending_commands(session_root: Path) -> list[dict]:
    """
    Reads pending commands from commands.ndjson, processes them, and marks them as processed exactly once.
    """
    if not session_root.exists():
        return []
        
    commands = session_files.list_commands(session_root)
    processed = []
    
    for cmd in commands:
        if not cmd.get("processed"):
            session_files.mark_command_processed(session_root, cmd["id"])
            processed.append(cmd)
            
    if processed:
        session_files.refresh_summary(session_root)
        
    return processed
