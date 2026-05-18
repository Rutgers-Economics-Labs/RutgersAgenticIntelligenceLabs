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
from app.runners.cli_base import runner_runtime_paths


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
    assert "--sandbox" in args
    assert "workspace-write" in args
    assert "--full-auto" not in args
    assert "--cd" in args
    assert "hello" == args[-1]


def test_codex_cli_uses_danger_full_access_for_data_role():
    runner = CodexCliRunner(command="codex")
    payload = _task_payload()
    payload.role = "data"

    args = runner._command_args("hello", payload)

    assert "--sandbox" in args
    sandbox_index = args.index("--sandbox")
    assert args[sandbox_index + 1] == "danger-full-access"


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


def test_codex_cli_treats_turn_completed_as_terminal_success():
    runner = CodexCliRunner(command="codex")

    events = runner._derived_events_from_stdout_line(
        "sess-1",
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
    )

    assert events[0].event_type == RunnerEventType.COMPLETED
    assert events[0].normalized_payload["status"] == "completed"


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


async def _call_send_message(runner, session_id: str) -> None:
    await runner.send_message(session_id, "continue")


async def _call_approve(runner, session_id: str) -> None:
    await runner.approve(session_id, {"message": "approved"})


def test_local_cli_send_message_is_noop_for_detached_unknown_session():
    runner = CursorCliRunner(command="agent")

    import asyncio

    asyncio.run(_call_send_message(runner, "cursor_cli_detached"))


def test_local_cli_approve_is_noop_for_detached_unknown_session():
    runner = CursorCliRunner(command="agent")

    import asyncio

    asyncio.run(_call_approve(runner, "cursor_cli_detached"))


def test_local_cli_get_session_recovers_detached_file_backed_state(tmp_path, monkeypatch):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-detached")
    session_files.update_state(root, status="completed")
    runtime = runner_runtime_paths(str(root))
    runtime["root"].mkdir(parents=True, exist_ok=True)
    runtime["command"].write_text(
        '{"session_id":"cursor_cli_detached","runner":"cursor_cli","command":["agent","-p","hello"],"cwd":"/tmp/repo"}\n',
        encoding="utf-8",
    )
    runtime["stdout"].write_text("line 1\nline 2\n", encoding="utf-8")
    runtime["stderr"].write_text("warn 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    runner = CursorCliRunner(command="agent")

    import asyncio

    result = asyncio.run(runner.get_session("cursor_cli_detached"))

    assert result["status"] == "completed"
    assert result["normalized_status"] == RunnerEventType.COMPLETED.value
    assert "line 2" in result["stdout"]
    assert result["raw"]["session_root"].endswith("sess-detached")


def test_local_cli_list_events_recovers_detached_file_backed_state(tmp_path, monkeypatch):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-detached")
    session_files.append_event(root, "assistant_message", content="Reading README")
    session_files.append_event(root, "file_change_detected", path="notes.md")
    runtime = runner_runtime_paths(str(root))
    runtime["root"].mkdir(parents=True, exist_ok=True)
    runtime["command"].write_text(
        '{"session_id":"cursor_cli_detached","runner":"cursor_cli","command":["agent","-p","hello"],"cwd":"/tmp/repo"}\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    runner = CursorCliRunner(command="agent")

    import asyncio

    events = asyncio.run(runner.list_events("cursor_cli_detached"))

    assert events[0].event_type == RunnerEventType.PROGRESS
    assert events[0].normalized_payload["content"] == "Reading README"
    assert events[1].event_type == RunnerEventType.FILE_CHANGE_DETECTED
    assert events[1].normalized_payload["path"] == "notes.md"
