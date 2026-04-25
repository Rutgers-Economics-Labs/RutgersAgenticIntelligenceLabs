from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.base import RunnerEventType
from app.runners.claude_code import ClaudeCodeRunner
from app.runners.codex_cli import CodexCliRunner
from app.runners.cursor_cli import CursorCliRunner
from app.runners.gemini_cli import GeminiCliRunner


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
    runner = CursorCliRunner(command="cursor")
    args = runner._command_args("hello", _task_payload())

    assert args[:2] == ["cursor", "agent"]
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
