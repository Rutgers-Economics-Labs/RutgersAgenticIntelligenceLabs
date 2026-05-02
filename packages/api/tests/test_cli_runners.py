from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.base import RunnerEvent
from app.runners.base import RunnerEventType
from app.runners.claude_code import ClaudeCodeRunner
from app.runners.codex_cli import CodexCliRunner
from app.runners.cursor_cli import CursorCliRunner
from app.runners.gemini_cli import GeminiCliRunner
from app.services.session_detail_service import build_session_detail
from app.services import session_files


def _task_payload() -> TaskPayload:
    return TaskPayload(
        project_slug="rail-sad",
        role="coding",
        task_id="task-1",
        repo_url="https://github.com/Rutgers-Economics-Labs/RAIL-sad",
        branch="main",
        local_repo_path="/tmp/rail-sad",
        task_description="Create a small verification artifact.",
        allowed_paths=["research_plan", "artifacts"],
        acceptance_criteria=["writes a file", "summarizes the result"],
    )


def test_codex_cli_uses_exec_mode():
    runner = CodexCliRunner(command="codex")
    args = runner._command_args("hello", _task_payload())

    assert args[:2] == ["codex", "exec"]
    assert "--json" in args
    assert "--cd" in args
    assert "hello" == args[-1]


def test_claude_cli_uses_print_mode():
    runner = ClaudeCodeRunner(command="claude")
    args = runner._command_args("hello", _task_payload())

    assert "--print" in args
    assert "--output-format" in args
    assert "stream-json" in args
    assert "--permission-mode" in args


def test_gemini_cli_uses_headless_prompt_mode():
    runner = GeminiCliRunner(command="gemini")
    args = runner._command_args("hello", _task_payload())

    assert args[:1] == ["gemini"]
    assert "--prompt" in args
    assert "hello" in args
    assert "--approval-mode" in args
    assert "yolo" in args


def test_cursor_cli_uses_agent_subcommand():
    runner = CursorCliRunner(command="agent")
    args = runner._command_args("hello", _task_payload())

    assert args[:1] == ["agent"]
    assert args[-1] == "hello"


def test_codex_cli_derives_structured_events_from_jsonl():
    runner = CodexCliRunner(command="codex")

    file_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"/tmp/repo/file.txt","kind":"add"}]}}',
    )
    command_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"item.completed","item":{"type":"command_execution","command":"echo hi","aggregated_output":"hi","exit_code":0}}',
    )

    assert file_events[0].event_type == RunnerEventType.FILE_CHANGE_DETECTED
    assert file_events[0].normalized_payload["path"] == "/tmp/repo/file.txt"
    assert command_events[0].event_type == RunnerEventType.BASH_COMMAND_COMPLETED


def test_claude_cli_derives_progress_and_file_change_from_stream_json():
    runner = ClaudeCodeRunner(command="claude")

    text_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"assistant","message":{"content":[{"type":"text","text":"I will inspect the README first."}]}}',
    )
    file_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/tmp/repo/CLAUDE_NOTES.md","content":"x"}}]}}',
    )

    assert text_events[0].event_type == RunnerEventType.PROGRESS
    assert "inspect the README" in text_events[0].normalized_payload["message"]
    assert file_events[0].event_type == RunnerEventType.FILE_CHANGE_DETECTED
    assert file_events[0].normalized_payload["path"] == "/tmp/repo/CLAUDE_NOTES.md"


def test_cursor_cli_derives_progress_and_file_change_from_stream_json():
    runner = CursorCliRunner(command="agent")

    text_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Reading README.md and creating notes."}]}}',
    )
    file_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"tool_call","subtype":"completed","tool_call":{"editToolCall":{"args":{"path":"/tmp/repo/CURSOR_NOTES.md","streamContent":"- note"},"result":{"success":{"path":"/tmp/repo/CURSOR_NOTES.md"}}}}}',
    )

    assert text_events[0].event_type == RunnerEventType.PROGRESS
    assert "creating notes" in text_events[0].normalized_payload["message"]
    assert file_events[0].event_type == RunnerEventType.FILE_CHANGE_DETECTED
    assert file_events[0].normalized_payload["path"] == "/tmp/repo/CURSOR_NOTES.md"


def test_gemini_cli_derives_progress_and_file_change_from_stream_json():
    runner = GeminiCliRunner(command="gemini")

    progress_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"tool_use","tool_name":"update_topic","parameters":{"summary":"Reading README then writing GEMINI_NOTES.md"}}',
    )
    file_events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"tool_use","tool_name":"write_file","parameters":{"file_path":"GEMINI_NOTES.md","content":"- note"}}',
    )

    assert progress_events[0].event_type == RunnerEventType.PROGRESS
    assert "GEMINI_NOTES.md" in progress_events[0].normalized_payload["message"]
    assert file_events[0].event_type == RunnerEventType.FILE_CHANGE_DETECTED
    assert file_events[0].normalized_payload["path"] == "GEMINI_NOTES.md"


def test_local_cli_persisted_events_use_ui_aliases(tmp_path):
    root = session_files.ensure_session_root(tmp_path, "coding", "alias-test")
    runner = CursorCliRunner(command="agent")
    session = runner._sessions["alias"] = type("S", (), {"session_root": str(root)})()

    runner._persist_event(
        session,
        RunnerEvent(
            event_type=RunnerEventType.PROGRESS,
            session_id="alias",
            normalized_payload={"message": "Reading README.md"},
        ),
    )
    runner._persist_event(
        session,
        RunnerEvent(
            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
            session_id="alias",
            normalized_payload={"path": "CURSOR_NOTES.md"},
        ),
    )

    detail = build_session_detail(root)
    assert "Reading README" in (detail["thinkingSummary"] or "")
    assert detail["activeFile"] == "CURSOR_NOTES.md"
