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

from fastapi import APIRouter, Body, HTTPException, Path as FPath, Query
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
    """Return metadata for all registered runner adapters.

    Combines three layers:
      - factory registration (which adapter classes exist)
      - static profile (capability declarations from YAML)
      - dynamic probe (installed? authenticated? versioned?)

    Profile and probe are optional in the response — a runner registered in
    the factory but missing a profile YAML still shows up, just without
    capability/readiness info. That way operators can see a registered-but-
    unprofiled state explicitly instead of silently dropping it.
    """
    from app.runners.factory import RunnerFactory
    from app.runners.profile_loader import load_all_profiles
    from app.runners.probe import probe_all

    registered = {item["name"]: item for item in RunnerFactory.list_runners()}
    profiles = load_all_profiles()
    probes = await probe_all()

    rows: list[dict[str, Any]] = []
    names = sorted(set(registered.keys()) | set(profiles.keys()))
    for name in names:
        row: dict[str, Any] = {
            "name": name,
            "registered": name in registered,
            "description": (registered.get(name) or {}).get("description", ""),
        }
        profile = profiles.get(name)
        if profile is not None:
            row["profile"] = profile.model_dump(mode="json")
        probe = probes.get(name)
        if probe is not None:
            row["probe"] = probe.model_dump(mode="json")
        rows.append(row)
    return {"runners": rows}


@router.get("/{runner}/probe")
async def probe_runner_endpoint(
    runner: str = FPath(..., description="Runner name, e.g. 'claude_code'"),
) -> dict[str, Any]:
    """Run a fresh probe for one runner. Cheap; safe to call from UI on demand.

    Probes do not make outbound API calls — they check command presence,
    version, and credential env vars. Authentication is not verified to
    avoid burning API budget on every UI tick.
    """
    from app.runners.probe import probe_runner as _probe

    result = await _probe(runner)
    if result is None:
        raise HTTPException(status_code=404, detail=f"no profile for runner {runner!r}")
    return result.model_dump(mode="json")


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


@router.get("/sessions/{session_id}/work-order")
async def get_work_order(
    session_id: str = FPath(...),
    project_slug: str = Query(...),
) -> dict[str, Any]:
    """Fetch the typed WorkOrder for a session."""
    from app.services import running_agent_service, planner_service
    from pathlib import Path
    import json

    agent_session = await running_agent_service.get_running_agent(session_id)
    
    # In Phase 2, we wrote work orders to research_plan/work_orders/<wo_id>.json
    # and recorded work_order_id in the session state on disk.
    
    project = await planner_service.get_project_by_slug(project_slug)
    if not project or not project.get("localRepoPath"):
        raise HTTPException(status_code=404, detail="Project or local path not found")
    
    project_root = Path(project["localRepoPath"])
    
    # Try to find the session directory to get the work order ID
    role = (agent_session or {}).get("role", "research")
    from app.services import session_files
    session_root = session_files.session_root(project_root, role, session_id)
    
    work_order_id = None
    if session_root.exists():
        state = session_files.read_state(session_root)
        work_order_id = state.get("work_order_id")
        
    if not work_order_id:
        # Fallback: check if we can derive it from the agent_session title or metadata
        # if it was recorded there. For now, if we can't find it, we fail.
        raise HTTPException(status_code=404, detail="Session has no work order ID associated")

    wo_path = project_root / "research_plan" / "work_orders" / f"{work_order_id}.json"
    
    if not wo_path.exists():
        raise HTTPException(status_code=404, detail=f"Work order file not found: {work_order_id}")
    
    return json.loads(wo_path.read_text(encoding="utf-8"))


