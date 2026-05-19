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
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType, TaskPayload
from app.runners.cli_base import LocalCLIRunner, runner_runtime_paths
from app.runners.factory import RunnerFactory
from app.services.audit_service import write_post_run_audit
from app.services.integrity_service import get_integrity_repo
from app.services import planner_service, running_agent_service, session_files
from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy
from app.services.convex_client import convex
from app.services.decision_service import raise_decision_event
from app.services import hydration_registry_service, project_artifacts_service
from app.services.integrity_service import evaluate_integrity_gate, summarize_agent_workflow_health
from app.services.repo_contract_service import infer_github_repo
from app.services.role_runtime_service import load_role_runtime_config
from app.services.safe_publish_service import (
    is_repo_publish_path_allowed,
    publish_repo_files,
    record_publish_failure,
    record_publish_success,
)
from rail.manifest import load_manifest
from rail.integrity import sync_sources_from_configs


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


def _should_retry_post_publish_verification(state: dict[str, Any]) -> bool:
    return (
        state.get("status") in TERMINAL_STATUSES
        and state.get("publish_status") == "published"
        and state.get("verification_status") == "failed"
    )


def _should_retry_workflow_contract_review(state: dict[str, Any]) -> bool:
    blockers = state.get("completion_summary", {}).get("blockers") or []
    return (
        state.get("status") in TERMINAL_STATUSES
        and state.get("publish_status") == "published"
        and state.get("verification_status") == "passed"
        and state.get("review_status") == "needs_changes"
        and any("Role workflow contract failed" in str(item) for item in blockers)
    )


def _should_retry_stale_review_status(state: dict[str, Any]) -> bool:
    blockers = state.get("completion_summary", {}).get("blockers") or []
    return (
        state.get("status") in TERMINAL_STATUSES
        and state.get("publish_status") == "published"
        and state.get("verification_status") in {"passed", "skipped"}
        and state.get("review_status") == "needs_changes"
        and not blockers
    )


def _should_retry_false_publish_failure(state: dict[str, Any]) -> bool:
    return (
        state.get("status") in TERMINAL_STATUSES
        and state.get("publish_status") == "failed"
        and bool(state.get("publish_commit_sha"))
        and state.get("verification_status") in {"passed", "skipped"}
        and state.get("review_status") == "needs_changes"
    )


def _runner_launch_blocked_by_auditors(
    role: str,
    task_description: str,
    auditors: dict[str, Any] | None,
) -> str | None:
    auditors = auditors or {}
    session_auditor = auditors.get("session") or {}
    planner_auditor = auditors.get("planner") or {}
    ontology_auditor = auditors.get("ontology") or {}
    integrity_auditor = auditors.get("integrity") or {}

    for auditor in (session_auditor, planner_auditor):
        if auditor.get("status") == "blocked":
            blockers = [str(item) for item in (auditor.get("blockers") or []) if item]
            if blockers:
                return blockers[0]

    role_name = str(role or "").strip().lower()
    description = str(task_description or "").strip().lower()

    if ontology_auditor.get("status") == "blocked":
        if role_name not in {"planner", "data", "health"}:
            blockers = [str(item) for item in (ontology_auditor.get("blockers") or []) if item]
            return blockers[0] if blockers else "Ontology auditor blocked this launch."

    if integrity_auditor.get("status") == "blocked":
        allowed_roles = {"planner", "health", "data", "coding"}
        if role_name not in allowed_roles and not any(
            token in description for token in ("verify", "evidence", "source", "provenance", "claim")
        ):
            blockers = [str(item) for item in (integrity_auditor.get("blockers") or []) if item]
            return blockers[0] if blockers else "Integrity auditor blocked this launch."

    # Planner drift suppression: block the planner role from creating more tasks
    # when the task graph is already saturated with open work.
    saturation_count = int(planner_auditor.get("taskSaturationCount") or 0)
    if saturation_count > 0 and role_name == "planner":
        return (
            f"Planner task graph saturated: {saturation_count} open task(s) already exceed the "
            f"saturation threshold. Resolve or cancel existing work before creating new tasks."
        )

    return None
STATE_INDEX_FILE_NAMES = (
    "assumptions.json",
    "sources.json",
    "claims.json",
    "source_candidates.json",
    "claim_candidates.json",
    "entity_candidates.json",
    "conflicts.json",
    "artifact_lineage.json",
    "verification_runs.json",
)
MERGED_STATE_INDEX_FILE_NAMES = {"artifact_lineage.json", "verification_runs.json"}
DATASET_SUFFIXES = {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}
ARTIFACT_SUFFIXES = {".md", ".pdf", ".png", ".svg", ".jpg", ".jpeg", ".html", ".htm", ".pptx", ".docx"}
SCRIPT_LINEAGE_SUFFIXES = {".py", ".sh", ".sql", ".ipynb", ".r", ".js", ".ts", ".tsx", ".jsx"}
_VERIFICATION_PATH_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:ya?ml|csv|tsv|jsonl?|parquet|xlsx?|md|pdf|png|svg|jpe?g|html?|py|sh))")
LOCAL_CLI_RUNNERS = {"claude_code", "codex_cli", "gemini_cli", "cursor_cli", "copilot_cli"}
ALLOWED_RUNNER_NAMES = LOCAL_CLI_RUNNERS | {"default", "jules"}
INTERNAL_WORKFLOW_DATASET_PATHS = {"ontology/.rail_hydration.json"}


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


def _normalize_runner_name_for_project(
    runner_name: str | None,
    *,
    role_config: Any | None = None,
) -> str:
    normalized = (runner_name or "").strip().lower()
    if normalized and normalized not in ALLOWED_RUNNER_NAMES:
        raise ValueError(f"Unsupported runner name: {runner_name}")
    if normalized and normalized != "default":
        return normalized
    if role_config is not None:
        default_runner = getattr(getattr(role_config, "policy", None), "runner", None)
        default_name = getattr(default_runner, "default", None)
        if default_name:
            normalized_default = str(default_name).strip().lower()
            if normalized_default not in ALLOWED_RUNNER_NAMES - {"default"}:
                raise ValueError(f"Unsupported default runner in role policy: {default_name}")
            return normalized_default
        manifest_default = getattr(getattr(role_config, "manifest", None), "agents", None)
        manifest_name = getattr(manifest_default, "default_runner", None)
        if manifest_name:
            normalized_manifest = str(manifest_name).strip().lower()
            if normalized_manifest not in ALLOWED_RUNNER_NAMES - {"default"}:
                raise ValueError(f"Unsupported default runner in manifest: {manifest_name}")
            return normalized_manifest
    return "jules"


def _project_root(project_record: dict[str, Any]) -> Path | None:
    path = project_record.get("localRepoPath")
    return Path(path).resolve() if path else None


def _resolve_session_root_path(
    session: dict[str, Any],
    *,
    project_root: Path | None = None,
) -> Path | None:
    session_path = session.get("sessionPath")
    if session_path:
        candidate = Path(session_path)
        if candidate.exists():
            return candidate

    session_id = session.get("_id") or session.get("sessionId")
    role = session.get("role")
    if project_root is None or not session_id:
        return None

    if role:
        candidate = session_files.session_root(project_root, role, session_id)
        if candidate.exists():
            return candidate

    sessions_root = project_root / "research_plan" / "sessions"
    if sessions_root.exists():
        for candidate in sessions_root.glob(f"*/{session_id}"):
            if candidate.exists():
                return candidate
    return None


