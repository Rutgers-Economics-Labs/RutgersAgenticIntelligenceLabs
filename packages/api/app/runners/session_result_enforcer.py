"""SessionResult enforcer — validate session_result.json at finalization time.

Called from _finalize_workspace_review after the session completes.  If a
valid session_result.json is present in the workspace it is parsed and its
content is returned.  Absence is NOT a hard failure for legacy sessions, but
is recorded in session state so the promotion gate can gate on it.

Standard write location (agents are instructed to write here):
    <workspace>/research_plan/sessions/<role>/<session_id>/session_result.json

Legacy fallback:
    <workspace>/session_result.json
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.runners.contracts import SessionResult


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

@dataclass
class EnforcerOutcome:
    """Outcome of one session-result enforcement run.

    Attributes:
        found:   True if session_result.json was found on disk.
        valid:   True if the file parses and validates against the schema.
        path:    Path where the file was found (None if not found).
        result:  Parsed SessionResult (None if not found or invalid).
        issues:  List of validation errors / warnings.
    """

    found: bool
    valid: bool
    path: Path | None = None
    result: SessionResult | None = None
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_session_result(
    workspace_root: Path,
    *,
    role: str,
    session_id: str,
) -> Path | None:
    """Search standard locations for session_result.json.

    Locations checked in priority order:
    1. ``<workspace>/research_plan/sessions/<role>/<session_id>/session_result.json``
       (canonical — matches what RAIL's session_files module creates)
    2. ``<workspace>/research_plan/sessions/<session_id>/session_result.json``
       (role-less fallback for runners that don't know the role segment)
    3. ``<workspace>/session_result.json``
       (legacy root-level fallback)

    Args:
        workspace_root: Root of the agent workspace.
        role: Agent role string (e.g. ``research``, ``artifact``).
        session_id: Convex session ID string.

    Returns:
        Path to the first existing file, or None.
    """
    candidates = [
        workspace_root / "research_plan" / "sessions" / role / session_id / "session_result.json",
        workspace_root / "research_plan" / "sessions" / session_id / "session_result.json",
        workspace_root / "session_result.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def enforce_session_result(
    workspace_root: Path,
    *,
    role: str,
    session_id: str,
) -> EnforcerOutcome:
    """Find and validate session_result.json for the completed session.

    This is the authoritative enforcement point called during finalization.
    It does NOT raise — callers decide whether absence/invalidity is fatal.

    Args:
        workspace_root: Root of the agent workspace.
        role: Agent role (e.g. ``research``).
        session_id: Convex session ID.

    Returns:
        EnforcerOutcome with all findings populated.
    """
    path = find_session_result(workspace_root, role=role, session_id=session_id)

    if path is None:
        return EnforcerOutcome(
            found=False,
            valid=False,
            issues=[
                "session_result.json was not found in workspace. "
                "Expected at research_plan/sessions/"
                f"{role}/{session_id}/session_result.json"
            ],
        )

    # File found — try to parse it.
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return EnforcerOutcome(
            found=True,
            valid=False,
            path=path,
            issues=[f"session_result.json is not valid JSON: {exc}"],
        )

    try:
        parsed = SessionResult.model_validate(raw)
    except ValidationError as exc:
        issues = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            issues.append(f"schema: {loc}: {err.get('msg')}")
        return EnforcerOutcome(
            found=True,
            valid=False,
            path=path,
            issues=issues,
        )

    return EnforcerOutcome(
        found=True,
        valid=True,
        path=path,
        result=parsed,
    )
