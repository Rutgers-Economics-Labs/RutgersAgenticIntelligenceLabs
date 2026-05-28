from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from rail.completion_gate import PlannerCompletionGate

from app.services.convex_client import convex
from app.services import session_files
from app.services.role_runtime_service import ROLE_ALIASES


PLANNER_THREAD_ID = "planner"
DEFAULT_BOARD_TITLE = "Main Board"
TASK_STATUSES = [
    "backlog",
    "ready",
    "awaiting_approval",
    "running",
    "blocked",
    "review",
    "done",
    "cancelled",
    "superseded",
]
TASK_APPROVAL_STATES = [
    "pending",
    "granted",
]
TASK_RUNNERS = [
    "default",
    "jules",
    "claude_code",
    "gemini_cli",
    "cursor_cli",
    "codex_cli",
]
TASK_PRIORITIES = [
    "high",
    "medium",
    "low",
]
APPROVAL_STATUSES = [
    "pending",
    "granted",
    "rejected",
]
APPROVAL_TYPES = [
    "run_task",
    "research_launch",
]
LEGACY_APPROVAL_STATUS_ALIASES = {
    "approved": "granted",
}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].rstrip("-") or "item"


def _normalize_approval_status(status: str | None) -> str:
    normalized = str(status or "pending").strip().lower()
    normalized = LEGACY_APPROVAL_STATUS_ALIASES.get(normalized, normalized)
    if normalized not in APPROVAL_STATUSES:
        raise ValueError(f"Unsupported approval status: {status}")
    return normalized


def _normalize_approval_type(approval_type: str | None) -> str:
    normalized = str(approval_type or "run_task").strip().lower()
    if normalized not in APPROVAL_TYPES:
        raise ValueError(f"Unsupported approval type: {approval_type}")
    return normalized


def _normalize_task_status(status: str | None, *, strict: bool = False) -> str:
    normalized = str(status or "backlog").strip().lower()
    if normalized in TASK_STATUSES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported task status: {status}")
    return "backlog"


def _normalize_role_alias(role: str | None, default: str) -> str:
    normalized = str(role or default).strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def _normalize_task_approval_state(approval_state: str | None, *, strict: bool = False) -> str | None:
    normalized = str(approval_state or "").strip().lower()
    if not normalized:
        return None
    normalized = LEGACY_APPROVAL_STATUS_ALIASES.get(normalized, normalized)
    if normalized in TASK_APPROVAL_STATES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported task approval state: {approval_state}")
    return None


def _normalize_task_priority(priority: str | None, *, strict: bool = False) -> str | None:
    normalized = str(priority or "").strip().lower()
    if not normalized:
        return None
    if normalized in TASK_PRIORITIES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported task priority: {priority}")
    return None


def _normalize_task_runner(runner: str | None, *, strict: bool = False) -> str | None:
    normalized = str(runner or "").strip().lower()
    if not normalized:
        return None
    if normalized in TASK_RUNNERS:
        return normalized
    if strict:
        raise ValueError(f"Unsupported task runner: {runner}")
    return None


def _enforce_planner_completion_gate(*, root: Path, task: dict[str, Any], patch: dict[str, Any]) -> None:
    if str(patch.get("status") or "").strip().lower() != "done":
        return
    if str(task.get("agentRole") or "").strip().lower() != "planner":
        return

    summary = PlannerCompletionGate().check(
        {
            "repo_path": str(root),
            "plan_root": "research_plan",
            "db_task_status_current": True,
        }
    )
    if summary.passed:
        return

    failures = summary.failures
    reason = failures[0].message if failures else "Planner completion gate failed."
    raise ValueError(f"Planner tasks cannot be marked done until planner completion checks pass: {reason}")


