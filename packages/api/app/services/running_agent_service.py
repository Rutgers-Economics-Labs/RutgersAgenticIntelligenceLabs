from __future__ import annotations

import time
from typing import Any

from app.services.convex_client import convex
from app.services.role_runtime_service import ROLE_ALIASES


ACTIVE_STATUSES = {"queued", "running", "awaiting_input", "awaiting_approval", "paused"}
SESSION_STATUSES = ACTIVE_STATUSES | {"completed", "failed", "cancelled", "blocked"}
LEGACY_SESSION_STATUS_ALIASES = {
    "done": "completed",
}


def _normalize_role_alias(role: str | None) -> str | None:
    if role in {None, ""}:
        return None
    normalized = str(role).strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def _normalize_session_status(status: str | None, *, strict: bool = False) -> str | None:
    if status in {None, ""}:
        return None
    normalized = str(status).strip().lower()
    normalized = LEGACY_SESSION_STATUS_ALIASES.get(normalized, normalized)
    if normalized in SESSION_STATUSES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported running-agent status: {status}")
    return status


def _session_status_has_drift(status: str | None) -> bool:
    normalized = _normalize_session_status(status)
    return normalized is not None and normalized != status


def _normalize_session_record(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return session
    normalized_role = _normalize_role_alias(session.get("role"))
    normalized_status = _normalize_session_status(session.get("status"))
    if normalized_role == session.get("role") and normalized_status == session.get("status"):
        return session
    return dict(session) | {"role": normalized_role, "status": normalized_status}


async def list_running_agent_status_drift(project_id: str, *, limit: int = 50) -> list[dict[str, str]]:
    sessions = await convex.query("agent:listByProjectId", {"projectId": project_id, "limit": limit}) or []
    drifted: list[dict[str, str]] = []
    for session in sessions:
        raw_status = session.get("status")
        normalized_status = _normalize_session_status(raw_status)
        if not _session_status_has_drift(raw_status) or normalized_status is None:
            continue
        drifted.append(
            {
                "sessionId": str(session.get("_id") or ""),
                "status": str(raw_status),
                "canonicalStatus": normalized_status,
            }
        )
    return drifted


async def repair_running_agent_status_drift(project_id: str, *, limit: int = 50) -> dict[str, list[str]]:
    repaired_session_ids: list[str] = []
    for session in await list_running_agent_status_drift(project_id, limit=limit):
        session_id = str(session.get("sessionId") or "")
        canonical_status = str(session.get("canonicalStatus") or "")
        if not session_id or not canonical_status:
            continue
        await update_running_agent(session_id, status=canonical_status)
        repaired_session_ids.append(session_id)
    return {"repairedSessionIds": repaired_session_ids}


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
    role = _normalize_role_alias(role) or "agent"
    status = _normalize_session_status(status, strict=True) or "queued"
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
    if "status" in patch:
        patch["status"] = _normalize_session_status(patch.get("status"), strict=True)
    await convex.mutation("agent:updateSessionState", {"sessionId": session_id, **patch})


async def get_running_agent(session_id: str) -> dict[str, Any] | None:
    return _normalize_session_record(await convex.query("agent:getSession", {"sessionId": session_id}))


async def list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    sessions = [
        _normalize_session_record(item) or item
        for item in (await convex.query("agent:listByProjectId", {"projectId": project_id, "limit": limit}) or [])
    ]
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
