from __future__ import annotations

from pathlib import Path

from app.services import session_files
from app.services.session_detail_service import build_session_detail


def _make_session(tmp_path: Path, role: str = "coding", sid: str = "s1") -> Path:
    return session_files.ensure_session_root(tmp_path, role, sid)


# ---------------------------------------------------------------------------
# Layer 1 – executive summary / currentFocus derivation
# ---------------------------------------------------------------------------


def test_detail_empty_session(tmp_path: Path):
    root = _make_session(tmp_path)
    detail = build_session_detail(root)

    assert detail["status"] == "initialized"
    assert isinstance(detail["currentFocus"], str)
    assert detail["currentActivity"]["summary"] == detail["currentFocus"]
    assert detail["changedFiles"] == []
    assert detail["changedFileCount"] == 0
    assert detail["timeline"] == []
    assert detail["recentMessages"] == []
    assert detail["recentCommands"] == []
    assert detail["pendingCommands"] == []


def test_detail_current_focus_file_change(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "file_change_detected", path="topics/labor/notes.md", status="running")

    detail = build_session_detail(root)
    assert "topics/labor/notes.md" in detail["currentFocus"]
    assert detail["currentActivity"]["kind"] == "editing_file"
    assert detail["activeFile"] == "topics/labor/notes.md"
    assert detail["workingOn"] == "topics/labor/notes.md"


def test_detail_current_focus_tool_call(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "tool_call", name="bash", content="python scripts/check.py", status="running")

    detail = build_session_detail(root)
    assert "bash" in detail["currentFocus"]
    assert detail["currentActivity"]["kind"] == "running_command"
    assert detail["activeCommand"]["name"] == "bash"
    assert "python scripts/check.py" in detail["activeCommand"]["preview"]


