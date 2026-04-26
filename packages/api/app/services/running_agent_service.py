from __future__ import annotations

import time
from typing import Any

from app.services.convex_client import convex


ACTIVE_STATUSES = {"queued", "running", "awaiting_input", "awaiting_approval", "paused"}


async def create_running_agent(
    *,
    project_id: str | None,
    project_slug: str | None,
    task_id: str | None,
    runtime_kind: str,
    role: str,
    title: str,
    external_session_id: str | None = None,
    session_path: str | None = None,
    status: str = "queued",
) -> str:
    result = await convex.mutation(
        "agent:createSession",
        {
            "title": title,
            "model": f"runtime:{runtime_kind}",
            "projectSlug": project_slug,
            "projectId": project_id,
            "taskId": task_id,
            "role": role,
            "runner": runtime_kind,
            "externalSessionId": external_session_id or "",
            "status": status,
            "sessionPath": session_path,
            "startedAt": int(time.time() * 1000),
            "lastHeartbeatAt": int(time.time() * 1000),
        },
    )
    return result["sessionId"]


async def update_running_agent(session_id: str, **fields: Any) -> None:
    patch = {k: v for k, v in fields.items() if v is not None}
    patch["lastHeartbeatAt"] = int(time.time() * 1000)
    await convex.mutation("agent:updateSessionState", {"sessionId": session_id, **patch})


async def get_running_agent(session_id: str) -> dict[str, Any] | None:
    return await convex.query("agent:getSession", {"sessionId": session_id})


async def list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    sessions = await convex.query("agent:listByProjectId", {"projectId": project_id, "limit": limit}) or []
    if not active_only:
        return sessions
    return [item for item in sessions if item.get("status") in ACTIVE_STATUSES]


async def find_active_worker(project_id: str) -> dict[str, Any] | None:
    sessions = await list_project_running_agents(project_id, active_only=True, limit=50)
    for item in sessions:
        if item.get("role") not in {None, "planner"}:
            return item
    return None


async def finalize_running_agent(session_id: str, *, status: str, ended_at: int | None = None) -> None:
    await update_running_agent(session_id, status=status, endedAt=ended_at or int(time.time() * 1000))
    try:
        await convex.mutation("agent:deleteSession", {"sessionId": session_id})
    except Exception:
        # Older backends may not yet support deletion; the active-only filter
        # keeps finished sessions out of the live control plane.
        pass
