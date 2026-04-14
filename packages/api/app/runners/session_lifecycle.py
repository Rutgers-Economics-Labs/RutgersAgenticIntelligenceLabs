"""
Jules session lifecycle service.

Orchestrates the full create → poll → complete/cancel flow for Jules runner
sessions, wiring together:

  - Auth resolution (project secrets → global settings fallback)
  - Convex ``agentSessions`` record management
  - ``runnerEvents`` persistence
  - Task board status transitions via ``planner_service``

This is the layer the planner and the ``/projects/{slug}/runner/*`` router
call; neither of them touches the Jules REST API directly.

Usage::

    from app.runners.session_lifecycle import (
        create_runner_session,
        poll_session_until_done,
        cancel_runner_session,
        ingest_session_events,
        resolve_runner_for_project,
    )
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType, TaskPayload
from app.runners.factory import RunnerFactory
from app.services.convex_client import convex


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------

async def resolve_jules_api_key(project_id: str | None, agent_role: str = "data") -> str:
    """Resolve the Jules API key for a project.

    Priority:
      1. Project secret ``JULES_API_KEY`` (if project_id provided and policy allows)
      2. Global ``settings.jules_api_key``

    Raises ``RuntimeError`` if no key is available.
    """
    from app.core.config import settings

    if project_id:
        try:
            from app.services.secret_service import resolve_secrets_for_role
            secrets = await resolve_secrets_for_role(project_id, agent_role)
            project_key = secrets.get("JULES_API_KEY") or ""
            if project_key:
                return project_key
        except Exception:
            pass

    global_key = (settings.jules_api_key or "").strip()
    if not global_key:
        raise RuntimeError(
            "No Jules API key available. Set JULES_API_KEY in the environment "
            "or store it as a project secret named 'JULES_API_KEY'."
        )
    return global_key


def resolve_runner_for_project(runner_name: str = "jules", *, api_key: str) -> Any:
    """Instantiate a runner adapter using the resolved API key."""
    from app.core.config import settings
    from app.runners.jules import JulesRunner

    if runner_name == "jules":
        return JulesRunner(
            api_key=api_key,
            api_url=settings.jules_api_url,
            source=settings.jules_source,
        )
    # Future adapters fall back to factory (they may not need per-project auth)
    return RunnerFactory.get(runner_name)


# ---------------------------------------------------------------------------
# Convex helpers
# ---------------------------------------------------------------------------

async def _create_convex_session(
    *,
    project_id: str | None,
    project_slug: str | None,
    task_id: str | None,
    runner: str,
    role: str,
    title: str,
    external_session_id: str | None = None,
) -> str:
    """Create an ``agentSessions`` record and return its Convex ID."""
    result = await convex.mutation(
        "agent:createSession",
        {
            "title": title,
            "model": f"runner:{runner}",
            "projectSlug": project_slug,
            "projectId": project_id,
            "taskId": task_id,
            "role": role,
            "runner": runner,
            "externalSessionId": external_session_id,
            "status": "queued",
        },
    )
    return result["sessionId"]


async def _update_convex_session(
    convex_session_id: str,
    *,
    status: str | None = None,
    external_session_id: str | None = None,
    ended_at: int | None = None,
) -> None:
    patch: dict[str, Any] = {}
    if status is not None:
        patch["status"] = status
    if external_session_id is not None:
        patch["externalSessionId"] = external_session_id
    if ended_at is not None:
        patch["endedAt"] = ended_at
    if patch:
        await convex.mutation(
            "agent:updateSessionState",
            {"sessionId": convex_session_id, **patch},
        )


async def _append_runner_event(
    convex_session_id: str,
    event: RunnerEvent,
) -> None:
    """Persist a single RunnerEvent in Convex ``runnerEvents``."""
    try:
        await convex.mutation(
            "runnerEvents:append",
            {
                "agentSessionId": convex_session_id,
                "eventType": event.event_type.value,
                "normalizedPayload": event.normalized_payload,
                "rawPayload": event.raw_payload,
                "debugVisibility": str(event.debug_visibility).lower(),
                "createdAt": int(time.time() * 1000),
            },
        )
    except Exception:
        pass  # event persistence is best-effort


# ---------------------------------------------------------------------------
# Public lifecycle API
# ---------------------------------------------------------------------------

async def create_runner_session(
    *,
    project_id: str | None,
    project_slug: str | None,
    task_id: str | None,
    runner_name: str = "jules",
    role: str,
    task_description: str,
    repo_url: str,
    branch: str = "main",
    allowed_paths: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_role_for_secrets: str | None = None,
) -> dict[str, Any]:
    """Create a Jules runner session and record it in Convex.

    Steps:
    1. Resolve Jules API key (project secret → global fallback)
    2. Create Convex ``agentSessions`` record (status: queued)
    3. Call Jules API to create the session
    4. Update Convex record with external session ID + running status
    5. Persist ``session_created`` RunnerEvent
    6. Return combined metadata

    Returns a dict:
      - ``convex_session_id``: Convex agentSessions _id
      - ``external_session_id``: Jules session ID
      - ``status``: initial Jules state
      - ``url``: Jules session URL (if available)
    """
    secret_role = agent_role_for_secrets or role

    # 1. Auth
    api_key = await resolve_jules_api_key(project_id, secret_role)
    runner = resolve_runner_for_project(runner_name, api_key=api_key)

    # 2. Create Convex record (no external ID yet)
    title = f"[{role}] {task_description[:60]}"
    convex_session_id = await _create_convex_session(
        project_id=project_id,
        project_slug=project_slug,
        task_id=task_id,
        runner=runner_name,
        role=role,
        title=title,
    )

    # 3. Submit to Jules
    payload = TaskPayload(
        project_slug=project_slug or "unknown",
        role=role,
        task_id=task_id or convex_session_id,
        repo_url=repo_url,
        branch=branch,
        task_description=task_description,
        allowed_paths=allowed_paths or [],
        acceptance_criteria=acceptance_criteria or [],
    )
    try:
        result = await runner.create_session(payload)
    except Exception as e:
        # Mark Convex session as failed if Jules rejects it
        await _update_convex_session(
            convex_session_id,
            status="failed",
            ended_at=int(time.time() * 1000),
        )
        raise RuntimeError(f"Jules session creation failed: {e}") from e

    external_id = result["session_id"]

    # 4. Update Convex with external ID + running status
    await _update_convex_session(
        convex_session_id,
        status="running",
        external_session_id=external_id,
    )

    # 5. Persist session_created event
    await _append_runner_event(
        convex_session_id,
        RunnerEvent(
            event_type=RunnerEventType.SESSION_CREATED,
            session_id=external_id,
            normalized_payload={
                "runner": runner_name,
                "role": role,
                "task_id": task_id,
                "url": result.get("url"),
                "convex_session_id": convex_session_id,
            },
            raw_payload=result.get("raw", {}),
        ),
    )

    return {
        "convex_session_id": convex_session_id,
        "external_session_id": external_id,
        "status": result.get("status", "running"),
        "url": result.get("url"),
        "runner": runner_name,
    }


async def get_runner_session(
    convex_session_id: str,
    *,
    sync_from_runner: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return the current state of a runner session.

    If ``sync_from_runner`` is True, fetches the latest state from Jules and
    updates the Convex record before returning.

    Returns the Convex ``agentSessions`` record augmented with runner data.
    """
    session = await convex.query("agent:getSession", {"sessionId": convex_session_id})
    if not session:
        raise ValueError(f"Session {convex_session_id} not found in Convex")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    result: dict[str, Any] = dict(session)

    if sync_from_runner and external_id:
        try:
            api_key = await resolve_jules_api_key(
                project_id or session.get("projectId"),
                session.get("role") or "data",
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            runner_info = await runner.get_session(external_id)

            # Normalize Jules state to our session status
            normalized = runner_info.get("normalized_status", "")
            status_map = {
                RunnerEventType.COMPLETED.value: "completed",
                RunnerEventType.FAILED.value: "failed",
                RunnerEventType.CANCELLED.value: "cancelled",
                RunnerEventType.QUESTION_ASKED.value: "awaiting_input",
                RunnerEventType.APPROVAL_REQUESTED.value: "awaiting_approval",
            }
            new_status = status_map.get(normalized, "running")

            is_terminal = new_status in {"completed", "failed", "cancelled"}
            await _update_convex_session(
                convex_session_id,
                status=new_status,
                ended_at=int(time.time() * 1000) if is_terminal else None,
            )

            result["runnerInfo"] = runner_info
            result["status"] = new_status
            result["pr_url"] = runner_info.get("pr_url")

        except Exception as e:
            result["syncError"] = str(e)

    return result


async def poll_session_until_done(
    convex_session_id: str,
    *,
    project_id: str | None = None,
    max_polls: int = 120,
    poll_interval_seconds: int = 15,
) -> dict[str, Any]:
    """Poll a Jules session to completion, updating Convex status each cycle.

    Blocks (async) until the session reaches a terminal state or ``max_polls``
    is exhausted.  Each poll cycle:
      1. Fetches session from Jules
      2. Updates Convex status
      3. Ingests new events into ``runnerEvents``

    Returns the final ``get_runner_session`` result.
    Raises ``TimeoutError`` if ``max_polls`` is exhausted.
    """
    terminal = {"completed", "failed", "cancelled"}

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval_seconds)
        result = await get_runner_session(
            convex_session_id,
            sync_from_runner=True,
            project_id=project_id,
        )
        # Ingest events (best-effort)
        try:
            await ingest_session_events(convex_session_id, project_id=project_id)
        except Exception:
            pass

        if result.get("status") in terminal:
            return result

    raise TimeoutError(
        f"Session {convex_session_id} did not complete after "
        f"{max_polls * poll_interval_seconds}s"
    )


