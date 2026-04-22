from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.services import llm_service, planner_service
from app.services.convex_client import convex
from app.services.role_runtime_service import (
    load_role_runtime_config,
    list_role_runtime_configs,
    read_project_skills,
    summarize_role_config,
)


PLANNER_MAX_TURNS = 8


def _planner_system_prompt(project: dict[str, Any], role_summaries: list[dict[str, Any]], skills: list[dict[str, str]]) -> str:
    role_lines = "\n".join(
        f"- {item['role']}: runner={item['runner']['default']}, bash={item['runner']['bash_access']}, writes={', '.join(item['permissions']['write']) or 'none'}"
        for item in role_summaries
    ) or "- no role configs found"
    skill_lines = "\n".join(f"- {item['path']}" for item in skills) or "- no project skills found"
    return f"""You are the planner for the RAIL project '{project['name']}' ({project['slug']}).

You are the only user-facing agent. Your job is to:
1. Understand the user's goal
2. Decide whether to answer directly, create tasks, or launch a worker
3. Preserve deep research capability using web/data/analysis tools
4. Use project role configs as the source of truth for runner choice, path policy, and skill access

Important operating rules:
- Prefer orchestration first, but you MAY use bash and skill files directly when needed.
- Keep one active worker run at a time.
- Use the role's default runner first; only override when necessary and record the reason.
- If a worker run requires approval, create/request the approval instead of bypassing it.
- Preserve compatibility with older setup/debug/research workflows by using the existing project/data tools.
- Be concise, concrete, and action-oriented.

Available role configs:
{role_lines}

Available project skills:
{skill_lines}
"""


def _planner_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_role_configs",
                "description": "List all repo-defined role configurations and their runner/path/tool policy.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_skills",
                "description": "List project skill markdown files available to the planner.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_skill",
                "description": "Read a project skill file by repo-relative path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_repo",
                "description": "Search the local project repo using ripgrep.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_bash",
                "description": "Run a bash command in the local project repo. Use sparingly and prefer orchestration when possible.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": "List planner tasks for the current project board.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "Create a planner task for a specific worker role. Uses the role's default runner unless overridden later.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "agent_role": {"type": "string"},
                        "repo_paths": {"type": "array", "items": {"type": "string"}},
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "description", "agent_role"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_task",
                "description": "Update task status or metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "status": {"type": "string"},
                        "approval_state": {"type": "string"},
                        "runner": {"type": "string"},
                    },
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "request_task_approval",
                "description": "Move a task into approval flow and create a pending approval record.",
                "parameters": {
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "launch_task_runner",
                "description": "Launch a worker session for an existing task, respecting sequential execution and role runner defaults. Optional runner_override_reason is recorded in task events.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "runner": {"type": "string"},
                        "runner_override_reason": {"type": "string"},
                    },
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_runner_sessions",
                "description": "List planner and worker sessions for the current project.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]


async def _run_shell(command: str, cwd: Path) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"error": "Command timed out after 60 seconds"}
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:12000],
        "stderr": stderr.decode("utf-8", errors="replace")[:12000],
    }


