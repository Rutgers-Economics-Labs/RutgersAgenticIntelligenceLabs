from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.services.convex_client import convex
from app.services import session_files


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
]


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].rstrip("-") or "item"


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
        meta = {}
    return meta if isinstance(meta, dict) else {}, parts[1]


def get_project_by_slug_path(project_root: Path, slug: str) -> Path:
    return project_root / "research_plan" / "tasks" / f"{slug}.md"


async def get_project_by_slug(slug: str) -> dict:
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise ValueError(f"Project '{slug}' not found")
    return project


def project_root_from_record(project: dict) -> Path | None:
    local_repo_path = project.get("localRepoPath")
    if not local_repo_path:
        return None
    return Path(local_repo_path).resolve()


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
    project_id = project.get("_id") or project.get("projectId")
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


def _task_to_runtime(path: Path) -> dict[str, Any]:
    meta, body = _split_frontmatter(_read_text(path))
    title = meta.get("title") or path.stem.replace("-", " ").title()
    task_id = meta.get("task_id") or path.stem
    # Strip the "## Description\n\n" header that _render_task_markdown adds,
    # to avoid it accumulating on every read/write cycle.
    description = body.strip()
    if description.startswith("## Description"):
        description = description[len("## Description"):].lstrip("\n").strip()
    return {
        "_id": task_id,
        "boardId": "main",
        "title": title,
        "description": description,
        "status": meta.get("status", "backlog"),
        "agentRole": meta.get("assigned_role") or meta.get("agent_role") or "planner",
        "repoPaths": meta.get("related_files") or [],
        "acceptanceCriteria": meta.get("acceptance_criteria") or [],
        "dependsOnTaskIds": meta.get("dependencies") or [],
        "approvalState": meta.get("approval_state") or None,
        "priority": meta.get("priority") or None,
        "runner": meta.get("runner") or None,
        "gitSnapshotPath": str(path.relative_to(path.parents[2])),
        "latestRunSummary": meta.get("latest_run_summary") or "Not started",
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
    tasks = [_task_to_runtime(path) for path in sorted(task_dir.glob("*.md"))]
    return tasks


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
        "repoPaths": repo_paths or [],
        "acceptanceCriteria": acceptance_criteria or [],
        "dependsOnTaskIds": depends_on_task_ids or [],
        "approvalState": approval_state,
        "gitSnapshotPath": git_snapshot_path or f"research_plan/tasks/{task_id}.md",
        "latestRunSummary": "Not started",
    }
    _write_file(path, _render_task_markdown(task))
    return task


async def update_task(task_id: str, *, project: dict, **fields) -> dict | None:
    root = project_root_from_record(project)
    if root is None:
        return None
    path = _task_root(root) / f"{task_id}.md"
    if not path.exists():
        return None
    task = _task_to_runtime(path)
    patch = {k: v for k, v in fields.items() if v is not None}
    mapping = {
        "title": "title",
        "description": "description",
        "status": "status",
        "priority": "priority",
        "runner": "runner",
        "repoPaths": "repoPaths",
        "acceptanceCriteria": "acceptanceCriteria",
        "approvalState": "approvalState",
        "gitSnapshotPath": "gitSnapshotPath",
        "latestRunSummary": "latestRunSummary",
    }
    for key, value in patch.items():
        target = mapping.get(key, key)
        if target in task:
            task[target] = value
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
        "approvalType": meta.get("approval_type", "run_task"),
        "status": meta.get("status", "pending"),
        "requestedByRole": meta.get("requested_by_role", "planner"),
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
    next_tasks = [f"- {task['title']}" for task in tasks if task.get("status") in {"ready", "awaiting_approval", "running"}]
    if not next_tasks:
        next_tasks = ["- Define the next execution step"]
    return (
        f"# Current Plan\n\n"
        f"Project: {project['name']}\n\n"
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

    board = board or await ensure_main_board(project)
    tasks = await list_tasks(board["_id"], project=project)
    approvals = await list_approvals(project)
    plan_root = root / "research_plan"

    _write_file(plan_root / "current_plan.md", _current_plan_markdown(project, tasks))
    syncer.mirror_board(board, tasks)
    for task in tasks:
        syncer.mirror_task(task)
    _write_file(plan_root / "approvals.md", _render_approvals_index(approvals))
    _write_file(plan_root / "blockers.md", _render_blockers(root))
