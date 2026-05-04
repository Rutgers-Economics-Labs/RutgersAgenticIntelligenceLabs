from __future__ import annotations

import asyncio
import json
import shlex
import shutil
import time
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import uuid4

from app.services import llm_service, planner_service
from app.services import running_agent_service
from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy, is_write_capable
from app.core.config import settings
from app.services.integrity_service import evaluate_integrity_gate
from app.services.role_runtime_service import (
    load_role_runtime_config,
    list_role_runtime_configs,
    read_project_skills,
    summarize_role_config,
)


PLANNER_MAX_TURNS = 8
DEFAULT_PLANNER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "planner.md"
PROJECT_PLANNER_PROMPT_PATH = Path("agents") / "prompts" / "planner.md"


def _default_planner_prompt() -> str:
    return DEFAULT_PLANNER_PROMPT_PATH.read_text(encoding="utf-8")


def _ensure_project_planner_prompt(project: dict[str, Any]) -> Path | None:
    root = planner_service.project_root_from_record(project)
    if root is None:
        return None
    path = root / PROJECT_PLANNER_PROMPT_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_default_planner_prompt(), encoding="utf-8")
    return path


def _render_prompt_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _planner_system_prompt(project: dict[str, Any], role_summaries: list[dict[str, Any]], skills: list[dict[str, str]]) -> str:
    role_lines = "\n".join(
        f"- {item['role']}: runner={item['runner']['default']}, bash={item['runner']['bash_access']}, writes={', '.join(item['permissions']['write']) or 'none'}"
        for item in role_summaries
    ) or "- no role configs found"
    skill_lines = "\n".join(f"- {item['path']}" for item in skills) or "- no project skills found"
    prompt_path = _ensure_project_planner_prompt(project)
    template = prompt_path.read_text(encoding="utf-8") if prompt_path else _default_planner_prompt()
    return _render_prompt_template(
        template,
        {
            "project_name": str(project.get("name") or "Untitled Project"),
            "project_slug": str(project.get("slug") or "unknown"),
            "role_lines": role_lines,
            "skill_lines": skill_lines,
        },
    )


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
                "description": "Update task status, description, or metadata. Always use this instead of writing files directly.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {"type": "string", "enum": ["backlog", "ready", "awaiting_approval", "running", "blocked", "review", "done", "cancelled"]},
                        "agent_role": {"type": "string"},
                        "runner": {"type": "string"},
                        "approval_state": {"type": "string"},
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                        "depends_on_task_ids": {"type": "array", "items": {"type": "string"}},
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
        {
            "type": "function",
            "function": {
                "name": "grant_approval",
                "description": "Grant a pending approval so a task runner can be launched. Call this when the user has confirmed they want to proceed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "approval_id": {"type": "string", "description": "The approval ID to grant"},
                        "note": {"type": "string", "description": "Optional resolution note"},
                    },
                    "required": ["approval_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "spawn_research_agents",
                "description": (
                    "Launch one or more Gemini-powered research subagents in parallel. "
                    "Each agent uses Google Search to research a specific topic and writes findings "
                    "to research/findings/{slug}/findings.md in the project repo. "
                    "Use this to gather information about data sources, APIs, literature, or any "
                    "topic before writing code or creating analysis tasks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agents": {
                            "type": "array",
                            "description": "List of research agents to spawn in parallel",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "focus": {"type": "string", "description": "Topic name, e.g. 'PJM Data Miner 2 API'"},
                                    "queries": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Specific questions to research, e.g. ['PJM Data Miner 2 API endpoint', 'PJM load data download format']",
                                    },
                                },
                                "required": ["focus", "queries"],
                            },
                        },
                        "extra_context": {
                            "type": "string",
                            "description": "Optional project context to give each subagent (research question, geography, time period, etc.)",
                        },
                    },
                    "required": ["agents"],
                },
            },
        },
    ]


def _planner_tools_with_project_tools() -> list[dict[str, Any]]:
    return [
        *_planner_tools(),
        *__import__("app.routers.project_agent", fromlist=["PROJECT_TOOLS_MERGED"]).PROJECT_TOOLS_MERGED,
    ]


