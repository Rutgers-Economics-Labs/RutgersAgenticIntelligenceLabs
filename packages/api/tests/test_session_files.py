from __future__ import annotations

from pathlib import Path

from app.services import session_files


def test_session_files_round_trip(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-1")

    first_event = session_files.append_event(
        root,
        "assistant_message",
        role="assistant",
        content="Inspecting the repo.",
        status="running",
    )
    command = session_files.append_command(
        root,
        "inject_message",
        content="Please summarize the current diff.",
    )
    session_files.mark_command_processed(root, int(command["id"]))

    state = session_files.read_state(root)
    events = session_files.list_events(root)
    commands = session_files.list_commands(root)
    summary = (root / "summary.md").read_text(encoding="utf-8")

    assert first_event["id"] == 1
    assert state["status"] == "running"
    assert len(events) == 1
    assert commands[0]["processed"] is True
    assert "Inspecting the repo." in summary
