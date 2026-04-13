from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from app.services.convex_client import convex


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
]


async def get_project_by_slug(slug: str) -> dict:
    project = await convex.query("projects:get", {"slug": slug})
    if not project:
        raise ValueError(f"Project '{slug}' not found")
    return project


def project_root_from_record(project: dict) -> Path | None:
    local_repo_path = project.get("localRepoPath")
    if not local_repo_path:
        return None
    return Path(local_repo_path).resolve()


async def ensure_planner_thread(project_id: str) -> str:
    # We model the long-lived thread by a stable logical thread_id and message stream.
    return PLANNER_THREAD_ID


async def append_planner_message(
    *,
    project_id: str,
    role: str,
    content: str,
    message_type: str = "chat",
    session_id: str | None = None,
    thread_id: str = PLANNER_THREAD_ID,
) -> Any:
    return await convex.mutation(
        "plannerMessages:append",
        {
            "projectId": project_id,
            "sessionId": session_id,
            "threadId": thread_id,
            "role": role,
            "content": content,
            "messageType": message_type,
        },
    )


async def list_planner_messages(project_id: str, thread_id: str = PLANNER_THREAD_ID, limit: int = 200) -> list[dict]:
    return await convex.query(
        "plannerMessages:listByProjectThread",
        {"projectId": project_id, "threadId": thread_id, "limit": limit},
    ) or []


async def ensure_main_board(project_id: str, session_id: str | None = None) -> dict:
    boards = await convex.query("taskBoards:listByProject", {"projectId": project_id}) or []
    if boards:
        return boards[0]
    board_id = await convex.mutation(
        "taskBoards:create",
        {
            "projectId": project_id,
            "sessionId": session_id,
            "title": DEFAULT_BOARD_TITLE,
            "status": "active",
        },
    )
    boards = await convex.query("taskBoards:listByProject", {"projectId": project_id}) or []
    for board in boards:
        if board["_id"] == board_id:
            return board
    raise RuntimeError("Failed to create planner task board")


async def list_tasks(board_id: str) -> list[dict]:
    return await convex.query("tasks:listByBoard", {"boardId": board_id}) or []


async def create_task(
    *,
    board_id: str,
    project_id: str,
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
    task_id = await convex.mutation(
        "tasks:create",
        {
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
            "gitSnapshotPath": git_snapshot_path,
        },
    )
    await convex.mutation(
        "taskEvents:append",
        {
            "taskId": task_id,
            "eventType": "created",
            "payload": {"status": status, "agentRole": agent_role},
        },
    )
    tasks = await list_tasks(board_id)
    for task in tasks:
        if task["_id"] == task_id:
            return task
    raise RuntimeError("Failed to create planner task")


async def update_task(task_id: str, **fields) -> None:
    patch = {k: v for k, v in fields.items() if v is not None}
    await convex.mutation("tasks:update", {"taskId": task_id, **patch})
    if "status" in patch:
        await convex.mutation(
            "taskEvents:append",
            {
                "taskId": task_id,
                "eventType": "status_changed",
                "payload": {"status": patch["status"]},
            },
        )


def _task_slug(task: dict) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in task["title"])
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "task"


def _task_file_markdown(task: dict) -> str:
    deps = "\n".join(f"  - {dep}" for dep in task.get("dependsOnTaskIds", [])) or "  []"
    criteria = "\n".join(f"  - {item}" for item in task.get("acceptanceCriteria", [])) or "  []"
    files = "\n".join(f"  - {item}" for item in task.get("repoPaths", [])) or "  []"
    latest = task.get("status", "unknown")
    return (
        f"---\n"
        f"title: {task['title']}\n"
        f"status: {task.get('status', 'backlog')}\n"
        f"assigned_role: {task.get('agentRole', '')}\n"
        f"dependencies:\n{deps}\n"
        f"acceptance_criteria:\n{criteria}\n"
        f"related_files:\n{files}\n"
        f"latest_run_summary: \"{latest}\"\n"
        f"---\n\n"
        f"## Description\n\n{task.get('description', '').strip() or 'No description provided.'}\n"
    )


def _task_board_markdown(tasks: list[dict]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        grouped[task.get("status", "backlog")].append(f"- {task['title']}")

    sections: list[str] = ["# Task Board", ""]
    for status in TASK_STATUSES:
        sections.append(f"## {status.replace('_', ' ').title()}")
        sections.append("")
        lines = grouped.get(status) or ["None."]
        sections.extend(lines)
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


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


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def sync_planner_files(project: dict, board: dict | None = None) -> None:
    root = project_root_from_record(project)
    if root is None:
        return

    board = board or await ensure_main_board(project["_id"])
    tasks = await list_tasks(board["_id"])
    plan_root = root / "research_plan"
    tasks_root = plan_root / "tasks"
    tasks_root.mkdir(parents=True, exist_ok=True)

    _write_file(plan_root / "current_plan.md", _current_plan_markdown(project, tasks))
    _write_file(plan_root / "task_board.md", _task_board_markdown(tasks))

    for task in tasks:
        task_path = tasks_root / f"{_task_slug(task)}.md"
        _write_file(task_path, _task_file_markdown(task))
        await convex.mutation(
            "tasks:update",
            {
                "taskId": task["_id"],
                "gitSnapshotPath": str(task_path.relative_to(root)),
            },
        )