def _planner_messages(
    project: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None,
) -> list[dict[str, Any]]:
    role_summaries = [summarize_role_config(item) for item in list_role_runtime_configs(project)]
    skills = read_project_skills(project)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _planner_system_prompt(project, role_summaries, skills)},
    ]
    for item in history or []:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def _planner_uses_codex_cli(project: dict[str, Any]) -> bool:
    try:
        config = load_role_runtime_config(project, "planner")
    except Exception:
        return False
    return config.policy.runner.default == "codex_cli"


def _build_codex_planner_prompt(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> str:
    return (
        "You are the planner agent for a RAIL project. "
        "You must decide whether to respond directly or request internal planner tool calls.\n\n"
        "Respond with exactly one JSON object and no markdown fences.\n"
        'Use this schema: {"assistant_message":"string","tool_calls":[{"name":"tool_name","arguments":{}}]}\n'
        "Rules:\n"
        "- Always include both keys.\n"
        "- If no tool call is needed, return an empty tool_calls array.\n"
        "- Only use tool names that appear in AVAILABLE_TOOLS.\n"
        "- Arguments must be valid JSON objects and should match the tool schemas.\n"
        "- After tool results are added to the conversation, use them before deciding on more work.\n"
        "- Keep assistant_message concise and user-facing.\n\n"
        f"AVAILABLE_TOOLS:\n{json.dumps(tools, indent=2, default=str)}\n\n"
        f"CONVERSATION:\n{json.dumps(messages, indent=2, default=str)}\n"
    )


async def _run_codex_cli_once(
    *,
    prompt: str,
    cwd: Path | None,
) -> str:
    command = (settings.codex_cli_command or "codex").strip()
    executable = shlex.split(command)[0] if command else ""
    if not executable or shutil.which(executable) is None:
        raise RuntimeError(
            f"Codex CLI is not available. Configure CODEX_CLI_COMMAND or install '{executable or 'codex'}'."
        )
    args = [
        *shlex.split(command),
        "exec",
        "--skip-git-repo-check",
        "--full-auto",
        "--json",
    ]
    if cwd is not None:
        args.extend(["--cd", str(cwd)])
    args.append(prompt)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Codex CLI planner run failed with exit code {proc.returncode}: "
            f"{stderr.decode('utf-8', errors='replace')[:4000]}"
        )
    return stdout.decode("utf-8", errors="replace")


def _extract_codex_assistant_fragments(raw_output: str) -> list[str]:
    fragments: list[str] = []
    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            fragments.append(line)
            continue
        if not isinstance(payload, dict):
            continue
        item = payload.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text") or item.get("message")
            if text:
                fragments.append(str(text))
            continue
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            content = payload.get("content")
            if content:
                fragments.append(str(content))
            continue
        if payload.get("type") == "result":
            result = payload.get("result")
            if isinstance(result, str) and result.strip():
                fragments.append(result)
    return fragments


def _parse_codex_planner_response(raw_output: str) -> dict[str, Any]:
    fragments = _extract_codex_assistant_fragments(raw_output)
    for text in reversed(fragments):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    combined = "\n".join(fragment.strip() for fragment in fragments if fragment.strip()).strip()
    if combined:
        return {"assistant_message": combined, "tool_calls": []}
    fallback = raw_output.strip()
    return {"assistant_message": fallback, "tool_calls": []}


async def _codex_planner_step(
    *,
    project: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    root = planner_service.project_root_from_record(project)
    raw_output = await _run_codex_cli_once(
        prompt=_build_codex_planner_prompt(messages, tools),
        cwd=root,
    )
    payload = _parse_codex_planner_response(raw_output)
    assistant_text = str(payload.get("assistant_message") or "").strip()
    tool_calls: list[dict[str, Any]] = []
    for index, call in enumerate(payload.get("tool_calls") or []):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "").strip()
        if not name:
            continue
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_calls.append(
            {
                "id": f"codex-tool-{uuid4().hex[:8]}-{index}",
                "name": name,
                "args": arguments,
            }
        )
    return assistant_text, tool_calls