def _latest_task_audit(root: Path, task_id: str) -> dict[str, Any] | None:
    audit_root = root / "research_plan" / "audits"
    if not audit_root.is_dir():
        return None
    candidates = sorted(audit_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        session = payload.get("session") or {}
        if str(session.get("taskId") or "").strip() != task_id:
            continue
        return payload
    return None


def _enforce_worker_completion_gate(*, root: Path, task: dict[str, Any], patch: dict[str, Any], require_audit: bool = True) -> None:
    if not require_audit:
        return
    if str(patch.get("status") or "").strip().lower() != "done":
        return
    role = str(task.get("agentRole") or "").strip().lower()
    if not role or role == "planner":
        return

    audit = _latest_task_audit(root, str(task.get("_id") or ""))
    if audit is None:
        raise ValueError(
            "Worker tasks cannot be marked done until a reviewed post-run audit exists for the task."
        )

    session = audit.get("session") or {}
    integrity = audit.get("integrity") or {}
    current_blocker = str(audit.get("currentBlocker") or "").strip()
    review_status = str(session.get("reviewStatus") or "").strip().lower()
    session_status = str(session.get("status") or "").strip().lower()
    if (
        review_status != "review"
        or session_status not in {"completed", "failed", "cancelled"}
        or bool(integrity.get("blocked"))
        or bool(current_blocker)
    ):
        raise ValueError(
            "Worker tasks cannot be marked done until a reviewed post-run audit clears blockers for the task."
        )


def _audit_allows_worker_done(root: Path, task_id: str) -> bool:
    audit = _latest_task_audit(root, task_id)
    if audit is None:
        return False
    session = audit.get("session") or {}
    integrity = audit.get("integrity") or {}
    current_blocker = str(audit.get("currentBlocker") or "").strip()
    review_status = str(session.get("reviewStatus") or "").strip().lower()
    session_status = str(session.get("status") or "").strip().lower()
    return (
        review_status == "review"
        and session_status in {"completed", "failed", "cancelled"}
        and not bool(integrity.get("blocked"))
        and not bool(current_blocker)
    )


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---\n"):
        return {}, content
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, content
    raw_meta = parts[0][4:]
    try:
        meta = yaml.safe_load(raw_meta) or {}
    except Exception:
        meta = _parse_frontmatter_lenient(raw_meta)
    return meta if isinstance(meta, dict) else {}, parts[1]


def _parse_frontmatter_lenient(raw_meta: str) -> dict[str, Any]:
    """Best-effort parser for older repo task files with invalid YAML scalars.

    This intentionally handles only the frontmatter shapes we persist for
    planner task files: top-level scalar keys plus simple indented lists.
    """
    meta: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in raw_meta.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            meta.setdefault(current_key, []).append(line[4:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if not value:
            meta[current_key] = []
            continue
        if value == "[]":
            meta[current_key] = []
            continue
        if value.lower() == "null":
            meta[current_key] = None
            continue
        meta[current_key] = value.strip("\"'")
    return meta


def get_project_by_slug_path(project_root: Path, slug: str) -> Path:
    return project_root / "research_plan" / "tasks" / f"{slug}.md"


def _candidate_local_project_roots(slug: str) -> list[Path]:
    repo_root = Path(__file__).resolve().parents[4]
    configured_base = Path(os.environ.get("RAIL_PROJECTS_DIR", str(repo_root))).expanduser().resolve()
    candidates = [
        configured_base / slug,
        configured_base / "generated_projects" / slug,
        repo_root / slug,
        repo_root / "generated_projects" / slug,
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _local_project_record_from_repo(slug: str) -> dict[str, Any] | None:
    for root in _candidate_local_project_roots(slug):
        manifest_path = root / "rail.yaml"
        if not manifest_path.exists():
            continue
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        project_meta = raw.get("project") if isinstance(raw.get("project"), dict) else {}
        hydration_meta = raw.get("hydration") if isinstance(raw.get("hydration"), dict) else {}
        autonomy_meta = raw.get("autonomy") if isinstance(raw.get("autonomy"), dict) else {}
        return {
            "_id": f"local:{slug}",
            "name": project_meta.get("name") or slug,
            "slug": project_meta.get("slug") or slug,
            "description": project_meta.get("description") or "",
            "status": "ready",
            "localRepoPath": str(root),
            "manifestPath": "rail.yaml",
            "defaultBranch": project_meta.get("default_branch") or project_meta.get("defaultBranch") or "main",
            "gitRepoUrl": project_meta.get("git_repo_url") or project_meta.get("gitRepoUrl"),
            "agentModel": project_meta.get("agent_model") or project_meta.get("agentModel"),
            "apiConfigSlugs": list(hydration_meta.get("linked_sources") or []),
            "pipelineConfigSlug": hydration_meta.get("default_pipeline") or hydration_meta.get("pipeline"),
            "ontologyConfigSlug": hydration_meta.get("ontology_file"),
            "githubSyncMode": autonomy_meta.get("mode"),
        }
    return None


async def get_project_by_slug(slug: str) -> dict:
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if project:
        return project
    local_project = _local_project_record_from_repo(slug)
    if local_project:
        return local_project
    raise ValueError(f"Project '{slug}' not found")


def project_root_from_record(project: dict) -> Path | None:
    local_repo_path = project.get("localRepoPath")
    if not local_repo_path:
        return None
    return Path(local_repo_path).resolve()


def load_validated_manifest(project: dict):
    """Load rail.yaml for a project record and enforce repo-contract validation."""
    from app.services.repo_contract_service import ensure_project_boot

    root = project_root_from_record(project)
    if root is None:
        raise ValueError("Project does not have a localRepoPath configured")
    return ensure_project_boot(root)


def _planner_session_root(project: dict, thread_id: str = PLANNER_THREAD_ID) -> Path | None:
    root = project_root_from_record(project)
    if root is None:
        return None
    return session_files.ensure_session_root(root, "planner", thread_id)


async def ensure_planner_thread(project_id: str) -> str:
    return PLANNER_THREAD_ID


async def append_planner_message(
    *,
    project: dict,
    role: str,
    content: str,
    message_type: str = "chat",
    session_id: str | None = None,
    thread_id: str = PLANNER_THREAD_ID,
) -> Any:
    root = _planner_session_root(project, thread_id)
    if root is None:
        return {"role": role, "content": content, "messageType": message_type}
    event_type = "assistant_message" if role == "assistant" else "user_message"
    return session_files.append_event(
        root,
        event_type,
        role=role,
        content=content,
        message_type=message_type,
        session_id=session_id,
    )


async def list_planner_messages(project: dict, thread_id: str = PLANNER_THREAD_ID, limit: int = 200) -> list[dict]:
    root = _planner_session_root(project, thread_id)
    if root is None:
        return []
    return session_files.session_messages(root)[-limit:]


async def ensure_main_board(project: dict, session_id: str | None = None) -> dict:
    project_id = project.get("_id") or project.get("projectId") or project.get("slug")
    if not project_id:
        raise ValueError("Project record is missing a durable id")
    return {
        "_id": "main",
        "projectId": project_id,
        "sessionId": session_id,
        "title": DEFAULT_BOARD_TITLE,
        "status": "active",
    }


def _task_root(project_root: Path) -> Path:
    return project_root / "research_plan" / "tasks"


def _task_dedupe_key(task: dict[str, Any]) -> tuple[str, str]:
    return (
        str(task.get("title") or "").strip().lower(),
        str(task.get("agentRole") or task.get("agent_role") or "").strip().lower(),
    )


def _session_task_roots(project_root: Path) -> list[Path]:
    sessions_root = project_root / "research_plan" / "sessions"
    if not sessions_root.is_dir():
        return []
    return sorted(path for path in sessions_root.glob("*/*") if path.is_dir())


def _session_state_recency_key(session_root: Path, state: dict[str, Any]) -> tuple[str, float]:
    updated_at = str(state.get("updated_at") or "").strip()
    try:
        mtime = session_root.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    return (updated_at, mtime)


def _latest_terminal_session_roots_by_task(project_root: Path) -> dict[str, Path]:
    latest: dict[str, tuple[tuple[str, float], Path]] = {}
    for session_root in _session_task_roots(project_root):
        state = session_files.read_state(session_root)
        if str(state.get("status") or "") not in {"completed", "failed", "cancelled"}:
            continue
        task_id = str(state.get("task_id") or "").strip()
        if not task_id:
            continue
        candidate = (_session_state_recency_key(session_root, state), session_root)
        existing = latest.get(task_id)
        if existing is None or candidate[0] > existing[0]:
            latest[task_id] = candidate
    return {task_id: item[1] for task_id, item in latest.items()}


def _task_preference_key(task: dict[str, Any], path: Path) -> tuple[int, int, float]:
    meta, _ = _split_frontmatter(_read_text(path))
    has_explicit_task_id = 1 if meta.get("task_id") else 0
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    return (
        has_explicit_task_id,
        len(str(task.get("_id") or "")),
        mtime,
    )


def _task_to_runtime(path: Path) -> dict[str, Any]:
    meta, body = _split_frontmatter(_read_text(path))
    title = meta.get("title") or path.stem.replace("-", " ").title()
    task_id = meta.get("task_id") or path.stem
    # Strip the "## Description\n\n" header that _render_task_markdown adds,
    # to avoid it accumulating on every read/write cycle.
    description = body.strip()
    if description.startswith("## Description"):
        description = description[len("## Description"):].lstrip("\n").strip()
    status = _normalize_task_status(meta.get("status", "backlog"))
    approval_state = _normalize_task_approval_state(meta.get("approval_state"))
    blocker_category = meta.get("blocker_category") or None
    if status in {"done", "cancelled", "superseded"}:
        approval_state = None
        blocker_category = None
    return {
        "_id": task_id,
        "boardId": "main",
        "title": title,
        "description": description,
        "status": status,
        "agentRole": _normalize_role_alias(meta.get("assigned_role") or meta.get("agent_role"), "planner"),
        "repoPaths": meta.get("related_files") or [],
        "acceptanceCriteria": meta.get("acceptance_criteria") or [],
        "dependsOnTaskIds": meta.get("dependencies") or [],
        "approvalState": approval_state,
        "priority": _normalize_task_priority(meta.get("priority")),
        "runner": _normalize_task_runner(meta.get("runner")),
        "blockerCategory": blocker_category,
        "gitSnapshotPath": str(path.relative_to(path.parents[2])),
        "latestRunSummary": meta.get("latest_run_summary") or "Not started",
        "supersededBy": meta.get("superseded_by") or None,
    }


async def list_tasks(board_id: str, *, project: dict | None = None) -> list[dict]:
    if project is None:
        return []
    root = project_root_from_record(project)
    if root is None:
        return []
    task_dir = _task_root(root)
    if not task_dir.is_dir():
        return []
    chosen: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
    fallback: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(task_dir.glob("*.md")):
        if not path.exists():
            continue
        task = _task_to_runtime(path)
        key = _task_dedupe_key(task)
        if key == ("", ""):
            fallback.append((task, path))
            continue
        existing = chosen.get(key)
        if existing is not None and not existing[1].exists():
            existing = None
            chosen.pop(key, None)
        if existing is None or _task_preference_key(task, path) > _task_preference_key(existing[0], existing[1]):
            chosen[key] = (task, path)
    tasks = [item[0] for item in chosen.values()] + [item[0] for item in fallback]
    return sorted(tasks, key=lambda item: str(item.get("_id") or ""))


async def reconcile_task_files(project: dict) -> dict[str, Any]:
    root = project_root_from_record(project)
    if root is None:
        return {"removed": []}
    task_dir = _task_root(root)
    if not task_dir.is_dir():
        return {"removed": []}

    chosen: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
    duplicates: list[Path] = []
    for path in sorted(task_dir.glob("*.md")):
        if not path.exists():
            continue
        task = _task_to_runtime(path)
        key = _task_dedupe_key(task)
        if key == ("", ""):
            continue
        existing = chosen.get(key)
        if existing is not None and not existing[1].exists():
            existing = None
            chosen.pop(key, None)
        if existing is None:
            chosen[key] = (task, path)
            continue
        if _task_preference_key(task, path) > _task_preference_key(existing[0], existing[1]):
            duplicates.append(existing[1])
            chosen[key] = (task, path)
        else:
            duplicates.append(path)

    removed: list[str] = []
    for path in duplicates:
        if not path.exists():
            continue
        removed.append(str(path.relative_to(root)))
        path.unlink()
    return {"removed": removed}


def _terminal_task_patch_from_session_state(state: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    status = str(state.get("status") or "")
    if status not in {"completed", "failed", "cancelled"}:
        return None

    review_status = str(state.get("review_status") or "")
    blockers = list((state.get("completion_summary") or {}).get("blockers") or [])
    recommended_next = list((state.get("completion_summary") or {}).get("recommended_next_tasks") or [])
    publish_error = str(state.get("publish_error") or "").strip()
    publish_commit = str(state.get("publish_commit_sha") or "").strip()

    if status == "cancelled":
        task_status = "cancelled"
    elif review_status == "review":
        task_status = "done"
    else:
        task_status = "blocked"

    blocker_category: str | None = None
    if task_status == "blocked":
        if publish_error or str(state.get("publish_status") or "") == "failed":
            blocker_category = "publish_failure"
        elif any("Role workflow contract failed" in str(item) for item in blockers):
            blocker_category = "workflow_contract"
        else:
            blocker_category = "verification_failure"

    summary_bits: list[str] = []
    if publish_commit:
        summary_bits.append(f"Published commit {publish_commit}")
    if blockers and task_status == "blocked":
        summary_bits.append("; ".join(str(item) for item in blockers[:3]))
    elif recommended_next:
        summary_bits.append(str(recommended_next[0]))
    latest_summary = ". ".join(bit for bit in summary_bits if bit) or f"Recovered from session {session_id}."

    return {
        "status": task_status,
        "approvalState": None if task_status in {"done", "cancelled"} else None,
        "blockerCategory": blocker_category,
        "latestRunSummary": latest_summary,
    }


def _task_explicitly_reopened(task: dict[str, Any]) -> bool:
    status = str(task.get("status") or "").strip().lower()
    summary = str(task.get("latestRunSummary") or "").strip()
    return status in {"backlog", "ready", "awaiting_approval", "running"} and summary.startswith("Reopened by Autopilot")


def _session_requires_worker_audit_hold(task: dict[str, Any], state: dict[str, Any]) -> bool:
    session_role = str(state.get("role") or "").strip().lower()
    if session_role and session_role != "planner":
        return True
    task_role = str(task.get("agentRole") or "").strip().lower()
    return task_role not in {"", "planner"}


async def reconcile_task_session_states(project: dict) -> dict[str, Any]:
    root = project_root_from_record(project)
    if root is None:
        return {"updated": []}

    tasks = await list_tasks("main", project=project)
    task_by_id = {str(task.get("_id") or ""): task for task in tasks}
    updated: list[str] = []

    for session_root in _latest_terminal_session_roots_by_task(root).values():
        state = session_files.read_state(session_root)
        task_id = str(state.get("task_id") or "").strip()
        if not task_id:
            continue
        task = task_by_id.get(task_id)
        if task is None:
            continue
        patch = _terminal_task_patch_from_session_state(state, str(state.get("session_id") or session_root.name))
        if patch is None:
            continue
        if _task_explicitly_reopened(task):
            continue
        if (
            patch.get("status") == "done"
            and _session_requires_worker_audit_hold(task, state)
            and not _audit_allows_worker_done(root, task_id)
        ):
            patch = {
                **patch,
                "status": "review",
                "latestRunSummary": (
                    "Session completed and is awaiting a reviewed post-run audit before task closeout."
                ),
            }
        current_status = str(task.get("status") or "")
        current_blocker = task.get("blockerCategory")
        current_summary = str(task.get("latestRunSummary") or "")
        needs_update = (
            current_status != patch["status"]
            or current_blocker != patch["blockerCategory"]
            or current_summary != patch["latestRunSummary"]
            or (task.get("approvalState") is not None and patch["status"] in {"done", "cancelled", "blocked"})
        )
        if not needs_update:
            continue
        await update_task(
            task_id,
            project=project,
            status=patch["status"],
            blockerCategory=patch["blockerCategory"],
            approvalState=patch["approvalState"],
            latestRunSummary=patch["latestRunSummary"],
        )
        updated.append(task_id)
    return {"updated": updated}


async def reconcile_planner_metadata(project: dict) -> dict[str, Any]:
    root = project_root_from_record(project)
    if root is None:
        return {"updatedTaskIds": [], "updatedApprovalIds": []}

    updated_task_ids: list[str] = []
    task_dir = _task_root(root)
    if task_dir.is_dir():
        for path in sorted(task_dir.glob("*.md")):
            task = _task_to_runtime(path)
            canonical = _render_task_markdown(task)
            current = _read_text(path)
            if current == canonical:
                continue
            _write_file(path, canonical)
            updated_task_ids.append(str(task.get("_id") or path.stem))

    updated_approval_ids: list[str] = []
    approval_dir = _approval_dir(root)
    if approval_dir.is_dir():
        for path in sorted(approval_dir.glob("*.md")):
            approval = _approval_to_runtime(path)
            canonical = _render_approval_markdown(approval)
            current = _read_text(path)
            if current == canonical:
                continue
            _write_file(path, canonical)
            updated_approval_ids.append(str(approval.get("_id") or path.stem))

    return {"updatedTaskIds": updated_task_ids, "updatedApprovalIds": updated_approval_ids}


def _render_task_markdown(task: dict[str, Any]) -> str:
    meta = {
        "task_id": task["_id"],
        "title": task["title"],
        "status": task.get("status", "backlog"),
        "assigned_role": task.get("agentRole") or task.get("agent_role") or "planner",
        "dependencies": task.get("dependsOnTaskIds") or [],
        "acceptance_criteria": task.get("acceptanceCriteria") or [],
        "related_files": task.get("repoPaths") or [],
        "latest_run_summary": task.get("latestRunSummary") or "Not started",
    }
    if task.get("approvalState"):
        meta["approval_state"] = task["approvalState"]
    if task.get("priority"):
        meta["priority"] = task["priority"]
    if task.get("runner"):
        meta["runner"] = task["runner"]
    if task.get("blockerCategory"):
        meta["blocker_category"] = task["blockerCategory"]
    if task.get("supersededBy"):
        meta["superseded_by"] = task["supersededBy"]
    frontmatter = yaml.safe_dump(meta, sort_keys=False).strip()
    description = (task.get("description") or "").strip()
    body = "## Description\n\n" + (description or "No description provided.") + "\n"
    return f"---\n{frontmatter}\n---\n\n{body}"


async def create_task(
    *,
    project: dict,
    board_id: str,
    title: str,
    description: str,
    status: str,
    agent_role: str,
    repo_paths: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    depends_on_task_ids: list[str] | None = None,
    session_id: str | None = None,
    priority: str | None = None,
    runner: str | None = None,
    approval_state: str | None = None,
    git_snapshot_path: str | None = None,
) -> dict:
    project_id = project.get("_id") or project.get("projectId")
    if not project_id:
        raise ValueError("Project record is missing a durable id")
    root = project_root_from_record(project)
    if root is None:
        raise ValueError("Project does not have a localRepoPath configured")

    status = _normalize_task_status(status, strict=True)
    priority = _normalize_task_priority(priority, strict=True)
    runner = _normalize_task_runner(runner, strict=True)
    approval_state = _normalize_task_approval_state(approval_state, strict=True)
    task_id = _slugify(title)
    path = _task_root(root) / f"{task_id}.md"
    task = {
        "_id": task_id,
        "boardId": board_id,
        "projectId": project_id,
        "sessionId": session_id,
        "title": title,
        "description": description,
        "status": status,
        "priority": priority,
        "agentRole": agent_role,
        "runner": runner,
        "blockerCategory": None,
        "repoPaths": repo_paths or [],
        "acceptanceCriteria": acceptance_criteria or [],
        "dependsOnTaskIds": depends_on_task_ids or [],
        "approvalState": approval_state,
        "gitSnapshotPath": git_snapshot_path or f"research_plan/tasks/{task_id}.md",
        "latestRunSummary": "Not started",
    }
    _write_file(path, _render_task_markdown(task))
    from app.services.autopilot_service import trigger_wake
    trigger_wake(project["slug"])
    return task


async def update_task(task_id: str, *, project: dict, **fields) -> dict | None:
    # Internal flag: when True, skip the worker-completion audit gate because
    # the caller is reconciling task state from audited reality (e.g.,
    # autopilot ontology-lifecycle reconciliation when DuckDB is already
    # hydrated). The caller is responsible for confirming the underlying
    # state via an auditor before passing this flag.
    audited_reality_bypass = bool(fields.pop("audited_reality_bypass", False))
    root = project_root_from_record(project)
    if root is None:
        return None
    path = _task_root(root) / f"{task_id}.md"
    if not path.exists():
        return None
    task = _task_to_runtime(path)
    # Keep explicit None values so callers can clear stale metadata like
    # blockerCategory or approvalState after a task is recovered.
    patch = dict(fields)
    if "status" in patch:
        patch["status"] = _normalize_task_status(patch.get("status"), strict=True)
    if "priority" in patch:
        patch["priority"] = _normalize_task_priority(patch.get("priority"), strict=True)
    if "runner" in patch:
        patch["runner"] = _normalize_task_runner(patch.get("runner"), strict=True)
    if "approvalState" in patch:
        patch["approvalState"] = _normalize_task_approval_state(patch.get("approvalState"), strict=True)
    if "approval_state" in patch:
        patch["approval_state"] = _normalize_task_approval_state(patch.get("approval_state"), strict=True)
    _enforce_planner_completion_gate(root=root, task=task, patch=patch)
    require_audit = True
    try:
        from rail.manifest import load_manifest
        _manifest = load_manifest(root)
        require_audit = _manifest.planner.require_audit_before_advance
    except Exception:
        pass
    if audited_reality_bypass:
        require_audit = False
    _enforce_worker_completion_gate(root=root, task=task, patch=patch, require_audit=require_audit)
    mapping = {
        "title": "title",
        "description": "description",
        "status": "status",
        "priority": "priority",
        "runner": "runner",
        "blockerCategory": "blockerCategory",
        "blocker_category": "blockerCategory",
        "agent_role": "agentRole",
        "agentRole": "agentRole",
        "repoPaths": "repoPaths",
        "acceptanceCriteria": "acceptanceCriteria",
        "acceptance_criteria": "acceptanceCriteria",
        "depends_on_task_ids": "dependsOnTaskIds",
        "dependsOnTaskIds": "dependsOnTaskIds",
        "approvalState": "approvalState",
        "approval_state": "approvalState",
        "gitSnapshotPath": "gitSnapshotPath",
        "latestRunSummary": "latestRunSummary",
    }
    for key, value in patch.items():
        target = mapping.get(key, key)
        if target in task:
            task[target] = value
    _write_file(path, _render_task_markdown(task))
    from app.services.autopilot_service import trigger_wake
    trigger_wake(project["slug"])
    return task


async def supersede_task(task_id: str, *, superseded_by_id: str, project: dict) -> dict | None:
    """Mark a task as superseded by a newer task, recording the successor's ID."""
    root = project_root_from_record(project)
    if root is None:
        return None
    path = _task_root(root) / f"{task_id}.md"
    if not path.exists():
        return None
    task = _task_to_runtime(path)
    task["status"] = "superseded"
    task["supersededBy"] = superseded_by_id
    _write_file(path, _render_task_markdown(task))
    return task


def _approval_dir(project_root: Path) -> Path:
    return project_root / "research_plan" / "approvals"


def _approval_to_runtime(path: Path) -> dict[str, Any]:
    meta, body = _split_frontmatter(_read_text(path))
    approval_id = meta.get("approval_id") or path.stem
    return {
        "_id": approval_id,
        "projectId": meta.get("project_id"),
        "taskId": meta.get("task_id"),
        "agentSessionId": meta.get("agent_session_id"),
        "approvalType": _normalize_approval_type(meta.get("approval_type", "run_task")),
        "status": _normalize_approval_status(meta.get("status", "pending")),
        "requestedByRole": _normalize_role_alias(meta.get("requested_by_role"), "planner"),
        "grantedByUserId": meta.get("granted_by_user_id"),
        "requestedAt": meta.get("requested_at"),
        "resolvedAt": meta.get("resolved_at"),
        "resolutionNote": (body.strip() or None),
    }


def _render_approval_markdown(approval: dict[str, Any]) -> str:
    meta = {
        "approval_id": approval["_id"],
        "project_id": approval.get("projectId"),
        "task_id": approval.get("taskId"),
        "agent_session_id": approval.get("agentSessionId"),
        "approval_type": approval.get("approvalType", "run_task"),
        "status": approval.get("status", "pending"),
        "requested_by_role": approval.get("requestedByRole", "planner"),
        "granted_by_user_id": approval.get("grantedByUserId"),
        "requested_at": approval.get("requestedAt"),
        "resolved_at": approval.get("resolvedAt"),
    }
    body = approval.get("resolutionNote") or "No notes."
    return f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n\n{body}\n"


async def list_approvals(project: dict) -> list[dict]:
    root = project_root_from_record(project)
    if root is None:
        return []
    approval_dir = _approval_dir(root)
    if not approval_dir.is_dir():
        return []
    return [_approval_to_runtime(path) for path in sorted(approval_dir.glob("*.md"))]


async def create_approval(
    *,
    project: dict,
    task_id: str | None,
    agent_session_id: str | None,
    approval_type: str,
    status: str = "pending",
    requested_by_role: str = "planner",
    granted_by_user_id: str | None = None,
    resolution_note: str | None = None,
) -> str:
    root = project_root_from_record(project)
    if root is None:
        raise ValueError("Project does not have a localRepoPath configured")
    approval_type = _normalize_approval_type(approval_type)
    status = _normalize_approval_status(status)
    approval_id = _slugify(f"{approval_type}-{task_id or agent_session_id or session_files.utc_now_iso()}")
    approval = {
        "_id": approval_id,
        "projectId": project["_id"],
        "taskId": task_id,
        "agentSessionId": agent_session_id,
        "approvalType": approval_type,
        "status": status,
        "requestedByRole": requested_by_role,
        "grantedByUserId": granted_by_user_id,
        "requestedAt": session_files.utc_now_iso(),
        "resolvedAt": None,
        "resolutionNote": resolution_note or "Pending approval.",
    }
    path = _approval_dir(root) / f"{approval_id}.md"
    _write_file(path, _render_approval_markdown(approval))
    return approval_id


async def resolve_approval(
    *,
    project: dict,
    approval_id: str,
    status: str,
    granted_by_user_id: str | None = None,
    resolution_note: str | None = None,
) -> dict | None:
    root = project_root_from_record(project)
    if root is None:
        return None
    status = _normalize_approval_status(status)
    path = _approval_dir(root) / f"{approval_id}.md"
    if not path.exists():
        return None
    approval = _approval_to_runtime(path)
    approval["status"] = status
    approval["grantedByUserId"] = granted_by_user_id
    approval["resolvedAt"] = session_files.utc_now_iso()
    if resolution_note is not None:
        approval["resolutionNote"] = resolution_note
    _write_file(path, _render_approval_markdown(approval))
    return approval


def _render_approvals_index(approvals: list[dict]) -> str:
    lines = ["# Approvals", ""]
    if not approvals:
        lines.append("No approvals recorded.")
        return "\n".join(lines) + "\n"
    for item in approvals:
        lines.append(
            f"- `{item.get('status', 'unknown')}` `{item.get('approvalType', 'run_task')}` "
            f"task=`{item.get('taskId') or 'none'}` session=`{item.get('agentSessionId') or 'none'}`"
        )
    lines.append("")
    return "\n".join(lines)


def _render_blockers(project_root: Path) -> str:
    lines = ["# Blockers", ""]
    tasks_dir = _task_root(project_root)
    blockers: list[str] = []
    if tasks_dir.is_dir():
        for path in sorted(tasks_dir.glob("*.md")):
            task = _task_to_runtime(path)
            if task.get("status") == "blocked":
                blockers.append(f"- `{task['_id']}` {task['title']}")
    if not blockers:
        lines.append("No active blockers.")
    else:
        lines.extend(blockers)
    lines.append("")
    return "\n".join(lines)


def _current_plan_markdown(project: dict, tasks: list[dict]) -> str:
    next_tasks = [
        f"- {task.get('title') or task.get('_id') or 'task'}"
        for task in tasks
        if task.get("status") in {"ready", "awaiting_approval", "running"}
    ]
    if not next_tasks:
        next_tasks = ["- Define the next execution step"]
    return (
        f"# Current Plan\n\n"
        f"Project: {project.get('name') or project.get('slug') or 'project'}\n\n"
        f"## Objective\n\n"
        f"{project.get('description') or 'Define and execute the next approved step for this project.'}\n\n"
        f"## Next Steps\n\n"
        + "\n".join(next_tasks)
        + "\n"
    )


async def sync_planner_files(project: dict, board: dict | None = None) -> None:
    root = project_root_from_record(project)
    if root is None:
        return

    from rail.planner_sync import PlannerSync
    syncer = PlannerSync(root)

    await reconcile_task_files(project)
    board = board or await ensure_main_board(project)
    tasks = await list_tasks(board["_id"], project=project)
    approvals = await list_approvals(project)
    plan_root = root / "research_plan"

    _write_file(plan_root / "current_plan.md", _current_plan_markdown(project, tasks))
    syncer.mirror_board(board, tasks)
    for task in tasks:
        syncer.mirror_task(task)
    canonical_paths = {str(task.get("gitSnapshotPath") or "") for task in tasks}
    task_root = _task_root(root)
    if task_root.is_dir():
        canonical_by_key = {_task_dedupe_key(task): str(task.get("gitSnapshotPath") or "") for task in tasks}
        for path in sorted(task_root.glob("*.md")):
            rel_path = str(path.relative_to(root))
            task = _task_to_runtime(path)
            key = _task_dedupe_key(task)
            canonical_rel_path = canonical_by_key.get(key)
            if canonical_rel_path and canonical_rel_path != rel_path:
                path.unlink(missing_ok=True)
    _write_file(plan_root / "approvals.md", _render_approvals_index(approvals))
    _write_file(plan_root / "blockers.md", _render_blockers(root))
    
async def git_sync(project: dict, message: str = "chore: sync workspace") -> bool:
    """Publish current repo-root changes through the GitHub App workflow."""
    import logging
    import asyncio
    from app.services.safe_publish_service import publish_repo_files, record_publish_failure, record_publish_success

    log = logging.getLogger(__name__)
    root = project_root_from_record(project)
    if root is None or not root.is_dir():
        return False
    if not (root / ".git").is_dir():
        return False
    try:
        status_proc = await asyncio.create_subprocess_shell(
            "git status --porcelain",
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await status_proc.communicate()
        if status_proc.returncode != 0:
            log.warning("git status failed during connector sync: %s", stderr.decode())
            return False
        changed_paths: list[str] = []
        for line in stdout.decode().splitlines():
            if not line.strip():
                continue
            path = line[3:].strip() if len(line) > 3 else line.strip()
            if path:
                changed_paths.append(path)
        if not changed_paths:
            return True
        result = await publish_repo_files(
            project,
            repo_root=root,
            changed_paths=changed_paths,
            commit_message=message,
        )
        if project.get("_id"):
            await record_publish_success(project["_id"], result)
        return True
    except Exception as exc:
        log.warning("connector git sync error: %s", exc)
        if project.get("_id"):
            await record_publish_failure(project["_id"], str(exc))
        return False
