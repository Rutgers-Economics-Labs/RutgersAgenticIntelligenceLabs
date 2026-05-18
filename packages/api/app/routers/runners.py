"""
/api/v1/runners — HTTP surface for the runner abstraction layer.

Provides endpoints so the planner, dashboard, and automation scripts can
drive runner sessions through a single, vendor-agnostic API rather than
importing adapter classes directly.

Routes:
    GET  /runners                                              list available adapters
    POST /runners/{runner}/sessions                            create_session
    GET  /runners/{runner}/sessions/{session_id}               get_session
    GET  /runners/{runner}/sessions/{session_id}/events        list_events (normalized)
    POST /runners/{runner}/sessions/{session_id}/messages      send_message
    POST /runners/{runner}/sessions/{session_id}/approve       approve
    POST /runners/{runner}/sessions/{session_id}/cancel        cancel
    POST /runners/{runner}/sessions/{session_id}/ingest-events fetch + persist events to Convex
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Path as FPath
from pydantic import BaseModel

router = APIRouter(prefix="/runners", tags=["runners"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    project_slug: str
    role: str
    task_id: str
    repo_url: str
    local_repo_path: str | None = None
    branch: str = "main"
    task_description: str
    allowed_paths: list[str] = []
    allowed_secrets: dict[str, str] = {}
    acceptance_criteria: list[str] = []

    # Optional Convex IDs — recorded against the session in Convex when provided
    convex_task_id: str | None = None
    convex_agent_session_id: str | None = None


class SendMessageRequest(BaseModel):
    message: str


class ApproveRequest(BaseModel):
    message: str | None = None
    granted_by_user_id: str | None = None


class IngestEventsRequest(BaseModel):
    """Optionally link the persisted events to a Convex agent_session row."""
    convex_agent_session_id: str | None = None
    debug_only: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_runner(runner_name: str):
    """Resolve the runner adapter or raise HTTP 400/503."""
    from app.runners.factory import RunnerFactory

    try:
        return RunnerFactory.get(runner_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


async def _launch_blocker_for_project_session(
    *,
    project_slug: str,
    role: str,
    task_description: str,
) -> str | None:
    from app.runners import session_lifecycle
    from app.services import planner_service, running_agent_service
    from app.services.auditor_service import build_auditor_statuses

    project = await planner_service.get_project_by_slug(project_slug)
    if not project:
        return None
    active_sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    auditors = await build_auditor_statuses(project, active_sessions=active_sessions)
    return session_lifecycle._runner_launch_blocked_by_auditors(role, task_description, auditors)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_runners():
    """Return metadata for all registered runner adapters."""
    from app.runners.factory import RunnerFactory
    return {"runners": RunnerFactory.list_runners()}


@router.post("/{runner}/sessions")
async def create_session(
    runner: str = FPath(..., description="Runner name, e.g. 'jules'"),
    data: CreateSessionRequest = Body(...),
) -> dict[str, Any]:
    """Create a new runner session for the given task payload.

    On success, returns the vendor-assigned session metadata
    (``session_id``, ``status``, optional ``url``).
    """
    from app.runners.base import TaskPayload

    adapter = _get_runner(runner)
    blocker = await _launch_blocker_for_project_session(
        project_slug=data.project_slug,
        role=data.role,
        task_description=data.task_description,
    )
    if blocker:
        raise HTTPException(status_code=409, detail=blocker)
    payload = TaskPayload(
        project_slug=data.project_slug,
        role=data.role,
        task_id=data.task_id,
        repo_url=data.repo_url,
        local_repo_path=data.local_repo_path,
        branch=data.branch,
        task_description=data.task_description,
        allowed_paths=data.allowed_paths,
        allowed_secrets=data.allowed_secrets,
        acceptance_criteria=data.acceptance_criteria,
    )
    try:
        result = await adapter.create_session(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")

    # Persist a lightweight record in Convex if a task or session ID was provided.
    if data.convex_task_id or data.convex_agent_session_id:
        try:
            from app.services.convex_client import convex
            from app.runners.base import RunnerEvent, RunnerEventType

            event = RunnerEvent(
                event_type=RunnerEventType.SESSION_CREATED,
                session_id=result["session_id"],
                normalized_payload={
                    "runner": runner,
                    "task_id": data.task_id,
                    "status": result.get("status"),
                    "url": result.get("url"),
                },
                raw_payload=result.get("raw", {}),
            )
            await convex.mutation(
                "runnerEvents:append",
                {
                    "agentSessionId": data.convex_agent_session_id,
                    **event.to_convex_dict(),
                    "createdAt": int(time.time() * 1000),
                },
            )
        except Exception:
            pass  # event persistence is best-effort; don't fail the session creation

    return result


@router.get("/{runner}/sessions/{session_id}")
async def get_session(
    runner: str = FPath(...),
    session_id: str = FPath(...),
) -> dict[str, Any]:
    """Return current session metadata and status."""
    adapter = _get_runner(runner)
    try:
        return await adapter.get_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")


@router.get("/{runner}/sessions/{session_id}/events")
async def list_events(
    runner: str = FPath(...),
    session_id: str = FPath(...),
) -> dict[str, Any]:
    """Fetch and return normalized events for a session.

    All events are returned as RunnerEvent dicts (``event_type``,
    ``session_id``, ``normalized_payload``, ``debug_visibility``).
    Raw vendor payloads are omitted from the default response; use
    ``/ingest-events`` to persist the full payload in Convex.
    """
    adapter = _get_runner(runner)
    try:
        events = await adapter.list_events(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")

    return {
        "session_id": session_id,
        "runner": runner,
        "events": [
            {
                "event_type": e.event_type.value,
                "session_id": e.session_id,
                "normalized_payload": e.normalized_payload,
                "debug_visibility": e.debug_visibility,
            }
            for e in events
        ],
    }


@router.post("/{runner}/sessions/{session_id}/messages")
async def send_message(
    runner: str = FPath(...),
    session_id: str = FPath(...),
    data: SendMessageRequest = Body(...),
) -> dict[str, Any]:
    """Relay a human message or question answer to the runner."""
    adapter = _get_runner(runner)
    try:
        await adapter.send_message(session_id, data.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")
    return {"ok": True, "session_id": session_id}


@router.post("/{runner}/sessions/{session_id}/approve")
async def approve(
    runner: str = FPath(...),
    session_id: str = FPath(...),
    data: ApproveRequest = Body(default_factory=ApproveRequest),
) -> dict[str, Any]:
    """Signal human approval for a pending gate (plan approval / task start).

    Optionally record the approval in Convex if an ``approvalId`` is provided.
    """
    adapter = _get_runner(runner)
    payload: dict[str, Any] = {}
    if data.message:
        payload["message"] = data.message
    if data.granted_by_user_id:
        payload["granted_by_user_id"] = data.granted_by_user_id
    try:
        await adapter.approve(session_id, payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")
    return {"ok": True, "session_id": session_id}


@router.post("/{runner}/sessions/{session_id}/cancel")
async def cancel(
    runner: str = FPath(...),
    session_id: str = FPath(...),
) -> dict[str, Any]:
    """Request cancellation of an in-progress session.

    Records a CANCELLED event in Convex (best-effort).
    Jules has no native cancel endpoint; the adapter records the intent only.
    """
    adapter = _get_runner(runner)
    try:
        await adapter.cancel(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error: {e}")

    # Persist cancellation event (best-effort)
    try:
        from app.services.convex_client import convex
        from app.runners.base import RunnerEvent, RunnerEventType

        event = RunnerEvent(
            event_type=RunnerEventType.CANCELLED,
            session_id=session_id,
            normalized_payload={"runner": runner, "reason": "user_requested"},
            raw_payload={},
        )
        await convex.mutation(
            "runnerEvents:append",
            {
                **event.to_convex_dict(),
                "createdAt": int(time.time() * 1000),
            },
        )
    except Exception:
        pass

    return {"ok": True, "session_id": session_id, "status": "cancelled"}


@router.post("/{runner}/sessions/{session_id}/ingest-events")
async def ingest_events(
    runner: str = FPath(...),
    session_id: str = FPath(...),
    data: IngestEventsRequest = Body(default_factory=IngestEventsRequest),
) -> dict[str, Any]:
    """Fetch all current events from the runner, normalize them, and persist
    them into the Convex ``runnerEvents`` table.

    This endpoint bridges the runner adapter and the operational database:
    the planner can call it after any session activity to ensure the DB stays
    in sync with the vendor event stream.

    Returns the number of events persisted and a summary list.
    """
    adapter = _get_runner(runner)
    try:
        events = await adapter.list_events(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Runner error fetching events: {e}")

    if data.debug_only:
        events = [e for e in events if e.debug_visibility]

    persisted: list[dict[str, Any]] = []
    try:
        from app.services.convex_client import convex
        for event in events:
            try:
                await convex.mutation(
                    "runnerEvents:append",
                    {
                        "agentSessionId": data.convex_agent_session_id,
                        **event.to_convex_dict(),
                        "createdAt": int(time.time() * 1000),
                    },
                )
                persisted.append({
                    "event_type": event.event_type.value,
                    "debug_visibility": event.debug_visibility,
                })
            except Exception as persist_err:
                persisted.append({
                    "event_type": event.event_type.value,
                    "error": str(persist_err),
                })
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Convex persistence error: {e}")

    return {
        "session_id": session_id,
        "runner": runner,
        "ingested": len(persisted),
        "events": persisted,
    }