async def _execute_planner_tool(project: dict[str, Any], name: str, args: dict[str, Any]) -> dict[str, Any]:
    from app.routers.project_agent import _execute_project_tool, PROJECT_TOOLS_MERGED
    from app.runners import session_lifecycle

    if name in {tool["function"]["name"] for tool in PROJECT_TOOLS_MERGED}:
        return await _execute_project_tool(name, args, project["_id"])

    if name == "list_role_configs":
        return {"roles": [summarize_role_config(item) for item in list_role_runtime_configs(project)]}

    if name == "list_skills":
        skills = read_project_skills(project)
        return {"skills": [{"name": item["name"], "path": item["path"]} for item in skills]}

    if name == "read_skill":
        path = (args.get("path") or "").strip()
        for item in read_project_skills(project):
            if item["path"] == path or item["name"] == path:
                return {"path": item["path"], "content": item["content"]}
        return {"error": f"Skill not found: {path}"}

    if name == "search_repo":
        root = planner_service.project_root_from_record(project)
        if root is None:
            return {"error": "Project does not have a local repo path"}
        query = (args.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}
        return await _run_shell(f"rg -n {json.dumps(query)} .", root)

    if name == "run_bash":
        root = planner_service.project_root_from_record(project)
        if root is None:
            return {"error": "Project does not have a local repo path"}
        command = (args.get("command") or "").strip()
        if not command:
            return {"error": "command is required"}
        return await _run_shell(command, root)

    board = await planner_service.ensure_main_board(project["_id"])

    if name == "list_tasks":
        return {"tasks": await planner_service.list_tasks(board["_id"])}

    if name == "create_task":
        role = args["agent_role"]
        role_config = load_role_runtime_config(project, role)
        task = await planner_service.create_task(
            board_id=board["_id"],
            project_id=project["_id"],
            title=args["title"],
            description=args["description"],
            status="ready",
            agent_role=role,
            repo_paths=args.get("repo_paths") or [],
            acceptance_criteria=args.get("acceptance_criteria") or [],
            runner=role_config.policy.runner.default,
            approval_state="pending" if role_config.policy.runner.approval_required else "not_required",
        )
        await planner_service.sync_planner_files(project, board)
        return {"task": task, "role": summarize_role_config(role_config)}

    if name == "update_task":
        task_id = args["task_id"]
        await planner_service.update_task(
            task_id,
            status=args.get("status"),
            approval_state=args.get("approval_state"),
            runner=args.get("runner"),
        )
        tasks = await planner_service.list_tasks(board["_id"])
        await planner_service.sync_planner_files(project, board)
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        return {"task": task or {"_id": task_id}}

    if name == "request_task_approval":
        task_id = args["task_id"]
        tasks = await planner_service.list_tasks(board["_id"])
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        await planner_service.update_task(task_id, status="awaiting_approval", approval_state="pending")
        approval_id = await convex.mutation(
            "approvals:create",
            {
                "projectId": project["_id"],
                "taskId": task["_id"],
                "approvalType": "run_task",
                "status": "pending",
                "requestedByRole": "planner",
            },
        )
        await planner_service.sync_planner_files(project, board)
        return {"approvalId": approval_id, "taskId": task_id, "status": "awaiting_approval"}

    if name == "launch_task_runner":
        task_id = args["task_id"]
        tasks = await planner_service.list_tasks(board["_id"])
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}

        active_sessions = await convex.query("agent:listByProjectId", {"projectId": project["_id"], "limit": 50}) or []
        active_worker = next(
            (
                item for item in active_sessions
                if item.get("role") not in {None, "planner"}
                and item.get("status") in {"queued", "running", "awaiting_input", "awaiting_approval"}
            ),
            None,
        )
        if active_worker:
            return {"error": "A worker session is already active", "activeSession": active_worker}

        role_config = load_role_runtime_config(project, task["agentRole"])
        selected_runner = args.get("runner") or task.get("runner") or role_config.policy.runner.default
        selected_runner = selected_runner if selected_runner else role_config.policy.runner.default
        if selected_runner != role_config.policy.runner.default:
            await convex.mutation(
                "taskEvents:append",
                {
                    "taskId": task["_id"],
                    "eventType": "runner_override",
                    "payload": {
                        "runner": selected_runner,
                        "reason": args.get("runner_override_reason") or "planner_override",
                        "defaultRunner": role_config.policy.runner.default,
                    },
                },
            )

        approvals = await convex.query("approvals:listByProject", {"projectId": project["_id"], "limit": 100}) or []
        granted = any(
            item.get("taskId") == task["_id"] and item.get("status") == "granted"
            for item in approvals
        )
        if role_config.policy.runner.approval_required and not granted:
            await planner_service.update_task(str(task["_id"]), status="awaiting_approval", approval_state="pending", runner=selected_runner)
            approval_id = await convex.mutation(
                "approvals:create",
                {
                    "projectId": project["_id"],
                    "taskId": task["_id"],
                    "approvalType": "run_task",
                    "status": "pending",
                    "requestedByRole": "planner",
                },
            )
            await planner_service.sync_planner_files(project, board)
            return {"status": "awaiting_approval", "approvalId": approval_id, "taskId": task_id}

        result = await session_lifecycle.create_runner_session(
            project_id=project["_id"],
            project_slug=project["slug"],
            task_id=str(task["_id"]),
            runner_name=selected_runner,
            role=task["agentRole"],
            task_description=task["description"],
            repo_url=project.get("gitRepoUrl") or "",
            branch=project.get("defaultBranch") or "main",
            local_repo_path=project.get("localRepoPath"),
            allowed_paths=role_config.policy.paths.write or task.get("repoPaths") or [],
            acceptance_criteria=task.get("acceptanceCriteria") or [],
            agent_role_for_secrets=task["agentRole"],
        )
        await planner_service.update_task(str(task["_id"]), status="running", runner=selected_runner, approval_state="granted")
        await planner_service.sync_planner_files(project, board)
        return result

    if name == "list_runner_sessions":
        sessions = await convex.query("agent:listByProjectId", {"projectId": project["_id"], "limit": 50}) or []
        return {"sessions": sessions}

    return {"error": f"Unknown planner tool: {name}"}


async def run_planner_turn(
    *,
    project: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    role_summaries = [summarize_role_config(item) for item in list_role_runtime_configs(project)]
    skills = read_project_skills(project)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _planner_system_prompt(project, role_summaries, skills)},
    ]
    for item in history or []:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message})

    if persist:
        await planner_service.append_planner_message(
            project_id=project["_id"],
            role="user",
            content=user_message,
            message_type="chat",
        )

    assistant_text = ""
    for _ in range(PLANNER_MAX_TURNS):
        response = await llm_service.complete(
            messages=messages,
            model=model,
            tools=[*_planner_tools(), *__import__("app.routers.project_agent", fromlist=["PROJECT_TOOLS_MERGED"]).PROJECT_TOOLS_MERGED],
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        assistant_text = message.content or assistant_text
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ] if tool_calls else None,
            }
        )
        if not tool_calls:
            break
        for call in tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": call.function.arguments}
            result = await _execute_planner_tool(project, call.function.name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    if persist and assistant_text:
        await planner_service.append_planner_message(
            project_id=project["_id"],
            role="assistant",
            content=assistant_text,
            message_type="chat",
        )
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    board = await planner_service.ensure_main_board(project["_id"])
    return {
        "threadId": thread_id,
        "assistantMessage": assistant_text,
        "messages": list(reversed(await planner_service.list_planner_messages(project["_id"], thread_id=thread_id))),
        "tasks": await planner_service.list_tasks(board["_id"]),
    }
