from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from app.services.convex_client import convex
from app.services.role_runtime_service import ROLE_ALIASES

logger = logging.getLogger(__name__)


ACTIVE_STATUSES = {"queued", "running", "awaiting_input", "awaiting_approval", "paused"}
SESSION_STATUSES = ACTIVE_STATUSES | {"completed", "failed", "cancelled", "blocked"}
RUNNER_NAMES = {"jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli"}
LEGACY_SESSION_STATUS_ALIASES = {
    "done": "completed",
}
_LOCAL_RUNNING_AGENTS: dict[str, dict[str, Any]] = {}


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


def _normalize_runner_name(runner: str | None, *, strict: bool = False) -> str | None:
    if runner in {None, ""}:
        return None
    normalized = str(runner).strip().lower()
    if normalized in RUNNER_NAMES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported running-agent runner: {runner}")
    return runner


def _session_status_has_drift(status: str | None) -> bool:
    normalized = _normalize_session_status(status)
    return normalized is not None and normalized != status


def _session_role_has_drift(role: str | None) -> bool:
    normalized = _normalize_role_alias(role)
    return normalized is not None and normalized != role


def _session_runner_has_drift(runner: str | None) -> bool:
    normalized = _normalize_runner_name(runner)
    return normalized is not None and normalized != runner