async def _git_commit_and_push(project: dict[str, Any], message: str = "chore(planner): sync plan files") -> None:
    """Commit and push any changes the planner wrote to the project repo."""
    import logging
    log = logging.getLogger(__name__)
    root = planner_service.project_root_from_record(project)
    if root is None or not root.is_dir():
        return
    if not (root / ".git").is_dir():
        return
    try:
        proc = await asyncio.create_subprocess_shell(
            f'git add -A && git diff --cached --quiet || git commit -m "{message}" && git push 2>&1 || true',
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
    except Exception as exc:
        log.warning("planner git push failed for %s: %s", root, exc)


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

    board = await planner_service.ensure_main_board(project)

    if name == "list_tasks":
        return {"tasks": await planner_service.list_tasks(board["_id"], project=project)}

    if name == "create_task":
        role = args["agent_role"]
        role_config = load_role_runtime_config(project, role)
        decision = evaluate_autonomy_policy(
            role_config.manifest,
            action=activity_key_for_role(role_config.role),
            write_capable=is_write_capable(role_policy=role_config.policy),
        )
        task = await planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title=args["title"],
            description=args["description"],
            status="ready",
            agent_role=role,
            repo_paths=args.get("repo_paths") or [],
            acceptance_criteria=args.get("acceptance_criteria") or [],
            runner=role_config.policy.runner.default,
            approval_state="pending" if decision.requires_human_approval else "not_required",
        )
        await planner_service.sync_planner_files(project, board)
        return {"task": task, "role": summarize_role_config(role_config)}

    if name == "update_task":
        task_id = args["task_id"]
        await planner_service.update_task(
            task_id,
            project=project,
            title=args.get("title"),
            description=args.get("description"),
            status=args.get("status"),
            approval_state=args.get("approval_state"),
            runner=args.get("runner"),
            agentRole=args.get("agent_role"),
            acceptanceCriteria=args.get("acceptance_criteria"),
            dependsOnTaskIds=args.get("depends_on_task_ids"),
        )
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        await planner_service.sync_planner_files(project, board)
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        return {"task": task or {"_id": task_id}}

    if name == "request_task_approval":
        task_id = args["task_id"]
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        await planner_service.update_task(
            task_id,
            project=project,
            status="awaiting_approval",
            approval_state="pending",
        )
        approval_id = await planner_service.create_approval(
            project=project,
            task_id=task["_id"],
            agent_session_id=None,
            approval_type="run_task",
            status="pending",
            requested_by_role="planner",
        )
        await planner_service.sync_planner_files(project, board)
        return {"approvalId": approval_id, "taskId": task_id, "status": "awaiting_approval"}

    if name == "launch_task_runner":
        task_id = args["task_id"]
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        task = next((item for item in tasks if str(item["_id"]) == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}

        active_worker = await running_agent_service.find_active_worker(project["_id"])
        if active_worker:
            return {"error": "A worker session is already active", "activeSession": active_worker}

        role_config = load_role_runtime_config(project, task["agentRole"])
        selected_runner = args.get("runner") or task.get("runner") or role_config.policy.runner.default
        selected_runner = selected_runner if selected_runner else role_config.policy.runner.default
        write_paths = role_config.policy.paths.write or task.get("repoPaths") or []
        decision = evaluate_autonomy_policy(
            role_config.manifest,
            action=activity_key_for_role(role_config.role),
            write_capable=is_write_capable(role_policy=role_config.policy, allowed_paths=write_paths),
            integrity_blocked=evaluate_integrity_gate(
                role_config.project_root,
                role_config.manifest,
                action=activity_key_for_role(role_config.role),
            )["blocked"],
        )

        approvals = await planner_service.list_approvals(project)
        granted = any(
            item.get("taskId") == task["_id"] and item.get("status") == "granted"
            for item in approvals
        )
        if decision.blocked:
            await planner_service.update_task(
                str(task["_id"]),
                project=project,
                status="blocked",
                runner=selected_runner,
                latestRunSummary=decision.reason,
            )
            await planner_service.sync_planner_files(project, board)
            return {"status": "blocked", "taskId": task_id, "reason": decision.reason, "boundary": decision.boundary}

        if decision.requires_human_approval and not granted:
            await planner_service.update_task(
                str(task["_id"]),
                project=project,
                status="awaiting_approval",
                approval_state="pending",
                runner=selected_runner,
            )
            approval_id = await planner_service.create_approval(
                project=project,
                task_id=task["_id"],
                agent_session_id=None,
                approval_type="run_task",
                status="pending",
                requested_by_role="planner",
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
            allowed_paths=write_paths,
            acceptance_criteria=task.get("acceptanceCriteria") or [],
            agent_role_for_secrets=task["agentRole"],
            policy_approval_granted=granted,
        )
        await planner_service.update_task(
            str(task["_id"]),
            project=project,
            status="running",
            runner=selected_runner,
            approval_state="granted",
            latestRunSummary=f"Session {result['convex_session_id']} started with {selected_runner}",
        )
        await planner_service.sync_planner_files(project, board)
        return result

    if name == "list_runner_sessions":
        sessions = await running_agent_service.list_project_running_agents(
            project["_id"],
            active_only=False,
            limit=50,
        )
        return {"sessions": sessions}

    if name == "grant_approval":
        approval_id = args.get("approval_id", "").strip()
        note = args.get("note") or "Approved by user via chat."
        result = await planner_service.resolve_approval(
            project=project,
            approval_id=approval_id,
            status="granted",
            resolution_note=note,
        )
        if result is None:
            return {"error": f"Approval not found: {approval_id}"}
        # Also update the task's approvalState
        task_id = result.get("taskId")
        if task_id:
            await planner_service.update_task(task_id, project=project, approval_state="granted")
        return {"granted": True, "approvalId": approval_id, "taskId": task_id}

    if name == "spawn_research_agents":
        from app.services.research_subagent import run_research_agents
        agent_specs = args.get("agents", [])
        extra_context = args.get("extra_context", "")
        if not agent_specs:
            return {"error": "No agents specified"}
        results = await run_research_agents(
            project,
            agents=agent_specs,
            extra_context=extra_context,
        )
        # Commit findings to repo immediately
        await _git_commit_and_push(project, f"feat(research): add findings from {len(results)} research subagent(s)")
        successful = [r for r in results if not r.get("error")]
        failed = [r for r in results if r.get("error")]
        return {
            "completed": len(successful),
            "failed": len(failed),
            "results": results,
            "findings_dir": "research/findings/",
            "note": "Findings written to repo and committed. Read each findings.md to synthesize a plan.",
        }

    return {"error": f"Unknown planner tool: {name}"}


def _append_agent_log(
    project: dict[str, Any],
    user_message: str,
    assistant_text: str,
    tool_calls: list[dict],
) -> None:
    """Append one planner turn to research_plan/agent_log.jsonl in the project repo."""
    root = planner_service.project_root_from_record(project)
    if root is None:
        return
    log_path = root / "research_plan" / "agent_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user": user_message,
        "summary": assistant_text[:500],
        "tools": [
            {
                "name": tc["name"],
                "args": tc.get("args", {}),
                # truncate large results to keep the log readable
                "result_preview": str(tc.get("result", ""))[:300],
            }
            for tc in tool_calls
        ],
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


async def stream_planner_turn(
    *,
    project: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    persist: bool = True,
) -> AsyncGenerator[dict, None]:
    """
    Streaming version of run_planner_turn. Yields SSE-compatible event dicts:
      {"type": "text_delta",   "content": str}
      {"type": "tool_call",    "id": str, "name": str, "args": dict}
      {"type": "tool_result",  "id": str, "name": str, "result": any}
      {"type": "done",         "assistant_message": str, "tasks": list}
    """
    all_tools = _planner_tools_with_project_tools()
    messages = _planner_messages(project, user_message, history)

    if persist:
        await planner_service.append_planner_message(
            project=project, role="user", content=user_message, message_type="chat",
        )

    assistant_text = ""
    all_tool_calls_log: list[dict] = []   # for agent_log.jsonl

    if _planner_uses_codex_cli(project):
        for _ in range(PLANNER_MAX_TURNS):
            assistant_text, turn_tool_calls = await _codex_planner_step(
                project=project,
                messages=messages,
                tools=all_tools,
            )
            if assistant_text:
                yield {"type": "text_delta", "content": assistant_text}
            raw_tool_calls = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                for tc in turn_tool_calls
            ] if turn_tool_calls else None
            messages.append({
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": raw_tool_calls,
            })
            if not turn_tool_calls:
                break
            for tc in turn_tool_calls:
                yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "args": tc["args"]}
                try:
                    result = await _execute_planner_tool(project, tc["name"], tc["args"])
                except Exception as exc:
                    result = {"error": str(exc)}
                yield {"type": "tool_result", "id": tc["id"], "name": tc["name"], "result": result}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, default=str),
                })
                all_tool_calls_log.append({
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": result,
                })
    else:
        for _ in range(PLANNER_MAX_TURNS):
            turn_tool_calls: list[dict] = []
            turn_text = ""

            async for event in llm_service.stream_agent(messages, all_tools, model=model):
                if event["type"] == "text_delta":
                    turn_text += event["content"]
                    yield event
                elif event["type"] == "tool_call":
                    turn_tool_calls.append(event)
                    yield event

            if turn_text:
                assistant_text = turn_text

            raw_tool_calls = [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                for tc in turn_tool_calls
            ] if turn_tool_calls else None
            messages.append({
                "role": "assistant",
                "content": turn_text or None,
                "tool_calls": raw_tool_calls,
            })

            if not turn_tool_calls:
                break

            for tc in turn_tool_calls:
                try:
                    result = await _execute_planner_tool(project, tc["name"], tc["args"])
                except Exception as exc:
                    result = {"error": str(exc)}
                yield {"type": "tool_result", "id": tc["id"], "name": tc["name"], "result": result}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, default=str),
                })
                all_tool_calls_log.append({
                    "name": tc["name"],
                    "args": tc["args"],
                    "result": result,
                })

    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)

    # If the last turn ended on tool calls without text, force a summary turn
    if not assistant_text.strip():
        messages.append({
            "role": "user",
            "content": "Please write a concise summary of everything you just did and the current state of the project.",
        })
        summary_text = ""
        if _planner_uses_codex_cli(project):
            summary_text, _ = await _codex_planner_step(
                project=project,
                messages=messages,
                tools=[],
            )
            if summary_text:
                yield {"type": "text_delta", "content": summary_text}
        else:
            async for event in llm_service.stream_agent(messages, [], model=model):
                if event["type"] == "text_delta":
                    summary_text += event["content"]
                    yield event
        assistant_text = summary_text.strip() or (
            f"Done. {len(tasks)} task(s) on the board." if tasks else "Planner turn complete."
        )

    if persist and assistant_text:
        await planner_service.append_planner_message(
            project=project, role="assistant", content=assistant_text, message_type="chat",
        )

    # Write tool call log to repo
    _append_agent_log(project, user_message, assistant_text, all_tool_calls_log)

    await planner_service.sync_planner_files(project, board)
    await _git_commit_and_push(project, "chore(planner): sync plan and task files")
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    yield {"type": "done", "assistant_message": assistant_text, "tasks": tasks, "thread_id": thread_id}


