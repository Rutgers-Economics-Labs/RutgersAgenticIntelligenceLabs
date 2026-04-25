"""
Frontend-ready session detail builder.

Turns raw session files (session.ndjson, commands.ndjson, state.json) into
a consolidated, typed read model the UI can render without further parsing.

The four observability layers from specs/frontend-command-center.md:
  Layer 1 – Executive summary   (currentFocus, status, workspaceBranch, ...)
  Layer 2 – Activity timeline   (normalized event rows)
  Layer 3 – Workspace/files     (changedFiles, changedFileCount, ...)
  Layer 4 – Commands/messages   (recentCommands, recentMessages, recentRelays)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services import session_files


# ---------------------------------------------------------------------------
# Event type classifications
# ---------------------------------------------------------------------------

_PROGRESS_TYPES = {"assistant_message", "progress", "planner_relay"}
_COMMAND_TYPES = {"tool_call", "tool_result"}
_FILE_CHANGE_TYPES = {"file_change_detected"}
_VERIFICATION_TYPES = {"verification_started", "verification_completed"}
_TERMINAL_TYPES = {"completed", "failed", "cancelled"}

_TIMELINE_LABELS: dict[str, str] = {
    "session_started": "Session Started",
    "status_changed": "Status Changed",
    "workspace_setup_started": "Setup Started",
    "workspace_setup_completed": "Setup Completed",
    "workspace_archive_started": "Archive Started",
    "workspace_archive_completed": "Archive Completed",
    "assistant_message": "Agent Message",
    "planner_relay": "Planner Relay",
    "tool_call": "Command Started",
    "tool_result": "Command Completed",
    "file_change_detected": "File Changed",
    "verification_started": "Verification Started",
    "verification_completed": "Verification Completed",
    "approval_requested": "Approval Requested",
    "question_asked": "Question Asked",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}


# ---------------------------------------------------------------------------
# Current-focus derivation (Layer 1)
# ---------------------------------------------------------------------------

def _derive_current_focus(events: list[dict[str, Any]], state: dict[str, Any]) -> str:
    status = state.get("status") or ""
    review_status = state.get("review_status") or ""

    if status == "completed":
        if review_status == "review":
            return "Work complete — ready for review"
        if review_status == "needs_changes":
            return "Work complete — review blockers found"
        return "Session completed"
    if status == "failed":
        return "Session failed"
    if status == "cancelled":
        return "Session cancelled"
    if status == "awaiting_approval":
        return "Waiting for human approval"
    if status == "awaiting_input":
        return "Agent is waiting for input"

    for event in reversed(events):
        etype = event.get("type", "")
        content = (
            event.get("content")
            or event.get("prompt")
            or event.get("message")
            or ""
        ).strip()

        if etype == "approval_requested":
            return f"Requesting approval: {content[:100]}" if content else "Requesting approval"
        if etype == "question_asked":
            return f"Asked question: {content[:100]}" if content else "Agent has a question"
        if etype == "verification_started":
            return "Running verification script"
        if etype == "verification_completed":
            vstat = state.get("verification_status") or ""
            return f"Verification {vstat}".strip() or "Verification completed"
        if etype == "file_change_detected":
            path = event.get("path") or ""
            return f"Editing {path}" if path else "Editing files"
        if etype == "tool_call":
            name = event.get("name") or event.get("tool_name") or ""
            return f"Running: {name}" if name else "Running command"
        if etype == "assistant_message":
            snippet = content.replace("\n", " ")
            return snippet[:120] if snippet else "Working..."
        if etype == "workspace_setup_started":
            return "Setting up workspace"
        if etype in {"session_started", "status_changed"}:
            continue

    if status:
        return f"Status: {status}"
    return "Initializing..."


# ---------------------------------------------------------------------------
# Timeline builder (Layer 2)
# ---------------------------------------------------------------------------

def _build_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        etype = event.get("type", "")
        content = (
            event.get("content")
            or event.get("message")
            or event.get("prompt")
            or ""
        )
        rows.append(
            {
                "id": event.get("id"),
                "timestamp": event.get("timestamp"),
                "eventType": etype,
                "label": _TIMELINE_LABELS.get(etype, etype.replace("_", " ").title()),
                "summary": str(content).strip()[:200] if content else None,
                "raw": event,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Review-file helpers
# ---------------------------------------------------------------------------

def _rel(p: str | Path, project_root: Path | None) -> str | None:
    if not p or not project_root:
        return str(p) if p else None
    try:
        return str(Path(p).relative_to(project_root))
    except ValueError:
        return str(p)


def _read_review_file(root: Path, name: str) -> str | None:
    path = root / name
    return path.read_text(encoding="utf-8") if path.exists() else None


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def build_session_detail(
    session_path: str | Path,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """
    Return a frontend-ready rich detail object for a single runner session.

    Reads session.ndjson, commands.ndjson, and state.json from *session_path*
    and produces the four observability layers required by the command-center
    frontend spec.
    """
    root = Path(session_path)
    proj_root = Path(project_root) if project_root else None

    state = session_files.read_state(root)
    events = session_files.list_events(root)
    commands = session_files.list_commands(root)

    # Layer 4 — commands and messages
    recent_messages = [
        e for e in events if e.get("type") in _PROGRESS_TYPES
    ][-10:]
    recent_commands = [
        e for e in events if e.get("type") in _COMMAND_TYPES
    ][-10:]
    recent_relays = [
        e for e in events if e.get("type") == "planner_relay"
    ][-5:]

    # Layer 3 — file activity
    file_change_events = [
        e for e in events if e.get("type") in _FILE_CHANGE_TYPES
    ]
    changed_files_ordered = list(
        dict.fromkeys(e.get("path") for e in file_change_events if e.get("path"))
    )

    # Layer 1 — executive summary
    current_focus = _derive_current_focus(events, state)

    last_event_summary: str | None = None
    for e in reversed(events):
        content = (
            e.get("content") or e.get("message") or e.get("prompt") or ""
        ).strip().replace("\n", " ")
        if content:
            last_event_summary = f"[{e.get('type')}] {content[:200]}"
            break

    # Review files (paths + inline content for small files)
    review_files: dict[str, Any] = {}
    for fname, inline in (
        ("summary.md", True),
        ("diff.md", True),
        ("todos.md", True),
        ("verification.md", True),
    ):
        path = root / fname
        if path.exists():
            key = fname.replace(".md", "")
            review_files[key] = {
                "path": _rel(path, proj_root),
                "content": path.read_text(encoding="utf-8") if inline else None,
            }

    return {
        # Layer 1 – executive summary
        "currentFocus": current_focus,
        "lastEventSummary": last_event_summary,
        "status": state.get("status"),
        "reviewStatus": state.get("review_status"),
        "workspacePath": state.get("workspace_path"),
        "workspaceBranch": state.get("workspace_branch"),
        "setupStatus": state.get("setup_status"),
        "verificationStatus": state.get("verification_status"),
        "archiveStatus": state.get("archive_status"),
        "setupExitCode": state.get("setup_exit_code"),
        "verificationExitCode": state.get("verification_exit_code"),
        # Layer 2 – activity timeline
        "timeline": _build_timeline(events),
        "eventCount": len(events),
        # Layer 3 – workspace and file activity
        "changedFiles": changed_files_ordered,
        "changedFileCount": len(changed_files_ordered),
        # Layer 4 – commands and messages
        "recentMessages": recent_messages,
        "recentCommands": recent_commands,
        "recentRelays": recent_relays,
        "pendingCommands": [c for c in commands if not c.get("processed")],
        # Review artifacts
        "reviewFiles": review_files,
    }