@router.get("/sessions/{session_id}/dispatch-decision")
async def get_dispatch_decision(
    session_id: str = FPath(...),
    project_slug: str = Query(...),
) -> dict[str, Any]:
    """Fetch the dispatch decision log for a session."""
    from app.services import running_agent_service, planner_service, session_files
    from pathlib import Path
    import json

    try:
        agent_session = await running_agent_service.get_running_agent(session_id)
    except Exception:
        agent_session = None

    project = await planner_service.get_project_by_slug(project_slug)
    if not project or not project.get("localRepoPath"):
        raise HTTPException(status_code=404, detail="Project or local path not found")
    
    project_root = Path(project["localRepoPath"])
    
    role = (agent_session or {}).get("role", "research")
    session_root = session_files.session_root(project_root, role, session_id)
    
    if not session_root.exists():
        sessions_root = project_root / "research_plan" / "sessions"
        if sessions_root.exists():
            for candidate in sessions_root.glob(f"*/{session_id}"):
                if candidate.exists():
                    session_root = candidate
                    break

    work_order_id = None
    if session_root.exists():
        state = session_files.read_state(session_root)
        work_order_id = state.get("work_order_id")
        
    if not work_order_id and agent_session:
        work_order_id = agent_session.get("work_order_id")
        
    if not work_order_id:
        raise HTTPException(status_code=404, detail="Session has no work order ID associated")
        
    dispatch_path = project_root / "research_plan" / "dispatch_log" / f"{work_order_id}.json"
    if not dispatch_path.exists():
        raise HTTPException(status_code=404, detail=f"Dispatch decision file not found for work order: {work_order_id}")
        
    try:
        return json.loads(dispatch_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse dispatch decision: {e}")


@router.get("/sessions/{session_id}/result")
async def get_session_result(
    session_id: str = FPath(...),
    project_slug: str = Query(...),
) -> dict[str, Any]:
    """Fetch the session result for a finished session."""
    from app.services import running_agent_service, planner_service, session_files
    from app.runners.contracts.session_result import SessionResult
    from pathlib import Path
    import json

    try:
        agent_session = await running_agent_service.get_running_agent(session_id)
    except Exception:
        agent_session = None

    project = await planner_service.get_project_by_slug(project_slug)
    if not project or not project.get("localRepoPath"):
        raise HTTPException(status_code=404, detail="Project or local path not found")
    
    project_root = Path(project["localRepoPath"])
    
    role = (agent_session or {}).get("role", "research")
    session_root = session_files.session_root(project_root, role, session_id)
    
    if not session_root.exists():
        sessions_root = project_root / "research_plan" / "sessions"
        if sessions_root.exists():
            for candidate in sessions_root.glob(f"*/{session_id}"):
                if candidate.exists():
                    session_root = candidate
                    break

    if not session_root.exists():
        raise HTTPException(status_code=404, detail="Session directory not found")
        
    result_path = session_root / "session_result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Session result file not found")
        
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session result JSON: {e}")
        
    try:
        SessionResult.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Session result file does not match SessionResult schema: {e}")
        
    return data


@router.post("/sessions/{session_id}/result")
async def submit_session_result(
    session_id: str = FPath(...),
    project_slug: str = Query(...),
    result: dict = Body(...),
) -> dict[str, Any]:
    """Submit the final session result."""
    from app.services import running_agent_service, session_files, planner_service
    from pathlib import Path
    import json

    agent_session = await running_agent_service.get_running_agent(session_id)
    project = await planner_service.get_project_by_slug(project_slug)
    if not project or not project.get("localRepoPath"):
        raise HTTPException(status_code=404, detail="Project or local path not found")
    
    project_root = Path(project["localRepoPath"])
    role = (agent_session or {}).get("role", "research")
    
    session_root = session_files.session_root(project_root, role, session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    
    (session_root / "session_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    
    return {"ok": True, "path": str(session_root / "session_result.json")}


@router.post("/sessions/{session_id}/ask")
async def ask_question(
    session_id: str = FPath(...),
    project_slug: str = Query(...),
    data: dict = Body(...),
) -> dict[str, Any]:
    """Ask a question to the planner mid-session."""
    question = data.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    from app.services import running_agent_service, planner_answer_service
    from app.runners.base import RunnerEvent, RunnerEventType
    import time

    agent_session = await running_agent_service.get_running_agent(session_id)
    
    # Tiered resolution
    resolution = await planner_answer_service.resolve_question(
        project_slug=project_slug,
        session_id=session_id,
        question=question,
    )

    if agent_session:
        from app.services.convex_client import convex
        event = RunnerEvent(
            event_type=RunnerEventType.QUESTION_ASKED,
            session_id=session_id,
            normalized_payload={
                "question": question,
                "answer": resolution.get("answer"),
                "tier": resolution.get("tier"),
                "status": resolution.get("status"),
            },
            raw_payload=resolution,
        )
        await convex.mutation(
            "runnerEvents:append",
            {
                "agentSessionId": agent_session["_id"],
                **event.to_convex_dict(),
                "createdAt": int(time.time() * 1000),
            },
        )

    return resolution