async def cancel_runner_session(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Cancel a runner session.

    Updates Convex status to ``cancelled`` and persists a CANCELLED event.
    Jules has no remote cancel endpoint; the cancel is recorded locally.
    """
    session = await convex.query("agent:getSession", {"sessionId": convex_session_id})
    if not session:
        raise ValueError(f"Session {convex_session_id} not found in Convex")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")

    if external_id:
        try:
            api_key = await resolve_jules_api_key(
                project_id or session.get("projectId"),
                session.get("role") or "data",
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            await runner.cancel(external_id)
        except Exception:
            pass

    now_ms = int(time.time() * 1000)
    await _update_convex_session(
        convex_session_id,
        status="cancelled",
        ended_at=now_ms,
    )

    if external_id:
        await _append_runner_event(
            convex_session_id,
            RunnerEvent(
                event_type=RunnerEventType.CANCELLED,
                session_id=external_id,
                normalized_payload={"reason": "user_requested", "runner": runner_name},
                raw_payload={},
            ),
        )

    return {"convex_session_id": convex_session_id, "status": "cancelled"}


async def ingest_session_events(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all current events from the runner and persist them in Convex.

    Normalizes vendor events and writes each into ``runnerEvents``.
    Returns the list of ingested event summaries.
    """
    session = await convex.query("agent:getSession", {"sessionId": convex_session_id})
    if not session:
        raise ValueError(f"Session {convex_session_id} not found in Convex")

    external_id = session.get("externalSessionId")
    if not external_id:
        return []

    runner_name = session.get("runner", "jules")
    api_key = await resolve_jules_api_key(
        project_id or session.get("projectId"),
        session.get("role") or "data",
    )
    runner = resolve_runner_for_project(runner_name, api_key=api_key)

    events = await runner.list_events(external_id)
    ingested: list[dict[str, Any]] = []
    for event in events:
        await _append_runner_event(convex_session_id, event)
        await _relay_runner_event(convex_session_id, session, event)
        ingested.append({
            "event_type": event.event_type.value,
            "debug_visibility": event.debug_visibility,
        })

    return ingested


async def _relay_runner_event(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    """Relay interactive events (approvals, questions) to operational tables.

    Detects:
      - APPROVAL_REQUESTED -> creates an 'approvals' record
      - QUESTION_ASKED     -> appends a planner message
    """
    if event.event_type == RunnerEventType.APPROVAL_REQUESTED:
        await _relay_approval_requested(convex_session_id, session_record, event)
    elif event.event_type == RunnerEventType.QUESTION_ASKED:
        await _relay_question_asked(convex_session_id, session_record, event)


async def _relay_approval_requested(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    """Register a new gate in the 'approvals' table if not already present."""
    project_id = session_record.get("projectId")
    if not project_id:
        return

    # Basic idempotency: check if we already have a pending approval for this session
    existing = await convex.query(
        "approvals:listByProject",
        {"projectId": project_id, "limit": 10},
    ) or []
    for appr in existing:
        if (appr.get("agentSessionId") == convex_session_id and
                appr.get("status") == "pending"):
            return

    await convex.mutation(
        "approvals:create",
        {
            "projectId": project_id,
            "taskId": session_record.get("taskId"),
            "agentSessionId": convex_session_id,
            "approvalType": event.normalized_payload.get("activity_key") or "run_task",
            "status": "pending",
            "requestedByRole": session_record.get("role") or "agent",
        },
    )


async def _relay_question_asked(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    """Relay an agent question to the long-lived planner thread."""
    project_id = session_record.get("projectId")
    if not project_id:
        return

    from app.services import planner_service

    question_text = event.normalized_payload.get("prompt") or "The agent has a question."
    await planner_service.append_planner_message(
        project_id=project_id,
        role="assistant",
        content=f"**[Question from Agent]**: {question_text}",
        message_type="question",
        session_id=convex_session_id,
    )