def test_detail_current_focus_awaiting_input(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(
        root, "question_asked", content="Should I overwrite the existing file?", status="awaiting_input"
    )
    session_files.update_state(root, status="awaiting_input")

    detail = build_session_detail(root)
    # Status-based shortcut fires before event scan: "Agent is waiting for input"
    assert "waiting" in detail["currentFocus"].lower() or "input" in detail["currentFocus"].lower()
    assert detail["currentActivity"]["kind"] == "awaiting_input"
    assert detail["waitingFor"]["kind"] == "question_asked"


def test_detail_current_focus_approval_requested(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(
        root, "approval_requested", content="Run verification script?", status="awaiting_approval"
    )
    session_files.update_state(root, status="awaiting_approval")

    detail = build_session_detail(root)
    assert "approval" in detail["currentFocus"].lower()
    assert detail["currentActivity"]["kind"] == "awaiting_approval"
    assert detail["waitingFor"]["kind"] == "approval_requested"


def test_detail_current_focus_completed_ready_for_review(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(root, status="completed", review_status="review")

    detail = build_session_detail(root)
    assert "review" in detail["currentFocus"].lower()


def test_detail_current_focus_completed_needs_changes(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(root, status="completed", review_status="needs_changes")

    detail = build_session_detail(root)
    assert "blocker" in detail["currentFocus"].lower() or "needs_changes" in detail["currentFocus"].lower() or "review" in detail["currentFocus"].lower()


def test_detail_current_focus_failed(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(root, status="failed")

    detail = build_session_detail(root)
    assert "failed" in detail["currentFocus"].lower()


def test_detail_current_focus_cancelled(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(root, status="cancelled")

    detail = build_session_detail(root)
    assert "cancelled" in detail["currentFocus"].lower()


def test_detail_current_focus_assistant_message(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "assistant_message", content="Reviewing the county labor ontology source.", status="running")

    detail = build_session_detail(root)
    assert "county labor" in detail["currentFocus"].lower()
    assert "county labor" in detail["thinkingSummary"].lower()
    assert detail["currentActivity"]["kind"] == "thinking"


def test_detail_current_focus_verification_started(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "verification_started", status="running")

    detail = build_session_detail(root)
    assert "verification" in detail["currentFocus"].lower()


def test_detail_prefers_latest_working_signal(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "assistant_message", content="Comparing source coverage for labor data.", status="running")
    session_files.append_event(root, "tool_call", name="bash", content="git diff --stat", status="running")
    session_files.append_event(root, "file_change_detected", path="topics/labor/source_notes.md", status="running")

    detail = build_session_detail(root)
    assert detail["currentActivity"]["kind"] == "editing_file"
    assert detail["workingOn"] == "topics/labor/source_notes.md"
    assert "Comparing source coverage" in detail["thinkingSummary"]


# ---------------------------------------------------------------------------
# Layer 2 – activity timeline
# ---------------------------------------------------------------------------


def test_detail_timeline_shape(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "assistant_message", content="Reviewing the ontology.", status="running")
    session_files.append_event(root, "tool_call", name="bash", status="running")

    detail = build_session_detail(root)
    assert len(detail["timeline"]) == 2

    first = detail["timeline"][0]
    assert first["eventType"] == "assistant_message"
    assert first["label"] == "Agent Message"
    assert "Reviewing" in first["summary"]
    assert "timestamp" in first
    assert "id" in first
    assert "raw" in first


def test_detail_timeline_labels_known_types(tmp_path: Path):
    root = _make_session(tmp_path)
    for etype in ("verification_started", "file_change_detected", "completed"):
        session_files.append_event(root, etype, status="running")

    detail = build_session_detail(root)
    label_map = {row["eventType"]: row["label"] for row in detail["timeline"]}
    assert label_map["verification_started"] == "Verification Started"
    assert label_map["file_change_detected"] == "File Changed"
    assert label_map["completed"] == "Completed"


def test_detail_event_count(tmp_path: Path):
    root = _make_session(tmp_path)
    for i in range(5):
        session_files.append_event(root, "assistant_message", content=f"msg {i}", status="running")

    detail = build_session_detail(root)
    assert detail["eventCount"] == 5


# ---------------------------------------------------------------------------
# Layer 3 – workspace and file activity
# ---------------------------------------------------------------------------


def test_detail_changed_files_deduplicated(tmp_path: Path):
    root = _make_session(tmp_path)
    for _ in range(3):
        session_files.append_event(root, "file_change_detected", path="topics/a.md", status="running")
    session_files.append_event(root, "file_change_detected", path="topics/b.md", status="running")

    detail = build_session_detail(root)
    assert detail["changedFiles"] == ["topics/a.md", "topics/b.md"]
    assert detail["changedFileCount"] == 2


def test_detail_changed_files_order_preserved(tmp_path: Path):
    root = _make_session(tmp_path)
    for path in ("z.md", "a.md", "m.md"):
        session_files.append_event(root, "file_change_detected", path=path, status="running")

    detail = build_session_detail(root)
    assert detail["changedFiles"] == ["z.md", "a.md", "m.md"]


def test_detail_workspace_fields(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(
        root,
        workspace_path="/tmp/workspace/coding/s1",
        workspace_branch="coding-s1",
        setup_status="passed",
        verification_status="failed",
        archive_status=None,
    )

    detail = build_session_detail(root)
    assert detail["workspacePath"] == "/tmp/workspace/coding/s1"
    assert detail["workspaceBranch"] == "coding-s1"
    assert detail["setupStatus"] == "passed"
    assert detail["verificationStatus"] == "failed"
    assert detail["archiveStatus"] is None


# ---------------------------------------------------------------------------
# Layer 4 – commands and messages
# ---------------------------------------------------------------------------


def test_detail_recent_messages_capped_at_10(tmp_path: Path):
    root = _make_session(tmp_path)
    for i in range(15):
        session_files.append_event(root, "assistant_message", content=f"msg {i}", status="running")

    detail = build_session_detail(root)
    assert len(detail["recentMessages"]) == 10
    # Most recent 10
    assert detail["recentMessages"][0]["content"] == "msg 5"
    assert detail["recentMessages"][-1]["content"] == "msg 14"


def test_detail_recent_commands_capped_at_10(tmp_path: Path):
    root = _make_session(tmp_path)
    for i in range(12):
        session_files.append_event(root, "tool_call", name=f"cmd_{i}", status="running")

    detail = build_session_detail(root)
    assert len(detail["recentCommands"]) == 10


def test_detail_recent_relays_capped_at_5(tmp_path: Path):
    root = _make_session(tmp_path)
    for i in range(7):
        session_files.append_event(root, "planner_relay", content=f"relay {i}", status="running")

    detail = build_session_detail(root)
    assert len(detail["recentRelays"]) == 5


def test_detail_pending_commands(tmp_path: Path):
    root = _make_session(tmp_path)
    c1 = session_files.append_command(root, "inject_message", content="hello")
    c2 = session_files.append_command(root, "inject_message", content="world")
    session_files.mark_command_processed(root, int(c1["id"]))

    detail = build_session_detail(root)
    assert len(detail["pendingCommands"]) == 1
    assert detail["pendingCommands"][0]["content"] == "world"


def test_detail_no_pending_commands_when_all_processed(tmp_path: Path):
    root = _make_session(tmp_path)
    c = session_files.append_command(root, "inject_message", content="hello")
    session_files.mark_command_processed(root, int(c["id"]))

    detail = build_session_detail(root)
    assert detail["pendingCommands"] == []


# ---------------------------------------------------------------------------
# Review files
# ---------------------------------------------------------------------------


def test_detail_review_files_present_after_refresh(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.update_state(root, status="completed", review_status="review")
    session_files.append_event(root, "assistant_message", content="Done.", status="completed")
    session_files.refresh_summary(root)

    detail = build_session_detail(root)
    for key in ("summary", "diff", "todos", "verification"):
        assert key in detail["reviewFiles"], f"Missing review file key: {key}"
        assert detail["reviewFiles"][key]["content"] is not None


def test_detail_review_files_relative_paths(tmp_path: Path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    session_root = session_files.ensure_session_root(
        project_root / "research_plan", "coding", "s99"
    )

    detail = build_session_detail(session_root, project_root)
    summary_path = detail["reviewFiles"]["summary"]["path"]
    assert not summary_path.startswith("/"), "Path should be relative to project_root"
    assert "research_plan" in summary_path


# ---------------------------------------------------------------------------
# lastEventSummary
# ---------------------------------------------------------------------------


def test_detail_last_event_summary(tmp_path: Path):
    root = _make_session(tmp_path)
    session_files.append_event(root, "assistant_message", content="Checking data sources.", status="running")

    detail = build_session_detail(root)
    assert detail["lastEventSummary"] is not None
    assert "Checking data sources." in detail["lastEventSummary"]
    assert "[assistant_message]" in detail["lastEventSummary"]


def test_detail_last_event_summary_none_for_empty_session(tmp_path: Path):
    root = _make_session(tmp_path)
    detail = build_session_detail(root)
    assert detail["lastEventSummary"] is None
