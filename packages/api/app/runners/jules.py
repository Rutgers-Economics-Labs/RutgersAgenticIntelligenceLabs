"""
JulesRunner — adapter for the Jules (jules.googleapis.com) coding agent API.

Extracts and formalises the Jules-specific session management currently
baked into ``run_jules_agents.py``, wrapping it behind the BaseRunner interface.

Jules session lifecycle:
    POST   /sessions               → create_session
    GET    /sessions/{id}          → get_session
    GET    /sessions/{id}/activities → list_events  (normalized)
    POST   /sessions/{id}:sendMessage → send_message / approve
    (no native cancel endpoint — cancel is recorded locally)
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.runners.base import BaseRunner, RunnerEvent, RunnerEventType, TaskPayload


# ---------------------------------------------------------------------------
# Jules-specific activity / state → normalized event type mappings
# ---------------------------------------------------------------------------

# Maps Jules session ``state`` values to a normalized event type.
_STATE_TO_EVENT: dict[str, RunnerEventType] = {
    "IN_PROGRESS": RunnerEventType.PROGRESS,
    "AWAITING_USER_FEEDBACK": RunnerEventType.QUESTION_ASKED,
    "COMPLETED": RunnerEventType.COMPLETED,
    "FAILED": RunnerEventType.FAILED,
    "CANCELLED": RunnerEventType.CANCELLED,
}

# Maps Jules activity type keys (the dict key present in each activity object)
# to a normalized event type.  Jules activities are typed by the field name
# present in the activity dict rather than a ``type`` string.
_ACTIVITY_KEY_TO_EVENT: dict[str, RunnerEventType] = {
    "sessionCreated": RunnerEventType.SESSION_CREATED,
    "planProposed": RunnerEventType.PLAN_PROPOSED,
    "approvalRequested": RunnerEventType.APPROVAL_REQUESTED,
    "questionAsked": RunnerEventType.QUESTION_ASKED,
    "sessionCompleted": RunnerEventType.COMPLETED,
    "sessionFailed": RunnerEventType.FAILED,
    "sessionCancelled": RunnerEventType.CANCELLED,
    "fileChanged": RunnerEventType.FILE_CHANGE_DETECTED,
    "planApproved": RunnerEventType.PROGRESS,
}

# Default Jules prompt sent when auto-approving a plan-approval request.
_DEFAULT_APPROVAL_MESSAGE = (
    "Please continue carefully, follow the current plan, and run verification "
    "before finishing."
)


def _build_prompt(payload: TaskPayload) -> str:
    """Convert a TaskPayload into the Jules task prompt string."""
    criteria_block = ""
    if payload.acceptance_criteria:
        criteria_lines = "\n".join(f"- {c}" for c in payload.acceptance_criteria)
        criteria_block = f"\n\nAcceptance criteria:\n{criteria_lines}"

    paths_block = ""
    if payload.allowed_paths:
        paths_lines = "\n".join(f"  - {p}" for p in payload.allowed_paths)
        paths_block = f"\n\nAllowed paths:\n{paths_lines}"

    return (
        f"Please implement the following task for the '{payload.project_slug}' project.\n\n"
        f"Role: {payload.role}\n"
        f"Task ID: {payload.task_id}\n\n"
        f"Task description:\n{payload.task_description}"
        f"{criteria_block}"
        f"{paths_block}\n\n"
        "Important constraints:\n"
        "- Respect the repo contract and existing local changes.\n"
        "- Do not undo unrelated work.\n"
        "- Run the most relevant verification commands after implementation.\n"
        "- If the task requires human approval or missing secrets, stop and ask.\n"
    )


def _normalize_activity(activity: dict[str, Any], session_id: str) -> RunnerEvent | None:
    """Normalize a single Jules activity dict into a RunnerEvent.

    Returns None if the activity type is not recognized.
    """
    for key, event_type in _ACTIVITY_KEY_TO_EVENT.items():
        if key in activity:
            return RunnerEvent(
                event_type=event_type,
                session_id=session_id,
                normalized_payload={
                    "activity_key": key,
                    "summary": str(activity[key])[:500] if not isinstance(activity[key], dict) else "",
                    **(activity[key] if isinstance(activity[key], dict) else {}),
                },
                raw_payload=activity,
                debug_visibility=(key not in {"sessionCompleted", "planProposed", "approvalRequested", "questionAsked"}),
            )
    # Unknown activity — include as debug-only progress event
    return RunnerEvent(
        event_type=RunnerEventType.PROGRESS,
        session_id=session_id,
        normalized_payload={"raw_keys": list(activity.keys())},
        raw_payload=activity,
        debug_visibility=True,
    )


# ---------------------------------------------------------------------------
# JulesRunner
# ---------------------------------------------------------------------------

class JulesRunner(BaseRunner):
    """Runner adapter for the Jules Google coding agent API.

    Args:
        api_key:  Jules API key (``X-Goog-Api-Key`` header).
        api_url:  Base Jules API URL (defaults to production endpoint).
        source:   Jules source string identifying the GitHub repository.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://jules.googleapis.com/v1alpha",
        source: str = "sources/github/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs",
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url.rstrip("/")
        self._source = source

    @property
    def name(self) -> str:
        return "jules"

    @property
    def description(self) -> str:
        return "Jules — Google's managed coding agent API (GitHub-native)"

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-Goog-Api-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self._api_url}/{path}", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._api_url}/{path}",
                headers=self._headers(),
                json=json,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # BaseRunner implementation
    # ------------------------------------------------------------------

    async def create_session(self, task_payload: TaskPayload) -> dict[str, Any]:
        """Create a Jules coding session.

        Returns a dict with ``session_id``, ``session_name``, ``status``,
        and ``pr_url`` (None until the session completes).
        """
        prompt = _build_prompt(task_payload)
        body = {
            "prompt": prompt,
            "sourceContext": {
                "source": self._source,
                "githubRepoContext": {
                    "startingBranch": task_payload.branch,
                },
            },
            "automationMode": "AUTO_CREATE_PR",
            "title": f"[{task_payload.role}] {task_payload.task_id}",
        }
        data = await self._post("sessions", body)
        return {
            "session_id": data["id"],
            "session_name": data["name"],
            "status": data.get("state", "IN_PROGRESS"),
            "url": data.get("url"),
            "raw": data,
        }

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch current Jules session metadata."""
        data = await self._get(f"sessions/{session_id}")
        state = data.get("state", "UNKNOWN")
        pr_url: str | None = None
        for output in data.get("outputs", []):
            if "pullRequest" in output:
                pr_url = output["pullRequest"].get("url")
                break

        return {
            "session_id": session_id,
            "session_name": data.get("name"),
            "status": state,
            "normalized_status": _STATE_TO_EVENT.get(state, RunnerEventType.PROGRESS).value,
            "pr_url": pr_url,
            "raw": data,
        }

    async def list_events(self, session_id: str) -> list[RunnerEvent]:
        """Fetch Jules activities and normalize them into RunnerEvents."""
        # Jules uses the session name (not just ID) in some paths.
        # We fetch the session first to get the name, then list activities.
        session = await self._get(f"sessions/{session_id}")
        session_name = session.get("name", f"sessions/{session_id}")

        try:
            activities_data = await self._get(f"{session_name}/activities?pageSize=100")
        except httpx.HTTPStatusError:
            activities_data = {}

        activities = activities_data.get("activities", [])
        events: list[RunnerEvent] = []
        for activity in activities:
            event = _normalize_activity(activity, session_id)
            if event is not None:
                events.append(event)

        return events

    async def send_message(self, session_id: str, message: str) -> None:
        """Relay a message (question answer / human feedback) to Jules."""
        session = await self._get(f"sessions/{session_id}")
        session_name = session.get("name", f"sessions/{session_id}")
        await self._post(f"{session_name}:sendMessage", {"prompt": message})

    async def approve(self, session_id: str, payload: dict[str, Any]) -> None:
        """Approve a Jules plan-approval gate.
        
        Uses the dedicated :approvePlan endpoint if the activity suggests a plan approval,
        otherwise falls back to :sendMessage.
        """
        activity_key = payload.get("activity_key")
        if activity_key == "planProposed" or activity_key == "approvalRequested":
            await self._post(f"sessions/{session_id}:approvePlan", {})
        else:
            message = payload.get("message") or _DEFAULT_APPROVAL_MESSAGE
            await self.send_message(session_id, message)

    async def cancel(self, session_id: str) -> None:
        """Record cancellation intent.

        Jules has no cancel REST endpoint. This method records the intent by
        raising no error — the caller should persist a ``CANCELLED`` event via
        ``ingest_events`` or directly in Convex.

        Future: if Jules adds a cancel endpoint, implement it here.
        """
        # No-op at the transport layer — the router / service layer is
        # responsible for persisting the cancelled state in Convex.
        pass

    # ------------------------------------------------------------------
    # Convenience: poll until terminal state
    # ------------------------------------------------------------------

    async def poll_until_done(
        self,
        session_id: str,
        *,
        max_polls: int = 120,
        poll_interval_seconds: int = 15,
    ) -> dict[str, Any]:
        """Block (async) until the session reaches a terminal state.

        Returns the final ``get_session`` result dict.  Raises
        ``TimeoutError`` if ``max_polls`` is exhausted.
        """
        import asyncio
        terminal = {RunnerEventType.COMPLETED, RunnerEventType.FAILED, RunnerEventType.CANCELLED}
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval_seconds)
            info = await self.get_session(session_id)
            normalized = RunnerEventType(info["normalized_status"]) if info.get("normalized_status") in RunnerEventType._value2member_map_ else None  # noqa: SLF001
            if normalized in terminal:
                return info
        raise TimeoutError(
            f"Jules session {session_id} did not reach a terminal state after "
            f"{max_polls * poll_interval_seconds}s"
        )