def _normalize_session_record(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return session
    normalized_role = _normalize_role_alias(session.get("role"))
    normalized_status = _normalize_session_status(session.get("status"))
    normalized_runner = _normalize_runner_name(session.get("runner"))
    if (
        normalized_role == session.get("role")
        and normalized_status == session.get("status")
        and normalized_runner == session.get("runner")
    ):
        return session
    return dict(session) | {"role": normalized_role, "status": normalized_status, "runner": normalized_runner}


def _make_local_running_agent_record(
    *,
    session_id: str,
    project_id: str | None,
    project_slug: str | None,
    task_id: str | None,
    runtime_kind: str,
    role: str,
    title: str,
    external_session_id: str | None,
    session_path: str | None,
    status: str,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "_id": session_id,
        "projectId": project_id,
        "projectSlug": project_slug,
        "taskId": task_id,
        "runner": runtime_kind,
        "role": role,
        "title": title,
        "externalSessionId": external_session_id or "",
        "sessionPath": session_path or "",
        "status": status,
        "startedAt": now_ms,
        "lastHeartbeatAt": now_ms,
    }


def _store_local_running_agent(record: dict[str, Any]) -> str:
    session_id = str(record.get("_id") or "")
    if not session_id:
        raise ValueError("Local running-agent record requires _id")
    _LOCAL_RUNNING_AGENTS[session_id] = record
    return session_id


def _merge_cached_session_record(session_id: str, session: dict[str, Any] | None) -> dict[str, Any] | None:
    cached = _LOCAL_RUNNING_AGENTS.get(session_id)
    if not cached and not session:
        return None
    if not cached:
        return _normalize_session_record(session)
    if not session:
        return _normalize_session_record(dict(cached))
    merged = dict(cached)
    merged.update({k: v for k, v in session.items() if v is not None})
    _LOCAL_RUNNING_AGENTS[session_id] = merged
    return _normalize_session_record(merged)


async def _safe_list_sessions(project_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    try:
        return await convex.query("agent:listByProjectId", {"projectId": project_id, "limit": limit}) or []
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("running_agent_service: transient Convex failure listing sessions for %s: %s", project_id, exc)
        return []


async def list_running_agent_status_drift(project_id: str, *, limit: int = 50) -> list[dict[str, str]]:
    sessions = await _safe_list_sessions(project_id, limit=limit)
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


async def list_running_agent_role_drift(project_id: str, *, limit: int = 50) -> list[dict[str, str]]:
    sessions = await _safe_list_sessions(project_id, limit=limit)
    drifted: list[dict[str, str]] = []
    for session in sessions:
        raw_role = session.get("role")
        normalized_role = _normalize_role_alias(raw_role)
        if not _session_role_has_drift(raw_role) or normalized_role is None:
            continue
        drifted.append(
            {
                "sessionId": str(session.get("_id") or ""),
                "role": str(raw_role),
                "canonicalRole": normalized_role,
            }
        )
    return drifted


async def list_running_agent_runner_drift(project_id: str, *, limit: int = 50) -> list[dict[str, str]]:
    sessions = await _safe_list_sessions(project_id, limit=limit)
    drifted: list[dict[str, str]] = []
    for session in sessions:
        raw_runner = session.get("runner")
        normalized_runner = _normalize_runner_name(raw_runner)
        if not _session_runner_has_drift(raw_runner) or normalized_runner is None:
            continue
        drifted.append(
            {
                "sessionId": str(session.get("_id") or ""),
                "runner": str(raw_runner),
                "canonicalRunner": normalized_runner,
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


async def repair_running_agent_role_drift(project_id: str, *, limit: int = 50) -> dict[str, list[str]]:
    repaired_session_ids: list[str] = []
    for session in await list_running_agent_role_drift(project_id, limit=limit):
        session_id = str(session.get("sessionId") or "")
        canonical_role = str(session.get("canonicalRole") or "")
        if not session_id or not canonical_role:
            continue
        await convex.mutation(
            "agent:updateSession",
            {
                "sessionId": session_id,
                "role": canonical_role,
            },
        )
        repaired_session_ids.append(session_id)
    return {"repairedSessionIds": repaired_session_ids}


async def repair_running_agent_runner_drift(project_id: str, *, limit: int = 50) -> dict[str, list[str]]:
    repaired_session_ids: list[str] = []
    for session in await list_running_agent_runner_drift(project_id, limit=limit):
        session_id = str(session.get("sessionId") or "")
        canonical_runner = str(session.get("canonicalRunner") or "")
        if not session_id or not canonical_runner:
            continue
        await convex.mutation(
            "agent:updateSession",
            {
                "sessionId": session_id,
                "runner": canonical_runner,
            },
        )
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
    runtime_kind = _normalize_runner_name(runtime_kind, strict=True) or "codex_cli"
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
    try:
        result = await convex.mutation("agent:createSession", payload)
        session_id = result["sessionId"]
        _store_local_running_agent(
            _make_local_running_agent_record(
                session_id=session_id,
                project_id=project_id,
                project_slug=project_slug,
                task_id=task_id,
                runtime_kind=runtime_kind,
                role=role,
                title=title,
                external_session_id=external_session_id,
                session_path=session_path,
                status=status,
            )
        )
        return session_id
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("running_agent_service: falling back to local running-agent state after Convex failure: %s", exc)
        local_session_id = f"local_runner_{uuid.uuid4().hex[:12]}"
        return _store_local_running_agent(
            _make_local_running_agent_record(
                session_id=local_session_id,
                project_id=project_id,
                project_slug=project_slug,
                task_id=task_id,
                runtime_kind=runtime_kind,
                role=role,
                title=title,
                external_session_id=external_session_id,
                session_path=session_path,
                status=status,
            )
        )


async def update_running_agent(session_id: str, **fields: Any) -> None:
    if session_id in _LOCAL_RUNNING_AGENTS:
        current = dict(_LOCAL_RUNNING_AGENTS[session_id])
        if "status" in fields and fields["status"] is not None:
            current["status"] = _normalize_session_status(fields["status"], strict=True)
        if fields.get("externalSessionId") is not None:
            current["externalSessionId"] = fields["externalSessionId"]
        if fields.get("endedAt") is not None:
            current["endedAt"] = fields["endedAt"]
        current["lastHeartbeatAt"] = int(time.time() * 1000)
        _LOCAL_RUNNING_AGENTS[session_id] = current
        if session_id.startswith("local_runner_"):
            return
    # Convex updateSessionState accepts: status, externalSessionId, endedAt,
    # actualCostUsd, estimatedCostUsd. All other fields are silently dropped.
    _allowed = {"status", "externalSessionId", "endedAt", "actualCostUsd", "estimatedCostUsd"}
    patch = {k: v for k, v in fields.items() if k in _allowed and v is not None}
    if "status" in patch:
        patch["status"] = _normalize_session_status(patch.get("status"), strict=True)
    try:
        await convex.mutation("agent:updateSessionState", {"sessionId": session_id, **patch})
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("running_agent_service: using cached running-agent state after Convex update failure for %s: %s", session_id, exc)


async def get_running_agent(session_id: str) -> dict[str, Any] | None:
    if session_id in _LOCAL_RUNNING_AGENTS:
        if session_id.startswith("local_runner_"):
            return _normalize_session_record(dict(_LOCAL_RUNNING_AGENTS[session_id]))
    try:
        return _merge_cached_session_record(session_id, await convex.query("agent:getSession", {"sessionId": session_id}))
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("running_agent_service: using cached running-agent state after Convex get failure for %s: %s", session_id, exc)
        return _normalize_session_record(dict(_LOCAL_RUNNING_AGENTS[session_id])) if session_id in _LOCAL_RUNNING_AGENTS else None


async def list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    sessions_by_id: dict[str, dict[str, Any]] = {}
    for item in await _safe_list_sessions(project_id, limit=limit):
        session_id = str(item.get("_id") or "")
        normalized = _merge_cached_session_record(session_id, item) if session_id else (_normalize_session_record(item) or item)
        if session_id:
            sessions_by_id[session_id] = normalized or item
    for item in _LOCAL_RUNNING_AGENTS.values():
        if item.get("projectId") != project_id:
            continue
        session_id = str(item.get("_id") or "")
        if not session_id:
            continue
        sessions_by_id[session_id] = _normalize_session_record(dict(item)) or dict(item)
    sessions = list(sessions_by_id.values())
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
    if session_id in _LOCAL_RUNNING_AGENTS:
        await update_running_agent(session_id, status=status, endedAt=ended_at or int(time.time() * 1000))
        return
    await update_running_agent(session_id, status=status, endedAt=ended_at or int(time.time() * 1000))
    try:
        await convex.mutation("agent:deleteSession", {"sessionId": session_id})
    except Exception:
        # Older backends may not yet support deletion; the active-only filter
        # keeps finished sessions out of the live control plane.
        pass
