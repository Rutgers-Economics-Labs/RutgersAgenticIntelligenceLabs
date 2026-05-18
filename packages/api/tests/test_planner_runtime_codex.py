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


def test_run_codex_cli_once_uses_workspace_write_sandbox(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0

        async def communicate(self):
            return (b'{"type":"result","result":"ok"}\n', b"")

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = list(args)
        return _Proc()

    monkeypatch.setattr(planner_runtime.shutil, "which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(planner_runtime.settings, "codex_cli_command", "codex")
    monkeypatch.setattr(planner_runtime.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    raw = asyncio.run(planner_runtime._run_codex_cli_once(prompt="hello", cwd=None))

    assert raw == '{"type":"result","result":"ok"}\n'
    assert "--sandbox" in captured["args"]
    sandbox_index = captured["args"].index("--sandbox")
    assert captured["args"][sandbox_index + 1] == "workspace-write"
    assert "--full-auto" not in captured["args"]


def test_launch_task_runner_normalizes_default_runner(monkeypatch):
    from app.runners import session_lifecycle

    project = {"_id": "project-1", "slug": "demo", "name": "Demo", "gitRepoUrl": "", "defaultBranch": "main", "localRepoPath": "/tmp/demo"}
    launched = {}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Propose questions",
                "description": "Planner follow-up",
                "status": "ready",
                "agentRole": "planner",
                "runner": "default",
                "repoPaths": ["research_plan", "topics"],
                "acceptanceCriteria": [],
            }
        ]

    async def _find_active_worker(project_id):
        return None

    async def _list_approvals(project_arg):
        return [{"taskId": "task-1", "status": "granted"}]

    async def _create_runner_session(**kwargs):
        launched.update(kwargs)
        return {"convex_session_id": "sess-1", "status": "running"}

    async def _update_task(*args, **kwargs):
        return None

    async def _sync_planner_files(*args, **kwargs):
        return None

    monkeypatch.setattr(planner_runtime.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(planner_runtime.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(planner_runtime.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(planner_runtime.planner_service, "update_task", _update_task)
    monkeypatch.setattr(planner_runtime.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(planner_runtime.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(session_lifecycle, "create_runner_session", _create_runner_session)
    monkeypatch.setattr(
        planner_runtime,
        "load_role_runtime_config",
        lambda project_arg, role: SimpleNamespace(
            role="planner",
            project_root="/tmp/demo",
            manifest=SimpleNamespace(),
            policy=SimpleNamespace(
                runner=SimpleNamespace(default="codex_cli"),
                paths=SimpleNamespace(write=["research_plan", "topics"]),
            ),
        ),
    )
    monkeypatch.setattr(planner_runtime, "evaluate_integrity_gate", lambda *args, **kwargs: {"blocked": False})
    monkeypatch.setattr(
        planner_runtime,
        "evaluate_autonomy_policy",
        lambda *args, **kwargs: SimpleNamespace(blocked=False, requires_human_approval=False, reason="", boundary=""),
    )
    monkeypatch.setattr(planner_runtime, "activity_key_for_role", lambda role: "planner")
    monkeypatch.setattr(planner_runtime, "is_write_capable", lambda **kwargs: True)

    result = asyncio.run(planner_runtime._execute_planner_tool(project, "launch_task_runner", {"task_id": "task-1"}))

    assert result["status"] == "running"
    assert launched["runner_name"] == "codex_cli"


def test_planner_system_prompt_includes_role_checklist_contracts():
    prompt = planner_runtime._planner_system_prompt(
        {"name": "Demo", "slug": "demo"},
        [
            {
                "role": "research",
                "runner": {"default": "codex_cli", "bash_access": "workspace-write"},
                "permissions": {"write": ["topics", "artifacts"]},
                "completion": {"requires": ["task_documented", "evidence_recorded"]},
                "promptFiles": {"checklist": "agents/checklists/research.md"},
            }
        ],
        [{"path": "skills/web-research.md", "content": "# Web Research"}],
    )

    assert "checklist=agents/checklists/research.md" in prompt
    assert "completion=task_documented, evidence_recorded" in prompt