def _session_task_id(session: dict[str, Any], session_root: Path | None = None) -> str | None:
    task_id = session.get("taskId")
    if task_id:
        return str(task_id)
    if session_root and session_root.exists():
        state = session_files.read_state(session_root)
        fallback = state.get("task_id")
        if fallback:
            return str(fallback)
    return None


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


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None


def _path_in_scopes(path_text: str, scopes: list[str]) -> bool:
    normalized = path_text.strip().lstrip("./")
    if not normalized:
        return False
    for scope in scopes:
        candidate = str(scope or "").strip().lstrip("./").rstrip("/")
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(f"{candidate}/"):
            return True
    return False


def _verification_failure_paths(state: dict[str, Any]) -> list[str]:
    text = "\n".join(
        str(part or "")
        for part in (
            state.get("verification_stdout_tail"),
            state.get("verification_stderr_tail"),
        )
    )
    if not text:
        return []
    matches = [match.strip().lstrip("./") for match in _VERIFICATION_PATH_RE.findall(text)]
    return _dedupe([match for match in matches if match])


def _verification_failures_outside_task_scope(
    *,
    state: dict[str, Any],
    task: dict[str, Any] | None,
    changed_files: list[str],
) -> bool:
    paths = _verification_failure_paths(state)
    if not paths:
        return False
    scopes = [str(item) for item in (task or {}).get("repoPaths") or [] if item]
    if not scopes:
        return False
    changed = [str(item).strip().lstrip("./") for item in changed_files if item]
    for path_text in paths:
        if _path_in_scopes(path_text, scopes):
            return False
        if changed and path_text in changed:
            return False
    return True


def _relevant_workflow_blockers(
    *,
    role_health: dict[str, Any],
    changed_files: list[str],
    summary: dict[str, Any],
) -> list[str]:
    relevant_paths = {
        str(item).strip().lstrip("./")
        for item in (
            list(changed_files)
            + list(summary.get("datasets_created") or [])
            + list(summary.get("artifacts_created") or [])
        )
        if item
        and str(item).strip().lstrip("./") not in INTERNAL_WORKFLOW_DATASET_PATHS
    }
    blocker_bits: list[str] = []
    for key, value in role_health.items():
        if key in {"status", "requirements"}:
            continue
        if isinstance(value, list):
            relevant_items = [
                str(item)
                for item in value
                if str(item).strip().lstrip("./") in relevant_paths
                and str(item).strip().lstrip("./") not in INTERNAL_WORKFLOW_DATASET_PATHS
            ]
            if relevant_items:
                blocker_bits.append(f"{key}: {', '.join(relevant_items)}")
        elif value:
            blocker_bits.append(f"{key}: {value}")
    return blocker_bits


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
        if file_name in MERGED_STATE_INDEX_FILE_NAMES:
            continue
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


def _copy_workspace_files_to_project(
    *,
    project_root: Path,
    workspace_root: Path,
    relative_paths: list[str],
    allowed_paths: list[str] | None = None,
) -> list[str]:
    copied: list[str] = []
    for relative_path in relative_paths:
        if not is_repo_publish_path_allowed(relative_path, allowed_paths=allowed_paths):
            continue
        source = (workspace_root / relative_path).resolve()
        if not source.exists() or not source.is_file():
            continue
        try:
            source.relative_to(workspace_root.resolve())
        except ValueError:
            continue
        target = (project_root / relative_path).resolve()
        try:
            target.relative_to(project_root.resolve())
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied.append(relative_path)
    return copied


async def _maybe_register_workspace_hydration_artifact(
    *,
    project: dict[str, Any],
    project_root: Path,
    session_root: Path,
    changed_files: list[str],
    role: str,
) -> None:
    if role != "data":
        return
    interesting = {".ontology/onto.duckdb", ".ontology/.rail_hydration.json", ".ontology/onto.db"}
    if not any(path in interesting for path in changed_files):
        return
    duckdb_path = project_root / ".ontology" / "onto.duckdb"
    hydration_meta_path = project_root / ".ontology" / ".rail_hydration.json"
    ontology_db_path = project_root / ".ontology" / "onto.db"
    if not duckdb_path.exists() or not hydration_meta_path.exists():
        return

    try:
        raw_meta = json.loads(hydration_meta_path.read_text(encoding="utf-8"))
    except Exception:
        raw_meta = {}

    from app.services.hydration_registry_service import (
        promote_project_hydration_artifact,
        register_hydration_artifact,
    )

    project_doc = dict(project)
    project_doc.setdefault("localRepoPath", str(project_root))
    project_doc.setdefault("manifestPath", "rail.yaml")
    if not project_doc.get("_id"):
        return

    artifact_id = await register_hydration_artifact(
        project=project_doc,
        pipeline_slug=str(raw_meta.get("pipeline_slug") or "default"),
        hydration_mode=str(raw_meta.get("hydration_mode") or "full"),
        ontology_artifact_path=str(ontology_db_path) if ontology_db_path.exists() else None,
        duckdb_artifact_path=str(duckdb_path),
        status="valid",
    )
    await promote_project_hydration_artifact(
        project=project_doc,
        ontology_artifact_path=str(ontology_db_path) if ontology_db_path.exists() else None,
        duckdb_artifact_path=str(duckdb_path),
    )
    session_files.append_event(
        session_root,
        "hydration_artifact_registered",
        content=f"Registered local hydration artifact {artifact_id} for this device and promoted it as the active project ontology.",
        status=session_files.read_state(session_root).get("status"),
    )


