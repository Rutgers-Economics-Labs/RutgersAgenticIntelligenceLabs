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
    # Convex agent:createSession validator (from schema inspection):
    #   required: title, model
    #   optional: externalSessionId, projectId, projectSlug, role, runner, status, taskId
    #   NOT accepted: startedAt, lastHeartbeatAt, sessionPath (extra fields → 400)
    # taskId must be v.id("tasks") — omit for file-based slug IDs (contain hyphens)
    is_convex_id = task_id and "-" not in task_id
    payload: dict = {
        "title": title,
        "model": f"runtime:{runtime_kind}",
        "projectSlug": project_slug,
        "projectId": project_id,
        "role": role,
        "runner": runtime_kind,
        "externalSessionId": external_session_id or "",
        "status": status,
    }
    if is_convex_id:
        payload["taskId"] = task_id
    result = await convex.mutation("agent:createSession", payload)
    return result["sessionId"]


async def update_running_agent(session_id: str, **fields: Any) -> None:
    # Convex updateSessionState accepts: status, externalSessionId, endedAt,
    # actualCostUsd, estimatedCostUsd. All other fields are silently dropped.
    _allowed = {"status", "externalSessionId", "endedAt", "actualCostUsd", "estimatedCostUsd"}
    patch = {k: v for k, v in fields.items() if k in _allowed and v is not None}
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
