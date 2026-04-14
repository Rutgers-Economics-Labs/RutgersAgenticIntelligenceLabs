"""
Runner abstraction — base interface and shared data models.

All runner adapters (Jules, future Claude Code, etc.) implement BaseRunner and
emit normalized RunnerEvent objects so the planner can consume a vendor-agnostic
stream of session lifecycle events.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Normalized event types (spec: specs/future-runners.md)
# ---------------------------------------------------------------------------

class RunnerEventType(str, Enum):
    SESSION_CREATED = "session_created"
    PLAN_PROPOSED = "plan_proposed"
    APPROVAL_REQUESTED = "approval_requested"
    QUESTION_ASKED = "question_asked"
    PROGRESS = "progress"
    FILE_CHANGE_DETECTED = "file_change_detected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# RunnerEvent — the common event payload all adapters emit
# ---------------------------------------------------------------------------

@dataclass
class RunnerEvent:
    """A normalized, vendor-agnostic runner event.

    Attributes:
        event_type:         One of the canonical RunnerEventType values.
        session_id:         The platform-external session identifier (vendor-assigned ID).
        normalized_payload: Structured, vendor-neutral fields for application logic.
        raw_payload:        Raw vendor response for debugging; treat as internal / opaque.
        debug_visibility:   If True, surface in debug/admin UIs only.
    """
    event_type: RunnerEventType
    session_id: str
    normalized_payload: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    debug_visibility: bool = False

    def to_convex_dict(self) -> dict[str, Any]:
        """Serialise for the Convex ``runner_events:append`` mutation."""
        return {
            "eventType": self.event_type.value,
            "sessionId": self.session_id,
            "normalizedPayload": self.normalized_payload,
            "rawPayload": self.raw_payload,
            "debugVisibility": self.debug_visibility,
        }


# ---------------------------------------------------------------------------
# Task payload shape (spec: specs/future-runners.md — Task Payload Shape)
# ---------------------------------------------------------------------------

@dataclass
class TaskPayload:
    """Vendor-neutral task payload sent to a runner on session creation.

    The runner adapter is responsible for transforming this into whatever
    format the backend vendor expects (e.g. Jules prompt, Claude task).
    """
    project_slug: str
    role: str
    task_id: str
    repo_url: str
    branch: str
    task_description: str
    allowed_paths: list[str] = field(default_factory=list)
    allowed_secrets: dict[str, str] = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_slug": self.project_slug,
            "role": self.role,
            "task_id": self.task_id,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "allowed_paths": self.allowed_paths,
            "allowed_secrets": list(self.allowed_secrets.keys()),
            "task_description": self.task_description,
            "acceptance_criteria": self.acceptance_criteria,
        }


# ---------------------------------------------------------------------------
# BaseRunner — the abstract interface every adapter must implement
# ---------------------------------------------------------------------------

class BaseRunner(ABC):
    """Abstract runner interface.

    Adapters must implement all six lifecycle methods. The planner and
    orchestrator layers depend exclusively on this interface; they never
    import vendor-specific adapter classes directly.

    Lifecycle overview:
        create_session  → vendor allocates a session, returns its metadata
        get_session     → poll current session state
        list_events     → fetch & normalize all events for a session
        send_message    → relay a question answer or human message to the runner
        approve         → signal human approval (plan-approval or task-start gate)
        cancel          → request cancellation of an in-progress session
    """

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    @abstractmethod
    async def create_session(self, task_payload: TaskPayload) -> dict[str, Any]:
        """Create a new runner session for the given task.

        Returns a dict containing at minimum:
          - ``session_id`` (str): vendor-assigned session identifier
          - ``status`` (str): initial session status
          - ``url`` (str | None): link to the session in the vendor UI
        """

    @abstractmethod
    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Return current session metadata and status for ``session_id``."""

    @abstractmethod
    async def list_events(self, session_id: str) -> list[RunnerEvent]:
        """Fetch all events for ``session_id`` and return them normalized."""

    @abstractmethod
    async def send_message(self, session_id: str, message: str) -> None:
        """Send a text message (question reply / human feedback) to the runner."""

    @abstractmethod
    async def approve(self, session_id: str, payload: dict[str, Any]) -> None:
        """Signal human approval for a pending gate.

        ``payload`` may contain approval context (e.g. approver ID, comment).
        Adapters map this to the vendor-specific approval mechanism.
        """

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        """Request cancellation of an in-progress session.

        Adapters should emit a ``CANCELLED`` RunnerEvent when the cancellation
        is acknowledged or recorded, even if the vendor has no cancel endpoint.
        """

    # ------------------------------------------------------------------
    # Runner metadata (override in adapter)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Short identifier for this runner (e.g. 'jules', 'claude_code')."""
        return type(self).__name__.lower().replace("runner", "")

    @property
    def description(self) -> str:
        """Human-readable description of this runner adapter."""
        return ""
