"""Normalize runner session state for reconciliation (Milestone 2)."""

from __future__ import annotations

ACTIVE_STATUSES = frozenset({"queued", "running", "awaiting_input", "awaiting_approval", "paused"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "blocked"})
SESSION_STATUSES = ACTIVE_STATUSES | TERMINAL_STATUSES

LEGACY_STATUS_ALIASES = {
    "done": "completed",
}


def normalize_session_status(status: str | None, *, strict: bool = False) -> str | None:
    if status in {None, ""}:
        return None
    normalized = str(status).strip().lower()
    normalized = LEGACY_STATUS_ALIASES.get(normalized, normalized)
    if normalized in SESSION_STATUSES:
        return normalized
    if strict:
        raise ValueError(f"Unsupported session status: {status}")
    return status


def is_active_status(status: str | None) -> bool:
    return normalize_session_status(status) in ACTIVE_STATUSES


def is_terminal_status(status: str | None) -> bool:
    return normalize_session_status(status) in TERMINAL_STATUSES


def normalize_session_record(state: dict) -> dict:
    """Return a copy with canonical status when recognized."""
    if not state:
        return state
    normalized_status = normalize_session_status(state.get("status"))
    if normalized_status is None or normalized_status == state.get("status"):
        return dict(state)
    return dict(state) | {"status": normalized_status}