async def _task_record(project: dict[str, Any], task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    for task in tasks:
        if str(task.get("_id")) == str(task_id):
            return task
    return None


async def _publish_completed_session_outputs(
    *,
    project: dict[str, Any],
    session: dict[str, Any],
    project_root: Path,
    workspace_root: Path,
    session_root: Path,
    changed_files: list[str],
) -> dict[str, Any]:
    if not infer_github_repo(project.get("github") or project.get("gitRepoUrl")):
        session_files.update_state(
            session_root,
            publish_status="skipped",
            publish_strategy="github_app_commit",
            publish_branch=project.get("defaultBranch") or "main",
            publish_error="",
        )
        session_files.append_event(
            session_root,
            "publish_completed",
            content="Connector publish skipped because the project is not linked to a GitHub repository.",
            status=session_files.read_state(session_root).get("status"),
        )
        return {
            "published": False,
            "strategy": "github_app_commit",
            "commit_sha": None,
            "branch": project.get("defaultBranch") or "main",
            "changed": False,
            "files": [],
            "skipped_files": changed_files,
        }
    task = await _task_record(project, _session_task_id(session, session_root))
    allowed_paths = (task or {}).get("repoPaths") or None
    mirrored = _copy_workspace_files_to_project(
        project_root=project_root,
        workspace_root=workspace_root,
        relative_paths=changed_files,
        allowed_paths=allowed_paths,
    )
    await _maybe_register_workspace_hydration_artifact(
        project=project,
        project_root=project_root,
        session_root=session_root,
        changed_files=mirrored,
        role=session.get("role") or "agent",
    )
    commit_message = (
        f"chore({session.get('role') or 'agent'}): publish task {session.get('taskId') or session.get('title') or 'session outputs'}"
    )
    result = await publish_repo_files(
        project,
        repo_root=project_root,
        changed_paths=mirrored,
        commit_message=commit_message,
        allowed_paths=allowed_paths,
    )
    session_files.update_state(
        session_root,
        publish_status="published" if result.get("published") else "skipped",
        publish_strategy=result.get("strategy") or "github_app_commit",
        publish_branch=result.get("branch"),
        publish_commit_sha=result.get("commit_sha"),
        publish_changed_files=[item.get("path") for item in result.get("files") or [] if item.get("path")],
        publish_skipped_files=result.get("skipped_files") or [],
        publish_error="",
    )
    session_files.append_event(
        session_root,
        "publish_completed",
        content=(
            f"Connector publish {'updated' if result.get('changed') else 'checked'} "
            f"{len(result.get('files') or [])} file(s) on `{result.get('branch')}`."
        ),
        commit_sha=result.get("commit_sha"),
        branch=result.get("branch"),
        status=session_files.read_state(session_root).get("status"),
    )
    if project.get("_id"):
        await record_publish_success(project["_id"], result)
    return result


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
        "scope": role,
        "loop_type": "analysis_reproducibility",
        "status": "passed" if verification_status == "passed" else "failed" if verification_status == "failed" else "pending",
        "task_id": task_id,
        "agent_session_id": session_id,
        "artifacts_checked": _dedupe(artifacts_created + datasets_created),
        "claims_checked": _dedupe(claim_added),
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
    workspace_root: Path,
    summary: dict[str, Any],
    session_id: str,
    task_id: str | None,
    role: str | None = None,
    verification_command: str | None = None,
    changed_files: list[str] | None = None,
) -> None:
    repo = get_integrity_repo(project_root)
    existing_artifact_index = {item.artifact_path: item for item in repo.load_artifact_lineage()}
    workspace_repo = get_integrity_repo(workspace_root)
    workspace_artifact_index = {item.artifact_path: item for item in workspace_repo.load_artifact_lineage()}
    changed_files = [path for path in (changed_files or []) if not path.startswith("research_plan/state/")]
    script_candidates = sorted(
        {
            path
            for path in changed_files
            if Path(path).suffix.lower() in SCRIPT_LINEAGE_SUFFIXES
        }
    )
    changed_source_keys = sorted(
        {
            Path(path).stem
            for path in changed_files
            if path.startswith(".ontology/sources/") and Path(path).suffix.lower() in {".yaml", ".yml"}
        }
    )
    synced_sources = (
        sync_sources_from_configs(project_root, sources_dir=".ontology/sources", source_keys=changed_source_keys)
        if changed_source_keys
        else []
    )
    source_refs = [
        f"research_plan/state/sources.json#{source_key}"
        for source_key in (summary.get("sources_used") or [])
    ]
    source_refs = _dedupe(
        source_refs
        + [f"research_plan/state/sources.json#{source.source_key}" for source in synced_sources]
    )
    assumption_refs = [
        f"research_plan/state/assumptions.json#{assumption_key}"
        for assumption_key in (summary.get("assumptions_added") or [])
    ]
    claim_refs = [
        f"research_plan/state/claims.json#{claim_key}"
        for claim_key in (summary.get("claims_created") or [])
    ]
    for artifact_path in summary.get("artifacts_created") or []:
        suffix = Path(artifact_path).suffix.lower()
        artifact_type = "dataset" if suffix in DATASET_SUFFIXES else "report" if suffix == ".md" else "artifact"
        existing_lineage = existing_artifact_index.get(artifact_path)
        workspace_lineage = workspace_artifact_index.get(artifact_path)
        inferred_inputs = sorted(
            {
                path
                for path in changed_files
                if path != artifact_path and path not in (summary.get("datasets_created") or [])
            }
        )
        inferred_scripts = sorted(
            {
                path
                for path in script_candidates
                if path == artifact_path or path.startswith(f"{Path(artifact_path).parent.as_posix()}/")
            }
        )
        inputs = (
            list(workspace_lineage.inputs)
            if workspace_lineage and workspace_lineage.inputs
            else list(existing_lineage.inputs)
            if existing_lineage and existing_lineage.inputs
            else inferred_inputs
        )
        scripts = (
            list(workspace_lineage.scripts)
            if workspace_lineage and workspace_lineage.scripts
            else list(existing_lineage.scripts)
            if existing_lineage and existing_lineage.scripts
            else inferred_scripts
        )
        verification_commands = (
            list(workspace_lineage.verification_commands)
            if workspace_lineage is not None
            else list(existing_lineage.verification_commands)
            if existing_lineage and existing_lineage.verification_commands
            else [verification_command] if verification_command and artifact_type != "dataset" else []
        )
        sources = (
            list(workspace_lineage.sources)
            if workspace_lineage is not None
            else list(existing_lineage.sources)
            if existing_lineage and existing_lineage.sources
            else source_refs
        )
        assumptions = (
            list(workspace_lineage.assumptions)
            if workspace_lineage is not None
            else list(existing_lineage.assumptions)
            if existing_lineage and existing_lineage.assumptions
            else assumption_refs
        )
        claims = (
            list(workspace_lineage.claims)
            if workspace_lineage is not None
            else list(existing_lineage.claims)
            if existing_lineage and existing_lineage.claims
            else claim_refs
        )
        verification_runs = (
            list(workspace_lineage.verification_runs)
            if workspace_lineage is not None
            else list(existing_lineage.verification_runs)
            if existing_lineage and existing_lineage.verification_runs
            else [f"research_plan/state/verification_runs.json#{session_id}-verification"]
        )
        repo.upsert_artifact_lineage(
            {
                "artifact_path": artifact_path,
                "artifact_type": artifact_type,
                "title": Path(artifact_path).name,
                "promotion_state": (
                    existing_lineage.promotion_state
                    if existing_lineage and existing_lineage.promotion_state != "draft"
                    else "draft"
                ),
                "reproducibility_mode": (
                    workspace_lineage.reproducibility_mode
                    if workspace_lineage and workspace_lineage.reproducibility_mode is not None
                    else existing_lineage.reproducibility_mode
                    if existing_lineage
                    else None
                ),
                "inputs": inputs,
                "scripts": scripts,
                "verification_commands": verification_commands,
                "sources": sources,
                "assumptions": assumptions,
                "claims": claims,
                "verification_runs": verification_runs,
            }
        )
        existing_artifact_index[artifact_path] = next(
            item for item in repo.load_artifact_lineage() if item.artifact_path == artifact_path
        )
    for dataset_path in summary.get("datasets_created") or []:
        existing_lineage = existing_artifact_index.get(dataset_path)
        workspace_lineage = workspace_artifact_index.get(dataset_path)
        inferred_scripts = sorted(
            {
                path
                for path in script_candidates
                if path == dataset_path or path.startswith(f"{Path(dataset_path).parent.as_posix()}/")
            }
        )
        repo.upsert_artifact_lineage(
            {
                "artifact_path": dataset_path,
                "artifact_type": "dataset",
                "title": Path(dataset_path).name,
                "promotion_state": (
                    existing_lineage.promotion_state
                    if existing_lineage and existing_lineage.promotion_state != "draft"
                    else "draft"
                ),
                "inputs": (
                    list(workspace_lineage.inputs)
                    if workspace_lineage and workspace_lineage.inputs
                    else list(existing_lineage.inputs)
                    if existing_lineage and existing_lineage.inputs
                    else source_refs
                ),
                "scripts": (
                    list(workspace_lineage.scripts)
                    if workspace_lineage and workspace_lineage.scripts
                    else list(existing_lineage.scripts)
                    if existing_lineage and existing_lineage.scripts
                    else inferred_scripts
                ),
                "verification_commands": (
                    list(workspace_lineage.verification_commands)
                    if workspace_lineage and workspace_lineage.verification_commands
                    else list(existing_lineage.verification_commands)
                    if existing_lineage and existing_lineage.verification_commands
                    else [verification_command] if verification_command else []
                ),
                "sources": (
                    list(workspace_lineage.sources)
                    if workspace_lineage and workspace_lineage.sources
                    else list(existing_lineage.sources)
                    if existing_lineage and existing_lineage.sources
                    else source_refs
                ),
                "assumptions": (
                    list(workspace_lineage.assumptions)
                    if workspace_lineage and workspace_lineage.assumptions
                    else list(existing_lineage.assumptions)
                    if existing_lineage and existing_lineage.assumptions
                    else assumption_refs
                ),
                "claims": (
                    list(workspace_lineage.claims)
                    if workspace_lineage and workspace_lineage.claims
                    else list(existing_lineage.claims)
                    if existing_lineage and existing_lineage.claims
                    else claim_refs
                ),
                "verification_runs": sorted(
                    {
                        *(
                            list(existing_lineage.verification_runs)
                            if existing_lineage and existing_lineage.verification_runs
                            else []
                        ),
                        f"research_plan/state/verification_runs.json#{session_id}-verification",
                    }
                ),
            }
        )
        existing_artifact_index[dataset_path] = next(
            item for item in repo.load_artifact_lineage() if item.artifact_path == dataset_path
        )
    for result in summary.get("verification_results") or []:
        repo.upsert_verification_run(
            {
                "run_id": result.get("run_id") or f"{session_id}-verification",
                "scope": result.get("scope") or role,
                "loop_type": result.get("loop_type") or "analysis_reproducibility",
                "task_id": task_id,
                "agent_session_id": session_id,
                "status": result.get("status") or "pending",
                "checks": result.get("checks") or [],
                "artifacts_checked": result.get("artifacts_checked") or result.get("artifact_paths") or [],
                "claims_checked": result.get("claims_checked") or [],
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


async def _ensure_workspace_rail_cli(project_root: Path, workspace_root: Path) -> dict[str, Any]:
    local_package = (project_root / ".." / ".." / "packages" / "rail-py").resolve()
    if local_package.is_dir():
        return await _run_process(["pip", "install", "--quiet", "-e", str(local_package)], cwd=workspace_root)
    return await _run_process(
        [
            "pip",
            "install",
            "--quiet",
            "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/rail-py",
        ],
        cwd=workspace_root,
    )


def _find_file_backed_session_root(project_root: Path | None, session_id: str) -> Path | None:
    if project_root is None:
        return None
    sessions_root = project_root / "research_plan" / "sessions"
    if not sessions_root.exists():
        return None
    for candidate in sessions_root.glob(f"*/{session_id}"):
        if candidate.exists():
            return candidate
    return None


def _process_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        state = subprocess.run(
            ["ps", "-o", "state=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if state.startswith("Z"):
            return False
    except Exception:
        pass
    return True


def _read_log_delta(path: Path, offset: int) -> tuple[int, list[str]]:
    if not path.exists():
        return offset, []
    with path.open("rb") as handle:
        handle.seek(max(offset, 0))
        chunk = handle.read()
        new_offset = handle.tell()
    if not chunk:
        return new_offset, []
    text = chunk.decode("utf-8", errors="replace")
    lines = [line.rstrip("\n") for line in text.splitlines()]
    return new_offset, lines


def _read_exit_code(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return 1


async def _repair_stale_running_agents_for_project(
    project: dict[str, Any],
    active_sessions: list[dict[str, Any]],
    *,
    project_root: Path | None,
) -> list[dict[str, Any]]:
    if project_root is None or not project_root.exists():
        return active_sessions

    surviving: list[dict[str, Any]] = []
    for active_session in active_sessions:
        session_root = _resolve_session_root_path(active_session, project_root=project_root)
        if session_root is None or not session_root.exists():
            surviving.append(active_session)
            continue
        state = session_files.read_state(session_root)
        status = str(state.get("status") or "")
        if status not in TERMINAL_STATUSES:
            surviving.append(active_session)
            continue
        await running_agent_service.finalize_running_agent(
            str(active_session["_id"]),
            status=status,
            ended_at=int(time.time() * 1000),
        )
    return surviving


async def _ingest_local_cli_runner_events(
    *,
    convex_session_id: str,
    session: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    state = session_files.read_state(root)
    runtime = runner_runtime_paths(str(root))
    runner_name = session.get("runner", "codex_cli")
    runner = resolve_runner_for_project(runner_name)
    if not isinstance(runner, LocalCLIRunner):
        raise RuntimeError(f"Runner {runner_name} is not a local CLI runner")

    external_id = session.get("externalSessionId") or state.get("external_session_id") or convex_session_id
    stdout_offset = int(state.get("runner_stdout_offset") or 0)
    stderr_offset = int(state.get("runner_stderr_offset") or 0)
    new_stdout_offset, stdout_lines = _read_log_delta(runtime["stdout"], stdout_offset)
    new_stderr_offset, stderr_lines = _read_log_delta(runtime["stderr"], stderr_offset)

    for text in stdout_lines:
        progress = RunnerEvent(
            event_type=RunnerEventType.PROGRESS,
            session_id=str(external_id),
            normalized_payload={"stream": "stdout", "line": text},
            raw_payload={"line": text},
            debug_visibility=False,
        )
        session_files.append_event(
            root,
            "assistant_message",
            content=text,
            stream="stdout",
            line=text,
            runner_event_type=progress.event_type.value,
            debug_visibility=progress.debug_visibility,
        )
        await _relay_runner_event(convex_session_id, session, progress)
        for event in runner._derived_events_from_stdout_line(str(external_id), text):
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

    for text in stderr_lines:
        progress = RunnerEvent(
            event_type=RunnerEventType.PROGRESS,
            session_id=str(external_id),
            normalized_payload={"stream": "stderr", "line": text},
            raw_payload={"line": text},
            debug_visibility=False,
        )
        session_files.append_event(
            root,
            "assistant_message",
            content=text,
            stream="stderr",
            line=text,
            runner_event_type=progress.event_type.value,
            debug_visibility=progress.debug_visibility,
        )
        await _relay_runner_event(convex_session_id, session, progress)

    session_files.update_state(
        root,
        runner_stdout_offset=new_stdout_offset,
        runner_stderr_offset=new_stderr_offset,
    )

    state = session_files.read_state(root)
    returncode = _read_exit_code(runtime["exit_code"])
    if state.get("status") not in TERMINAL_STATUSES and returncode is not None:
        completion = RunnerEvent(
            event_type=RunnerEventType.BASH_COMMAND_COMPLETED,
            session_id=str(external_id),
            normalized_payload={"returncode": returncode},
        )
        terminal = RunnerEvent(
            event_type=RunnerEventType.COMPLETED if returncode == 0 else RunnerEventType.FAILED,
            session_id=str(external_id),
            normalized_payload={"returncode": returncode},
        )
        for event in (completion, terminal):
            file_event_type = EVENT_TYPE_MAP.get(event.event_type.value, "status_changed")
            payload = _event_payload(event)
            status = STATUS_MAP.get(event.event_type.value)
            if status:
                payload["status"] = status
            session_files.append_event(root, file_event_type, **payload)
            if status:
                _sync_file_status(root, status)
                session_files.update_state(
                    root,
                    review_status="review" if status == "completed" else "needs_changes",
                    runner_returncode=returncode,
                    runner_pid=int(runtime["pid"].read_text(encoding="utf-8").strip() or "0")
                    if runtime["pid"].exists()
                    else None,
                )
            await _relay_runner_event(convex_session_id, session, event)
        state = session_files.read_state(root)

    pid = None
    if runtime["pid"].exists():
        try:
            pid = int(runtime["pid"].read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = None
    status = state.get("status") or session.get("status") or "running"
    if status not in TERMINAL_STATUSES and returncode is not None:
        process_running = _process_is_running(pid) if pid else False
        if not process_running:
            status = "completed" if returncode == 0 else "failed"
            _sync_file_status(root, status)
            session_files.update_state(
                root,
                review_status="review" if status == "completed" else "needs_changes",
                runner_returncode=returncode,
                runner_pid=pid,
            )
            state = session_files.read_state(root)
    return {
        "session_id": str(external_id),
        "status": state.get("status") or status,
        "normalized_status": {
            "completed": RunnerEventType.COMPLETED.value,
            "failed": RunnerEventType.FAILED.value,
            "cancelled": RunnerEventType.CANCELLED.value,
        }.get(state.get("status") or status, RunnerEventType.PROGRESS.value),
        "raw": {
            "pid": pid,
            "stdout_path": str(runtime["stdout"]),
            "stderr_path": str(runtime["stderr"]),
            "exit_code_path": str(runtime["exit_code"]),
        },
    }


def _validate_research_output_contract(workspace_root: Path, changed_files: list[str]) -> list[str]:
    candidate_paths = [
        workspace_root / rel_path
        for rel_path in changed_files
        if rel_path.endswith(".md")
        and (
            rel_path.startswith("topics/")
            or rel_path.startswith("artifacts/")
            or rel_path.startswith("research/findings/")
        )
    ]
    if not candidate_paths:
        return [
            "Role workflow contract failed for `research`. No markdown findings output was produced under `topics/`, `artifacts/`, or `research/findings/`.",
        ]

    for path in candidate_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        has_facts = bool(re.search(r"(?m)^#{1,6}\s+facts?\b", text))
        has_interpretation = bool(re.search(r"(?m)^#{1,6}\s+interpretation\b", text))
        has_open_questions = bool(re.search(r"(?m)^#{1,6}\s+open questions?\b", text))
        if has_facts and has_interpretation and has_open_questions:
            claims_path = workspace_root / "research_plan" / "state" / "claims.json"
            try:
                claims_raw = json.loads(claims_path.read_text(encoding="utf-8")) if claims_path.exists() else []
            except json.JSONDecodeError:
                claims_raw = []
            if isinstance(claims_raw, list) and claims_raw:
                return []
            return [
                "Role workflow contract failed for `research`. Research sessions must produce at least one claim candidate in `research_plan/state/claims.json`.",
            ]

    return [
        "Role workflow contract failed for `research`. Research markdown outputs must include `Facts`, `Interpretation`, and `Open Questions` sections.",
    ]


def _validate_artifact_output_contract(workspace_root: Path, changed_files: list[str]) -> list[str]:
    candidate_paths = [
        workspace_root / rel_path
        for rel_path in changed_files
        if rel_path.endswith(".md") and rel_path.startswith("artifacts/")
    ]
    if not candidate_paths:
        return [
            "Role workflow contract failed for `artifact`. No markdown artifact was produced under `artifacts/`.",
        ]

    for path in candidate_paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        has_evidence_links = bool(re.search(r"(?m)^#{1,6}\s+evidence links?\b", lowered))
        has_ledger_ref = bool(
            re.search(r"research_plan/state/(claims|sources)\.json#[A-Za-z0-9._:-]+", text)
        )
        if has_evidence_links and has_ledger_ref:
            return []

    return [
        "Role workflow contract failed for `artifact`. Artifact markdown outputs must include an `Evidence Links` section with at least one claim or source ledger reference.",
    ]


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

    resolved_base_ref = base_branch
    fetch_result = await _run_process(
        ["git", "-C", str(project_root), "fetch", "origin", base_branch],
        cwd=project_root,
    )
    if fetch_result["returncode"] == 0:
        remote_ref = f"refs/remotes/origin/{base_branch}"
        show_ref = await _run_process(
            ["git", "-C", str(project_root), "show-ref", "--verify", "--quiet", remote_ref],
            cwd=project_root,
        )
        if show_ref["returncode"] == 0:
            resolved_base_ref = f"origin/{base_branch}"

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
            resolved_base_ref,
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
                resolved_base_ref,
            ],
            cwd=project_root,
        )
    if result["returncode"] != 0:
        raise RuntimeError(result["stderr"].strip() or result["stdout"].strip() or "git worktree add failed")
    return {
        "status": "ready",
        "mode": "git-worktree",
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "base_ref": resolved_base_ref,
    }


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
    result = await _run_workspace_hook(
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
    if result.get("status") != "passed":
        return result

    rail_result = await _ensure_workspace_rail_cli(project_root, workspace_root)
    if rail_result["returncode"] != 0:
        session_files.update_state(
            session_root,
            setup_status="failed",
            setup_exit_code=rail_result["returncode"],
            setup_stdout_tail=_tail_output((result.get("stdout") or "") + "\n" + (rail_result.get("stdout") or "")),
            setup_stderr_tail=_tail_output((result.get("stderr") or "") + "\n" + (rail_result.get("stderr") or "")),
        )
        session_files.append_event(
            session_root,
            "workspace_setup_completed",
            content="Workspace setup failed while installing rail-py.",
            status=session_files.read_state(session_root).get("status"),
            exit_code=rail_result["returncode"],
        )
        return {"status": "failed", **rail_result}

    session_files.update_state(
        session_root,
        setup_stdout_tail=_tail_output((result.get("stdout") or "") + "\nRAIL CLI installed."),
        setup_stderr_tail=_tail_output((result.get("stderr") or "") + ("\n" + rail_result.get("stderr") if rail_result.get("stderr") else "")),
    )
    return result


async def _overlay_active_hydration_artifacts_into_workspace(
    *,
    project: dict[str, Any] | None,
    workspace_root: Path,
    session_root: Path,
) -> dict[str, Any]:
    if not project or not project.get("_id"):
        return {"status": "skipped", "reason": "missing_project"}

    hydration_status = await hydration_registry_service.get_hydration_status(project=project)
    reusable = hydration_status.get("reusableArtifact") or {}
    if hydration_status.get("state") != "hydrated_on_this_device" or not reusable:
        return {"status": "skipped", "reason": hydration_status.get("state") or "not_hydrated"}

    onto_db_source = reusable.get("ontologyArtifactPath")
    onto_duckdb_source = reusable.get("duckdbArtifactPath")
    if not onto_db_source or not onto_duckdb_source:
        artifacts = await project_artifacts_service.resolve(str(project["_id"]))
        onto_db_source = onto_db_source or artifacts.db_path
        onto_duckdb_source = onto_duckdb_source or artifacts.duckdb_path
    workspace_ontology_root = workspace_root / ".ontology"
    workspace_ontology_root.mkdir(parents=True, exist_ok=True)

    copies: list[dict[str, Any]] = []
    for source_path, filename in (
        (Path(str(onto_db_source)), "onto.db"),
        (Path(str(onto_duckdb_source)), "onto.duckdb"),
    ):
        if not source_path.exists():
            continue
        destination = workspace_ontology_root / filename
        shutil.copy2(source_path, destination)
        copies.append(
            {
                "filename": filename,
                "source": str(source_path),
                "destination": str(destination),
                "sha256": _sha256_file(destination),
            }
        )

    metadata = {
        "artifactId": reusable.get("_id"),
        "projectId": project.get("_id"),
        "projectSlug": project.get("slug"),
        "state": hydration_status.get("state"),
        "pipelineSlug": hydration_status.get("pipelineSlug"),
        "hydrationMode": hydration_status.get("hydrationMode"),
        "commitSha": reusable.get("commitSha"),
        "manifestFingerprint": reusable.get("manifestFingerprint"),
        "ontologyArtifactPath": str(workspace_ontology_root / "onto.db"),
        "duckdbArtifactPath": str(workspace_ontology_root / "onto.duckdb"),
        "mirroredFrom": {
            "ontologyArtifactPath": reusable.get("ontologyArtifactPath"),
            "duckdbArtifactPath": reusable.get("duckdbArtifactPath"),
        },
        "copiedAtMs": int(time.time() * 1000),
    }
    metadata_path = workspace_ontology_root / ".rail_hydration.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    session_files.update_state(
        session_root,
        workspace_hydration_status="mirrored",
        workspace_hydration_pipeline=hydration_status.get("pipelineSlug"),
        workspace_hydration_commit_sha=reusable.get("commitSha"),
        workspace_hydration_duckdb=str(workspace_ontology_root / "onto.duckdb"),
    )
    session_files.append_event(
        session_root,
        "status_changed",
        content="Mirrored active hydration artifacts into workspace `.ontology/`.",
        status=session_files.read_state(session_root).get("status"),
        metadata={"hydration_artifacts": copies, "pipelineSlug": hydration_status.get("pipelineSlug")},
    )
    return {"status": "mirrored", "files": copies, "pipelineSlug": hydration_status.get("pipelineSlug")}


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
    project = await _load_project(session.get("projectId"), session.get("projectSlug"))
    project_root = _project_root(project or {})
    if project_root is None:
        raise RuntimeError("Session has no project root")
    session_root = _resolve_session_root_path(session, project_root=project_root)
    if session_root is None:
        raise RuntimeError("Session has no sessionPath")
    state = session_files.read_state(session_root)
    workspace_path = state.get("workspace_path")
    if not workspace_path:
        raise RuntimeError("Session has no workspace_path")
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
    project: dict[str, Any],
    project_root: Path,
    session_root: Path,
    base_branch: str,
) -> None:
    state = session_files.read_state(session_root)
    workspace_path = state.get("workspace_path")
    terminal_status = state.get("status")
    if not workspace_path:
        session_files.refresh_summary(session_root)
        if terminal_status in TERMINAL_STATUSES:
            summary = state.get("completion_summary") or {}
            changed_files = list(
                dict.fromkeys(
                    str(path)
                    for path in (summary.get("artifacts_created") or [])
                    if path
                )
            )
            for item in session_files.list_events(session_root):
                if item.get("type") == "file_change_detected" and item.get("path"):
                    path = str(item["path"])
                    if path not in changed_files:
                        changed_files.append(path)
            await write_post_run_audit(
                project=project,
                project_root=project_root,
                session_root=session_root,
                session_id=convex_session_id,
                session=session,
                changed_files=changed_files,
            )
        return
    workspace_root = Path(workspace_path)
    workspace_branch = state.get("workspace_branch") or f"{session.get('role') or 'agent'}-{convex_session_id}"
    review_status = state.get("review_status") or "pending"
    config = _workspace_config(project_root)
    changed_files = await _list_changed_files(workspace_root)
    if terminal_status in {"failed", "cancelled"}:
        review_status = "needs_changes"

    resolved_task_id = _session_task_id(session, session_root)
    task_record: dict[str, Any] | None = None
    if resolved_task_id:
        try:
            task_record = await _task_record(project, resolved_task_id)
        except Exception:
            task_record = None
    publish_error: str | None = None
    if terminal_status == "completed":
        try:
            await _publish_completed_session_outputs(
                project=project,
                session=session,
                project_root=project_root,
                workspace_root=workspace_root,
                session_root=session_root,
                changed_files=changed_files,
            )
        except Exception as exc:
            publish_error = str(exc)
            review_status = "needs_changes"
            session_files.update_state(
                session_root,
                publish_status="failed",
                publish_strategy="github_app_commit",
                publish_error=publish_error,
            )
            session_files.append_event(
                session_root,
                "publish_failed",
                content=publish_error,
                status=session_files.read_state(session_root).get("status"),
            )
            if project.get("_id"):
                await record_publish_failure(project["_id"], publish_error)

    state = session_files.read_state(session_root)
    should_rerun_verification = terminal_status == "completed" and not publish_error and (
        state.get("verification_status") not in {"passed", "failed", "skipped"}
        or (
            state.get("verification_status") == "failed"
            and state.get("publish_status") == "published"
        )
    )
    if should_rerun_verification:
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
    elif terminal_status == "completed" and state.get("verification_status") in {"passed", "skipped"} and not publish_error:
        review_status = "review"

    summary = await _normalize_completion_summary(
        project_root=project_root,
        workspace_root=workspace_root,
        session_root=session_root,
        session_id=convex_session_id,
        task_id=_session_task_id(session, session_root),
        status=terminal_status or "unknown",
        role=session.get("role") or "agent",
    )
    if publish_error:
        summary["blockers"] = _dedupe((summary.get("blockers") or []) + [f"Connector publish failed: {publish_error}"])
        summary["recommended_next_tasks"] = _dedupe(
            (summary.get("recommended_next_tasks") or []) + ["Fix connector-backed publish failure before re-running autopilot."]
        )
    _copy_workspace_state_indexes(project_root, workspace_root)
    _sync_completion_summary_to_integrity_indexes(
        project_root=project_root,
        workspace_root=workspace_root,
        summary=summary,
        session_id=convex_session_id,
        task_id=_session_task_id(session, session_root),
        role=session.get("role") or "agent",
        verification_command=config.get("verification_script"),
        changed_files=changed_files,
    )
    if terminal_status == "completed" and changed_files:
        try:
            get_integrity_repo(project_root).extract_candidates_from_paths(changed_files)
        except Exception:
            pass
    role = session.get("role") or "agent"
    workflow = summarize_agent_workflow_health(project_root)
    role_health = workflow.get(role)
    workflow_blocker_summary: str | None = None
    role_contract_blockers: list[str] = []
    if terminal_status == "completed" and role == "research":
        role_contract_blockers.extend(_validate_research_output_contract(workspace_root, changed_files))
    if terminal_status == "completed" and role == "artifact":
        role_contract_blockers.extend(_validate_artifact_output_contract(workspace_root, changed_files))
    if terminal_status == "completed" and isinstance(role_health, dict) and role_health.get("status") == "blocked":
        blocker_bits = _relevant_workflow_blockers(
            role_health=role_health,
            changed_files=changed_files,
            summary=summary,
        )
        if blocker_bits:
            workflow_blocker_summary = (
                f"Role workflow contract failed for `{role}`."
                + (f" {'; '.join(blocker_bits)}" if blocker_bits else "")
            )
            role_contract_blockers.append(workflow_blocker_summary)
    if terminal_status == "completed" and role_contract_blockers:
        summary["blockers"] = _dedupe((summary.get("blockers") or []) + role_contract_blockers)
        summary["recommended_next_tasks"] = _dedupe(
            (summary.get("recommended_next_tasks") or []) + [f"Resolve `{role}` workflow blockers before finalizing the session."]
        )
        review_status = "needs_changes"

    current_state = session_files.read_state(session_root)
    if (
        terminal_status == "completed"
        and review_status == "needs_changes"
        and current_state.get("verification_status") == "failed"
        and not publish_error
        and not role_contract_blockers
        and _verification_failures_outside_task_scope(
            state=current_state,
            task=task_record,
            changed_files=changed_files,
        )
    ):
        review_status = "review"
        summary["recommended_next_tasks"] = _dedupe(
            (summary.get("recommended_next_tasks") or [])
            + ["Launch a follow-up task for the remaining repo-level verification failures outside this task scope."]
        )

    session_files.update_state(session_root, review_status=review_status)
    session_files.update_state(session_root, completion_summary=summary)
    session_files.refresh_summary(session_root)
    if terminal_status in TERMINAL_STATUSES:
        await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id=convex_session_id,
            session=session,
            changed_files=changed_files,
        )
    # Audited merge: once a session is published and passes review, merge the
    # workspace branch back into the base branch via the GitHub API.
    github_repo = infer_github_repo(project.get("github") or project.get("gitRepoUrl"))
    if (
        terminal_status == "completed"
        and review_status == "review"
        and not publish_error
        and github_repo
    ):
        try:
            from app.services.github_service import github_service
            await github_service.merge_branch(
                github_repo,
                base_branch,
                workspace_branch,
                commit_message=f"chore(autopilot): merge audited workspace {workspace_branch} → {base_branch} [{convex_session_id}]",
            )
        except Exception as merge_exc:
            merge_error = str(merge_exc)
            session_files.update_state(
                session_root,
                publish_status="failed",
                publish_error=merge_error,
            )
            session_files.append_event(
                session_root,
                "publish_failed",
                content=f"Audited branch merge failed: {merge_error}",
                status=session_files.read_state(session_root).get("status"),
            )
    if publish_error and resolved_task_id:
        await planner_service.update_task(
            resolved_task_id,
            project=project,
            status="blocked",
            blockerCategory="publish_failure",
            latestRunSummary=f"Connector publish failed for session {convex_session_id}: {publish_error}",
        )
        await raise_decision_event(
            project,
            source="runner",
            event_type="publish_failed",
            severity="needs_planner",
            summary=f"Connector publish failed for task {resolved_task_id}: {publish_error}",
            evidence_refs=[
                f"task:{resolved_task_id}",
                f"runner_session:{convex_session_id}",
                f"session_state:{session_root / 'state.json'}",
            ],
            recommended_actions=[
                "Fix connector authentication or path policy",
                "Retry the task only after publish succeeds",
                "Inspect session summary and publish metadata",
            ],
        )
    elif role_contract_blockers and resolved_task_id:
        await planner_service.update_task(
            resolved_task_id,
            project=project,
            status="blocked",
            blockerCategory="workflow_contract",
            latestRunSummary="; ".join(role_contract_blockers),
        )
    elif resolved_task_id:
        task_status = "done" if review_status == "review" else "blocked"
        current_state = session_files.read_state(session_root)
        verification_paths = _verification_failure_paths(current_state)
        summary_bits: list[str] = []
        publish_commit = current_state.get("publish_commit_sha")
        if publish_commit:
            summary_bits.append(f"Published commit {publish_commit}")
        if summary.get("blockers") and review_status != "review":
            summary_bits.append("; ".join(str(item) for item in (summary.get("blockers") or [])[:3]))
        elif verification_paths and review_status == "review":
            summary_bits.append(
                "Remaining verification failures are outside this task scope: " + ", ".join(verification_paths[:4])
            )
        elif summary.get("recommended_next_tasks"):
            summary_bits.append(str((summary.get("recommended_next_tasks") or [])[0]))
        latest_summary = ". ".join(bit for bit in summary_bits if bit) or f"Session {convex_session_id} completed."
        await planner_service.update_task(
            resolved_task_id,
            project=project,
            status=task_status,
            blockerCategory="verification_failure" if task_status == "blocked" else None,
            latestRunSummary=latest_summary,
        )





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

    project = await _load_project(project_id, project_slug)
    project_root = _project_root(project or {})
    if project_root is None and local_repo_path:
        project_root = Path(local_repo_path).resolve()
    if project_root is None:
        raise RuntimeError("Runner sessions require a local repo path")
    workspace_config = _workspace_config(project_root)

    if project_id:
        from app.services.reconciliation_service import ensure_execution_lane_available

        lane_state = await ensure_execution_lane_available(
            project or {"_id": project_id, "localRepoPath": str(project_root)},
        )
        active_sessions = list(lane_state.get("activeSessions") or [])
        nonconcurrent = workspace_config.get("nonconcurrent_run", True)
        if not lane_state.get("available") and (nonconcurrent or lane_state.get("policy") == "single_active_worker"):
            if active_sessions:
                active_session = active_sessions[0]
                active_role = active_session.get("role") or "agent"
                raise RuntimeError(
                    "Sequential execution enforced: "
                    f"{active_role} session {active_session['_id']} is still active"
                )
            raise RuntimeError(str(lane_state.get("reason") or "Execution lane blocked."))
    if project:
        role_config = None
        try:
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
        except ValueError as exc:
            raise RuntimeError(f"Runner launch blocked by invalid project state: {exc}") from exc
        if decision.blocked:
            detail = "; ".join(integrity_gate["reasons"]) if integrity_gate["reasons"] else decision.reason
            raise RuntimeError(detail)
        if decision.requires_human_approval and not policy_approval_granted:
            raise PermissionError(decision.reason)
        runner_name = _normalize_runner_name_for_project(runner_name, role_config=role_config)
    else:
        runner_name = _normalize_runner_name_for_project(runner_name)

    if project_id and project:
        from app.services.auditor_service import build_auditor_statuses

        auditors = await build_auditor_statuses(
            project,
            tasks=None,
            active_sessions=active_sessions,
        )
        auditor_blocker = _runner_launch_blocked_by_auditors(role, task_description, auditors)
        if auditor_blocker:
            raise RuntimeError(auditor_blocker)

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
        task_id=task_id,
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
    await _overlay_active_hydration_artifacts_into_workspace(
        project=project,
        workspace_root=workspace_root,
        session_root=session_root,
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
        try:
            await write_post_run_audit(
                project=project or {},
                project_root=project_root,
                session_root=session_root,
                session_id=running_session_id,
                session={"_id": running_session_id, "role": role, "taskId": task_id},
                changed_files=[],
            )
        except Exception:
            pass
        raise RuntimeError(
            setup_result["stderr"].strip()
            or setup_result["stdout"].strip()
            or "Workspace setup failed"
        )
    await _overlay_active_hydration_artifacts_into_workspace(
        project=project,
        workspace_root=workspace_root,
        session_root=session_root,
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
        try:
            await write_post_run_audit(
                project=project or {},
                project_root=project_root,
                session_root=session_root,
                session_id=running_session_id,
                session={"_id": running_session_id, "role": role, "taskId": task_id},
                changed_files=[],
            )
        except Exception:
            pass
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
    project = await _load_project(project_id or (session.get("projectId") if session else None), session.get("projectSlug") if session else None)
    project_root = _project_root(project or {})
    root = _resolve_session_root_path(session, project_root=project_root) if session else _find_file_backed_session_root(project_root, convex_session_id)
    if not session:
        if not root or not root.exists():
            raise ValueError(f"Session {convex_session_id} not found")
        state = session_files.read_state(root)
        role = state.get("role") or root.parent.name
        if (
            project_root is not None
            and state.get("status") in TERMINAL_STATUSES
            and (
                state.get("publish_status") in {None, "", "not_started"}
                or state.get("verification_status") not in {"passed", "failed", "skipped"}
                or state.get("review_status") == "pending"
                or _should_retry_post_publish_verification(state)
                or _should_retry_workflow_contract_review(state)
                or _should_retry_stale_review_status(state)
                or _should_retry_false_publish_failure(state)
            )
        ):
            synthetic_session = {
                "_id": convex_session_id,
                "projectId": project_id,
                "projectSlug": project.get("slug") if project else None,
                "role": role,
                "runner": state.get("runner") or "codex_cli",
                "externalSessionId": state.get("external_session_id"),
                "status": state.get("status") or "completed",
                "taskId": _session_task_id({}, root),
            }
            await _finalize_workspace_review(
                convex_session_id=convex_session_id,
                session=synthetic_session,
                project=project or {},
                project_root=project_root,
                session_root=root,
                base_branch=(project or {}).get("defaultBranch") or "main",
            )
            state = session_files.read_state(root)
        result: dict[str, Any] = {
            "_id": convex_session_id,
            "projectId": project_id,
            "projectSlug": project.get("slug") if project else None,
            "role": role,
            "runner": state.get("runner") or "codex_cli",
            "externalSessionId": state.get("external_session_id"),
            "status": state.get("status") or "completed",
            "title": state.get("title") or f"[{role}] {convex_session_id}",
        }
        result["fileState"] = state
        result["summaryPath"] = str(root / "summary.md")
        return result

    result = dict(session)
    if root and root.exists():
        result["fileState"] = session_files.read_state(root)
        result["summaryPath"] = str(root / "summary.md")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    if sync_from_runner and external_id:
        try:
            if runner_name in LOCAL_CLI_RUNNERS and root and root.exists():
                runner_info = await _ingest_local_cli_runner_events(
                    convex_session_id=convex_session_id,
                    session=session,
                    root=root,
                )
            else:
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
            if root and root.exists() and new_status in TERMINAL_STATUSES:
                file_state = session_files.read_state(root)
                needs_finalization = (
                    file_state.get("status") not in TERMINAL_STATUSES
                    or file_state.get("publish_status") in {None, "", "not_started"}
                    or file_state.get("verification_status") not in {"passed", "failed", "skipped"}
                )
                if needs_finalization:
                    try:
                        await ingest_session_events(convex_session_id, project_id=project_id)
                    except Exception:
                        pass
                    refreshed_state = session_files.read_state(root)
                    still_needs_finalization = (
                        refreshed_state.get("publish_status") in {None, "", "not_started"}
                        or refreshed_state.get("verification_status") not in {"passed", "failed", "skipped"}
                        or refreshed_state.get("review_status") == "pending"
                        or _should_retry_post_publish_verification(refreshed_state)
                        or _should_retry_workflow_contract_review(refreshed_state)
                        or _should_retry_stale_review_status(refreshed_state)
                        or _should_retry_false_publish_failure(refreshed_state)
                    )
                    if still_needs_finalization:
                        if project_root is not None:
                            await _finalize_workspace_review(
                                convex_session_id=convex_session_id,
                                session=session,
                                project=project or {},
                                project_root=project_root,
                                session_root=root,
                                base_branch=(project or {}).get("defaultBranch") or "main",
                            )
                    result["fileState"] = session_files.read_state(root)
                    result["summaryPath"] = str(root / "summary.md")
        except Exception as exc:
            result["syncError"] = str(exc)
        finally:
            if root and root.exists():
                result["fileState"] = session_files.read_state(root)
                result["summaryPath"] = str(root / "summary.md")
    if root and root.exists():
        file_state = session_files.read_state(root)
        still_needs_finalization = (
            file_state.get("status") in TERMINAL_STATUSES
            and (
                file_state.get("publish_status") in {None, "", "not_started"}
                or file_state.get("verification_status") not in {"passed", "failed", "skipped"}
                or file_state.get("review_status") == "pending"
                or _should_retry_post_publish_verification(file_state)
                or _should_retry_workflow_contract_review(file_state)
                or _should_retry_stale_review_status(file_state)
                or _should_retry_false_publish_failure(file_state)
            )
        )
        if still_needs_finalization and project_root is not None:
            await _finalize_workspace_review(
                convex_session_id=convex_session_id,
                session=session,
                project=project or {},
                project_root=project_root,
                session_root=root,
                base_branch=(project or {}).get("defaultBranch") or "main",
            )
            result["fileState"] = session_files.read_state(root)
            result["summaryPath"] = str(root / "summary.md")
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
    had_runtime_session = session is not None
    project = await _load_project(project_id or (session.get("projectId") if session else None), session.get("projectSlug") if session else None)
    project_root = _project_root(project or {})
    root = _resolve_session_root_path(session, project_root=project_root) if session else _find_file_backed_session_root(project_root, convex_session_id)
    if not session:
        if not root or not root.exists():
            raise ValueError(f"Session {convex_session_id} not found")
        state = session_files.read_state(root)
        role = state.get("role") or root.parent.name
        session = {
            "_id": convex_session_id,
            "projectId": project_id,
            "projectSlug": project.get("slug") if project else None,
            "role": role,
            "runner": state.get("runner") or "codex_cli",
            "externalSessionId": state.get("external_session_id"),
            "status": state.get("status") or "running",
        }

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

    if root and root.exists():
        session_files.append_event(
            root,
            "cancelled",
            content="Session cancelled by user.",
            status="cancelled",
        )
        _sync_file_status(root, "cancelled")
        if project_root is not None:
            # Run the finalize hook so post-run auditors fire on the cancelled
            # session and reconciliation does not flag it as a stale audit.
            try:
                await _finalize_workspace_review(
                    convex_session_id=convex_session_id,
                    session=session,
                    project=project or {},
                    project_root=project_root,
                    session_root=root,
                    base_branch=(project or {}).get("defaultBranch") or "main",
                )
            except Exception:
                pass

    if had_runtime_session:
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
    project = await _load_project(project_id or session.get("projectId"), session.get("projectSlug"))
    project_root = _project_root(project or {})
    root = _resolve_session_root_path(session, project_root=project_root)
    if runner_name in LOCAL_CLI_RUNNERS and root and root.exists():
        info = await _ingest_local_cli_runner_events(
            convex_session_id=convex_session_id,
            session=session,
            root=root,
        )
        state = session_files.read_state(root)
        if state.get("status") in TERMINAL_STATUSES:
            await running_agent_service.finalize_running_agent(
                convex_session_id,
                status=state["status"],
                ended_at=int(time.time() * 1000),
            )
        return [{"event_type": info.get("normalized_status", "progress"), "debug_visibility": False}]

    api_key = (
        await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
        if runner_name == "jules"
        else None
    )
    runner = resolve_runner_for_project(runner_name, api_key=api_key)
    events = await runner.list_events(external_id)
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
            if project_root is not None:
                await _finalize_workspace_review(
                    convex_session_id=convex_session_id,
                    session=session,
                    project=project or {},
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
    project = await _load_project(session.get("projectId"), session.get("projectSlug"))
    project_root = _project_root(project or {})
    root = _resolve_session_root_path(session, project_root=project_root)
    if root is None:
        raise RuntimeError("Session has no sessionPath")
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
        task_id=_session_task_id(session_record),
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
    if not project_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return
    project_root = _project_root(project)
    session_root = _resolve_session_root_path(session_record, project_root=project_root)
    task_id = _session_task_id(session_record, session_root)
    if not task_id:
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
