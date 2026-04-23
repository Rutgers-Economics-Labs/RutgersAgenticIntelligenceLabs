"""
Runner session lifecycle service.

This module provides the planner-owned runtime bridge for both API-backed and
local CLI-backed workers. Durable session state is mirrored into repo files:

  - research_plan/sessions/<role>/<session-id>/session.ndjson
  - research_plan/sessions/<role>/<session-id>/commands.ndjson
  - research_plan/sessions/<role>/<session-id>/state.json
  - research_plan/sessions/<role>/<session-id>/summary.md

The runtime DB remains a lightweight live-control plane through
``running_agent_service``.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType, TaskPayload
from app.runners.factory import RunnerFactory
from app.services import planner_service, running_agent_service, session_files
from app.services.convex_client import convex


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
STATUS_MAP = {
    RunnerEventType.COMPLETED.value: "completed",
    RunnerEventType.FAILED.value: "failed",
    RunnerEventType.CANCELLED.value: "cancelled",
    RunnerEventType.QUESTION_ASKED.value: "awaiting_input",
    RunnerEventType.APPROVAL_REQUESTED.value: "awaiting_approval",
}
EVENT_TYPE_MAP = {
    RunnerEventType.SESSION_CREATED.value: "session_started",
    RunnerEventType.STATUS_CHANGED.value: "status_changed",
    RunnerEventType.PLAN_PROPOSED.value: "status_changed",
    RunnerEventType.APPROVAL_REQUESTED.value: "approval_requested",
    RunnerEventType.QUESTION_ASKED.value: "question_asked",
    RunnerEventType.PROGRESS.value: "assistant_message",
    RunnerEventType.BASH_COMMAND_STARTED.value: "tool_call",
    RunnerEventType.BASH_COMMAND_COMPLETED.value: "tool_result",
    RunnerEventType.FILE_CHANGE_DETECTED.value: "file_change_detected",
    RunnerEventType.VERIFICATION_STARTED.value: "verification_started",
    RunnerEventType.VERIFICATION_COMPLETED.value: "verification_completed",
    RunnerEventType.COMPLETED.value: "completed",
    RunnerEventType.FAILED.value: "failed",
    RunnerEventType.CANCELLED.value: "cancelled",
}


async def resolve_jules_api_key(project_id: str | None, agent_role: str = "data") -> str:
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


def resolve_runner_for_project(runner_name: str = "jules", *, api_key: str | None = None) -> Any:
    if runner_name == "jules":
        from app.core.config import settings
        from app.runners.jules import JulesRunner

        if not api_key:
            raise RuntimeError("Jules runner requires an API key")
        return JulesRunner(
            api_key=api_key,
            api_url=settings.jules_api_url,
            source=settings.jules_source,
        )

    return RunnerFactory.get(runner_name)


def _project_root(project_record: dict[str, Any]) -> Path | None:
    path = project_record.get("localRepoPath")
    return Path(path).resolve() if path else None


def _event_payload(event: RunnerEvent) -> dict[str, Any]:
    payload = dict(event.normalized_payload or {})
    if payload.get("line"):
        payload.setdefault("content", payload.get("line"))
    if payload.get("message"):
        payload.setdefault("content", payload.get("message"))
    if payload.get("prompt"):
        payload.setdefault("content", payload.get("prompt"))
    if payload.get("command"):
        payload.setdefault("name", "bash")
    payload["runner_event_type"] = event.event_type.value
    payload["raw_payload"] = event.raw_payload or {}
    payload["debug_visibility"] = event.debug_visibility
    return payload


async def _append_runner_event(convex_session_id: str, event: RunnerEvent) -> None:
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
        pass


def _sync_file_status(root: Path, status: str) -> None:
    session_files.update_state(root, status=status)
    session_files.refresh_summary(root)


async def _load_project(project_id: str | None, project_slug: str | None) -> dict[str, Any] | None:
    if project_id:
        return await convex.query("projects:getById", {"projectId": project_id})
    if project_slug:
        return await convex.query("projects:getBySlug", {"slug": project_slug})
    return None


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
    local_repo_path: str | None = None,
    allowed_paths: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_role_for_secrets: str | None = None,
) -> dict[str, Any]:
    secret_role = agent_role_for_secrets or role

    if project_id:
        active_worker = await running_agent_service.find_active_worker(project_id)
        if active_worker:
            raise RuntimeError(
                f"Sequential execution enforced: worker session {active_worker['_id']} is still active"
            )

    project = await _load_project(project_id, project_slug)
    project_root = _project_root(project or {})
    if project_root is None and local_repo_path:
        project_root = Path(local_repo_path).resolve()
    if project_root is None:
        raise RuntimeError("Runner sessions require a local repo path")

    api_key = await resolve_jules_api_key(project_id, secret_role) if runner_name == "jules" else None
    runner = resolve_runner_for_project(runner_name, api_key=api_key)

    title = f"[{role}] {task_description[:60]}"
    running_session_id = await running_agent_service.create_running_agent(
        project_id=project_id,
        project_slug=project_slug,
        task_id=task_id,
        runtime_kind=runner_name,
        role=role,
        title=title,
        external_session_id=None,
        session_path=None,
        status="queued",
    )
    session_root = session_files.ensure_session_root(project_root, role, running_session_id)
    session_files.append_event(
        session_root,
        "session_started",
        content=task_description,
        runner=runner_name,
        role=role,
        task_id=task_id,
        status="queued",
    )
    await running_agent_service.update_running_agent(running_session_id, sessionPath=str(session_root))

    task_payload = TaskPayload(
        project_slug=project_slug or (project.get("slug") if project else "unknown"),
        role=role,
        task_id=task_id or running_session_id,
        repo_url=repo_url,
        branch=branch,
        local_repo_path=str(project_root),
        task_description=task_description,
        allowed_paths=allowed_paths or [],
        acceptance_criteria=acceptance_criteria or [],
    )
    try:
        result = await runner.create_session(task_payload)
    except Exception as exc:
        _sync_file_status(session_root, "failed")
        session_files.append_event(
            session_root,
            "failed",
            content=str(exc),
            status="failed",
        )
        await running_agent_service.finalize_running_agent(
            running_session_id,
            status="failed",
            ended_at=int(time.time() * 1000),
        )
        raise RuntimeError(f"Runner session creation failed: {exc}") from exc

    external_id = result["session_id"]
    await running_agent_service.update_running_agent(
        running_session_id,
        status="running",
        externalSessionId=external_id,
    )
    session_files.append_event(
        session_root,
        "status_changed",
        content=f"Worker session started with {runner_name}",
        runner=runner_name,
        external_session_id=external_id,
        status="running",
    )
    await _append_runner_event(
        running_session_id,
        RunnerEvent(
            event_type=RunnerEventType.SESSION_CREATED,
            session_id=external_id,
            normalized_payload={
                "runner": runner_name,
                "role": role,
                "task_id": task_id,
                "url": result.get("url"),
                "running_session_id": running_session_id,
            },
            raw_payload=result.get("raw", {}),
        ),
    )

    return {
        "convex_session_id": running_session_id,
        "external_session_id": external_id,
        "status": result.get("status", "running"),
        "url": result.get("url"),
        "runner": runner_name,
        "sessionPath": str(session_root),
    }


async def get_runner_session(
    convex_session_id: str,
    *,
    sync_from_runner: bool = True,
    project_id: str | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    result: dict[str, Any] = dict(session)
    session_path = session.get("sessionPath")
    root = Path(session_path) if session_path else None
    if root and root.exists():
        result["fileState"] = session_files.read_state(root)
        result["summaryPath"] = str(root / "summary.md")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    if sync_from_runner and external_id:
        try:
            api_key = (
                await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
                if runner_name == "jules"
                else None
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            runner_info = await runner.get_session(external_id)
            normalized = runner_info.get("normalized_status", "")
            new_status = STATUS_MAP.get(normalized, runner_info.get("status", "running"))
            is_terminal = new_status in TERMINAL_STATUSES
            await running_agent_service.update_running_agent(
                convex_session_id,
                status=new_status,
                endedAt=int(time.time() * 1000) if is_terminal else None,
            )
            if root and root.exists():
                _sync_file_status(root, new_status)
            result["runnerInfo"] = runner_info
            result["status"] = new_status
            result["pr_url"] = runner_info.get("pr_url")
        except Exception as exc:
            result["syncError"] = str(exc)
    return result


async def poll_session_until_done(
    convex_session_id: str,
    *,
    project_id: str | None = None,
    max_polls: int = 120,
    poll_interval_seconds: int = 15,
) -> dict[str, Any]:
    for _ in range(max_polls):
        await asyncio.sleep(poll_interval_seconds)
        result = await get_runner_session(
            convex_session_id,
            sync_from_runner=True,
            project_id=project_id,
        )
        try:
            await ingest_session_events(convex_session_id, project_id=project_id)
        except Exception:
            pass
        if result.get("status") in TERMINAL_STATUSES:
            return result

    raise TimeoutError(
        f"Session {convex_session_id} did not complete after {max_polls * poll_interval_seconds}s"
    )


async def cancel_runner_session(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    external_id = session.get("externalSessionId")
    runner_name = session.get("runner", "jules")
    if external_id:
        try:
            api_key = (
                await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
                if runner_name == "jules"
                else None
            )
            runner = resolve_runner_for_project(runner_name, api_key=api_key)
            await runner.cancel(external_id)
        except Exception:
            pass

    session_path = session.get("sessionPath")
    if session_path:
        root = Path(session_path)
        if root.exists():
            session_files.append_event(
                root,
                "cancelled",
                content="Session cancelled by user.",
                status="cancelled",
            )
            _sync_file_status(root, "cancelled")

    await running_agent_service.finalize_running_agent(
        convex_session_id,
        status="cancelled",
        ended_at=int(time.time() * 1000),
    )
    return {"convex_session_id": convex_session_id, "status": "cancelled"}


async def ingest_session_events(
    convex_session_id: str,
    *,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")

    external_id = session.get("externalSessionId")
    if not external_id:
        return []

    runner_name = session.get("runner", "jules")
    api_key = (
        await resolve_jules_api_key(project_id or session.get("projectId"), session.get("role") or "data")
        if runner_name == "jules"
        else None
    )
    runner = resolve_runner_for_project(runner_name, api_key=api_key)
    events = await runner.list_events(external_id)
    session_path = session.get("sessionPath")
    root = Path(session_path) if session_path else None
    existing_count = len(session_files.list_events(root)) if root and root.exists() else 0
    new_events = events[existing_count:]

    ingested: list[dict[str, Any]] = []
    for event in new_events:
        await _append_runner_event(convex_session_id, event)
        if root and root.exists():
            file_event_type = EVENT_TYPE_MAP.get(event.event_type.value, "status_changed")
            payload = _event_payload(event)
            status = STATUS_MAP.get(event.event_type.value)
            if status:
                payload["status"] = status
            session_files.append_event(root, file_event_type, **payload)
            if status:
                _sync_file_status(root, status)
        await _relay_runner_event(convex_session_id, session, event)
        ingested.append(
            {
                "event_type": event.event_type.value,
                "debug_visibility": event.debug_visibility,
            }
        )

    if session_path and Path(session_path).exists():
        state = session_files.read_state(session_path)
        if state.get("status") in TERMINAL_STATUSES:
            await running_agent_service.finalize_running_agent(
                convex_session_id,
                status=state["status"],
                ended_at=int(time.time() * 1000),
            )

    return ingested


async def append_session_command(
    convex_session_id: str,
    *,
    command_type: str,
    content: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = await running_agent_service.get_running_agent(convex_session_id)
    if not session:
        raise ValueError(f"Session {convex_session_id} not found")
    session_path = session.get("sessionPath")
    if not session_path:
        raise RuntimeError("Session has no sessionPath")
    root = Path(session_path)
    command = session_files.append_command(
        root,
        command_type,
        content=content,
        payload=payload or {},
    )
    external_id = session.get("externalSessionId")
    if external_id:
        runner_name = session.get("runner", "jules")
        api_key = (
            await resolve_jules_api_key(session.get("projectId"), session.get("role") or "data")
            if runner_name == "jules"
            else None
        )
        runner = resolve_runner_for_project(runner_name, api_key=api_key)
        if command_type == "inject_message" and content:
            await runner.send_message(external_id, content)
        elif command_type == "approve":
            await runner.approve(external_id, payload or {"message": content or "approved"})
        elif command_type == "cancel":
            await runner.cancel(external_id)
        session_files.mark_command_processed(root, int(command["id"]))
    return command


async def _relay_runner_event(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    if event.event_type == RunnerEventType.APPROVAL_REQUESTED:
        await _relay_approval_requested(convex_session_id, session_record, event)
    elif event.event_type == RunnerEventType.QUESTION_ASKED:
        await _relay_question_asked(convex_session_id, session_record, event)
    elif event.event_type in {RunnerEventType.COMPLETED, RunnerEventType.FAILED, RunnerEventType.CANCELLED}:
        await _relay_terminal_status(session_record, event)


async def _relay_approval_requested(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    project_id = session_record.get("projectId")
    if not project_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return

    existing = await planner_service.list_approvals(project)
    for approval in existing:
        if approval.get("agentSessionId") == convex_session_id and approval.get("status") == "pending":
            return

    await planner_service.create_approval(
        project=project,
        task_id=session_record.get("taskId"),
        agent_session_id=convex_session_id,
        approval_type=event.normalized_payload.get("activity_key") or "run_task",
        status="pending",
        requested_by_role=session_record.get("role") or "agent",
        resolution_note=event.normalized_payload.get("prompt") or event.normalized_payload.get("message"),
    )
    await planner_service.sync_planner_files(project)


async def _relay_question_asked(
    convex_session_id: str,
    session_record: dict[str, Any],
    event: RunnerEvent,
) -> None:
    project_id = session_record.get("projectId")
    if not project_id:
        return
    question_text = (
        event.normalized_payload.get("prompt")
        or event.normalized_payload.get("message")
        or "The agent has a question."
    )
    await planner_service.append_planner_message(
        project_id=project_id,
        role="assistant",
        content=f"[Question from {session_record.get('role') or 'agent'}] {question_text}",
        message_type="question",
        session_id=convex_session_id,
    )


async def _relay_terminal_status(session_record: dict[str, Any], event: RunnerEvent) -> None:
    project_id = session_record.get("projectId")
    task_id = session_record.get("taskId")
    if not project_id or not task_id:
        return
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        return
    status = STATUS_MAP.get(event.event_type.value, "done")
    task_status = {
        "completed": "done",
        "failed": "blocked",
        "cancelled": "cancelled",
    }.get(status, "review")
    summary = (
        event.normalized_payload.get("message")
        or event.normalized_payload.get("stderr")
        or f"Session ended with status {status}."
    )
    await planner_service.update_task(
        str(task_id),
        project=project,
        status=task_status,
        latestRunSummary=summary,
    )
    await planner_service.sync_planner_files(project)