async def run_planner_turn(
    *,
    project: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    model: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    messages = _planner_messages(project, user_message, history)
    all_tools = _planner_tools_with_project_tools()

    if persist:
        await planner_service.append_planner_message(
            project=project,
            role="user",
            content=user_message,
            message_type="chat",
        )

    assistant_text = ""
    for _ in range(PLANNER_MAX_TURNS):
        if _planner_uses_codex_cli(project):
            assistant_text, tool_calls = await _codex_planner_step(
                project=project,
                messages=messages,
                tools=all_tools,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_text or None,
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["args"]),
                            },
                        }
                        for call in tool_calls
                    ] if tool_calls else None,
                }
            )
        else:
            response = await llm_service.complete(
                messages=messages,
                model=model,
                tools=all_tools,
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
            if _planner_uses_codex_cli(project):
                args = call["args"]
                result = await _execute_planner_tool(project, call["name"], args)
                tool_call_id = call["id"]
            else:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": call.function.arguments}
                result = await _execute_planner_tool(project, call.function.name, args)
                tool_call_id = call.id
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, default=str),
                }
            )

    board = await planner_service.ensure_main_board(project)

    if not assistant_text.strip():
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        if tasks:
            assistant_text = f"Planner completed without a final summary. Current task count: {len(tasks)}."
        else:
            assistant_text = "Planner completed without a final summary."

    if persist and assistant_text:
        await planner_service.append_planner_message(
            project=project,
            role="assistant",
            content=assistant_text,
            message_type="chat",
        )
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    return {
        "threadId": thread_id,
        "assistantMessage": assistant_text,
        "messages": list(reversed(await planner_service.list_planner_messages(project, thread_id=thread_id))),
        "tasks": await planner_service.list_tasks(board["_id"], project=project),
    }
