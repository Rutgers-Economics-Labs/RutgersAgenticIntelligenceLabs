from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

async def _unused_acompletion(**kwargs):
    raise AssertionError("LiteLLM should not be called in codex planner tests")


sys.modules.setdefault(
    "litellm",
    SimpleNamespace(
        acompletion=_unused_acompletion,
        success_callback=[],
        set_verbose=False,
    ),
)

from app.services import planner_runtime


def test_parse_codex_planner_response_prefers_structured_json():
    raw_output = "\n".join(
        [
            '{"type":"item.completed","item":{"type":"agent_message","text":"thinking"}}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"assistant_message\\":\\"Plan updated\\",\\"tool_calls\\":[{\\"name\\":\\"list_tasks\\",\\"arguments\\":{}}]}"}}',
        ]
    )

    parsed = planner_runtime._parse_codex_planner_response(raw_output)

    assert parsed["assistant_message"] == "Plan updated"
    assert parsed["tool_calls"][0]["name"] == "list_tasks"


def test_run_planner_turn_uses_codex_cli_when_planner_runner_is_codex(monkeypatch):
    async def _append_planner_message(**kwargs):
        return None

    async def _ensure_main_board(project):
        return {"_id": "board-1"}

    async def _list_tasks(board_id, project=None):
        return [{"_id": "task-1", "title": "Inspect repo", "status": "ready", "agentRole": "coding"}]

    async def _ensure_planner_thread(project_id):
        return "planner"

    async def _fake_execute_tool(project, name, args):
        assert name == "list_tasks"
        assert args == {}
        return {"tasks": [{"_id": "task-1"}]}

    calls = {"codex": 0, "llm": 0}

    async def _fake_codex_step(*, project, messages, tools):
        calls["codex"] += 1
        if calls["codex"] == 1:
            return "I checked the current task board.", [{"id": "tool-1", "name": "list_tasks", "args": {}}]
        return "I checked the current task board.", []

    async def _fake_complete(**kwargs):
        calls["llm"] += 1
        raise AssertionError("LLM path should not run when planner uses codex_cli")

    monkeypatch.setattr(planner_runtime, "_planner_uses_codex_cli", lambda project: True)
    monkeypatch.setattr(planner_runtime, "_codex_planner_step", _fake_codex_step)
    monkeypatch.setattr(planner_runtime, "_execute_planner_tool", _fake_execute_tool)
    monkeypatch.setattr(planner_runtime.llm_service, "complete", _fake_complete)
    monkeypatch.setattr(planner_runtime.planner_service, "append_planner_message", _append_planner_message)
    monkeypatch.setattr(planner_runtime.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(planner_runtime.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(planner_runtime.planner_service, "ensure_planner_thread", _ensure_planner_thread)
    monkeypatch.setattr(planner_runtime, "_planner_messages", lambda project, user_message, history: [{"role": "user", "content": user_message}])
    monkeypatch.setattr(planner_runtime, "_planner_tools_with_project_tools", lambda: [{"function": {"name": "list_tasks"}}])

    result = asyncio.run(
        planner_runtime.run_planner_turn(
            project={"_id": "project-1", "slug": "demo", "name": "Demo"},
            user_message="What should we do next?",
            history=[],
            persist=True,
        )
    )

    assert calls["codex"] == 2
    assert calls["llm"] == 0
    assert result["threadId"] == "planner"
    assert result["assistantMessage"] == "I checked the current task board."
