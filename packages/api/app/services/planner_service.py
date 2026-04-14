from __future__ import annotations

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
    project = await convex.query("projects:getBySlug", {"slug": slug})
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


_STATUS_EVENT_MAP: dict[str, str] = {
    "ready": "moved_to_ready",
    "awaiting_approval": "approval_requested",
    "running": "runner_started",
    "blocked": "blocked",
    "review": "verification_passed",
    "done": "done",
    "cancelled": "cancelled",
}


async def update_task(task_id: str, **fields) -> None:
    patch = {k: v for k, v in fields.items() if v is not None}
    new_status = patch.pop("status", None)

    if new_status:
        # Use atomic transition mutation: updates status + appends event in one call.
        event_type = _STATUS_EVENT_MAP.get(new_status, "status_changed")
        await convex.mutation(
            "tasks:transition",
            {
                "taskId": task_id,
                "newStatus": new_status,
                "eventType": event_type,
                "eventPayload": {"status": new_status},
            },
        )

    if patch:
        await convex.mutation("tasks:update", {"taskId": task_id, **patch})


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

    from rail.planner_sync import PlannerSync
    syncer = PlannerSync(root)

    board = board or await ensure_main_board(project["_id"])
    tasks = await list_tasks(board["_id"])
    plan_root = root / "research_plan"

    # current_plan.md — not managed by PlannerSync
    _write_file(plan_root / "current_plan.md", _current_plan_markdown(project, tasks))

    # task_board.md and per-task files — delegate to PlannerSync
    syncer.mirror_board(board, tasks)

    for task in tasks:
        rel_path = syncer.mirror_task(task)
        await convex.mutation(
            "tasks:update",
            {
                "taskId": task["_id"],
                "gitSnapshotPath": rel_path,
            },
        )
