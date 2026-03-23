"""
Project-aware AI agent for the RAIL project dashboard.

Provides a streaming chat endpoint with tools scoped to a specific project:
  - get_project_info        read the project's current state
  - list_available_configs  list ontologies / apis / pipelines to choose from
  - link_ontology           set the project's ontology
  - link_pipeline           set the project's pipeline
  - add_data_source         attach an API config to the project
  - remove_data_source      detach an API config from the project
  - run_hydration           trigger the project's hydration pipeline
  - get_recent_jobs         list the most recent jobs for this project
  - get_job_logs            fetch log lines for a specific job
  - create_config           create a new YAML config (delegates to agent_service)
  - search_data_registry    search the data registry (delegates to agent_service)
"""

import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import llm_service

router = APIRouter(prefix="/project-agent", tags=["project-agent"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ProjectChatRequest(BaseModel):
    project_id: str
    message: str
    history: list[dict] = []
    model: str | None = None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PROJECT_SYSTEM_PROMPT = """You are a project assistant for RAIL (Rutgers Agentic Intelligence Labs).
You help researchers set up and debug their data projects.

You have access to tools to:
1. Read the project's current configuration
2. Link an ontology, pipeline, or data sources to the project
3. Create new YAML configs (ontology, api source, pipeline)
4. Run the hydration pipeline to populate the knowledge graph
5. Inspect job logs to debug failures
6. Search the data registry for available datasets

When the user asks to set something up:
- First call get_project_info to understand the current state
- Then take the appropriate action using the available tools
- Always confirm what you did and what changed

When debugging a pipeline failure:
- Get recent jobs with get_recent_jobs
- Fetch logs with get_job_logs
- Explain the error clearly and suggest a fix

Be concise, specific, and proactive. Don't just describe — take action."""


# ---------------------------------------------------------------------------
# Project-specific tools
# ---------------------------------------------------------------------------

PROJECT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": "Get the current state of the project: ontology, data sources, pipeline, status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_configs",
            "description": "List available ontology, API, or pipeline configs that can be linked to this project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {
                        "type": "string",
                        "enum": ["ontologies", "apis", "pipelines", "all"],
                        "description": "Which type of config to list.",
                    }
                },
                "required": ["config_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_ontology",
            "description": "Set the project's ontology config by slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "The ontology config slug to link."}
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_pipeline",
            "description": "Set the project's hydration pipeline config by slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "The pipeline config slug to link."}
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_data_source",
            "description": "Attach an API/data source config to the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "The API config slug to attach."}
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_data_source",
            "description": "Detach an API/data source config from the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "The API config slug to remove."}
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_hydration",
            "description": "Trigger the project's hydration pipeline. Only call this if the project has a pipeline configured.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_jobs",
            "description": "Get the most recent hydration jobs for this project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of jobs to return (default 5)."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_logs",
            "description": "Fetch log lines for a specific job to debug errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job ID to fetch logs for."}
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_config",
            "description": "Create a new YAML config (ontology, api source, or pipeline) in the platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {"type": "string", "enum": ["apis", "ontologies", "pipelines"]},
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "content": {"type": "string", "description": "Full YAML content."},
                },
                "required": ["config_type", "name", "slug", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_data_registry",
            "description": "Search the catalog of known data sources (Census, FRED, World Bank, etc.) by topic or geography.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "provider": {"type": "string"},
                    "geography": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def _execute_project_tool(name: str, args: dict, project_id: str) -> dict:
    if name == "get_project_info":
        project = await convex.query("projects:getById", {"projectId": project_id})
        if not project:
            return {"error": "Project not found"}
        return {
            "name": project.get("name"),
            "slug": project.get("slug"),
            "status": project.get("status"),
            "ontologyConfigSlug": project.get("ontologyConfigSlug"),
            "pipelineConfigSlug": project.get("pipelineConfigSlug"),
            "apiConfigSlugs": project.get("apiConfigSlugs", []),
        }

    if name == "list_available_configs":
        config_type = args.get("config_type", "all")
        result: dict = {}
        if config_type in ("apis", "all"):
            items = await convex.query("configs:listApis", {}) or []
            result["apis"] = [{"name": c["name"], "slug": c["slug"]} for c in items]
        if config_type in ("ontologies", "all"):
            items = await convex.query("configs:listOntologies", {}) or []
            result["ontologies"] = [{"name": c["name"], "slug": c["slug"]} for c in items]
        if config_type in ("pipelines", "all"):
            items = await convex.query("configs:listPipelines", {}) or []
            result["pipelines"] = [{"name": c["name"], "slug": c["slug"]} for c in items]
        return result

    if name == "link_ontology":
        await convex.mutation("projects:updateById", {
            "projectId": project_id,
            "ontologyConfigSlug": args["slug"],
        })
        return {"linked": True, "ontologyConfigSlug": args["slug"]}

    if name == "link_pipeline":
        await convex.mutation("projects:updateById", {
            "projectId": project_id,
            "pipelineConfigSlug": args["slug"],
            "status": "ready",
        })
        return {"linked": True, "pipelineConfigSlug": args["slug"]}

    if name == "add_data_source":
        project = await convex.query("projects:getById", {"projectId": project_id})
        if not project:
            return {"error": "Project not found"}
        current = project.get("apiConfigSlugs", [])
        slug = args["slug"]
        if slug not in current:
            await convex.mutation("projects:updateById", {
                "projectId": project_id,
                "apiConfigSlugs": [*current, slug],
            })
        return {"added": True, "slug": slug}

    if name == "remove_data_source":
        project = await convex.query("projects:getById", {"projectId": project_id})
        if not project:
            return {"error": "Project not found"}
        current = project.get("apiConfigSlugs", [])
        slug = args["slug"]
        await convex.mutation("projects:updateById", {
            "projectId": project_id,
            "apiConfigSlugs": [s for s in current if s != slug],
        })
        return {"removed": True, "slug": slug}

    if name == "run_hydration":
        project = await convex.query("projects:getById", {"projectId": project_id})
        if not project:
            return {"error": "Project not found"}
        pipeline_slug = project.get("pipelineConfigSlug")
        if not pipeline_slug:
            return {"error": "No pipeline configured for this project. Link a pipeline first."}
        from app.routers.jobs import _trigger_job
        result = await _trigger_job(pipeline_slug, project_id)
        return {"jobId": result["jobId"], "status": result["status"], "message": "Hydration job started."}

    if name == "get_recent_jobs":
        limit = min(args.get("limit", 5), 20)
        jobs = await convex.query("jobs:listByProject", {"projectId": project_id, "limit": limit})
        if not jobs:
            return {"jobs": []}
        return {"jobs": [
            {
                "jobId": j["_id"],
                "status": j.get("status"),
                "createdAt": j.get("createdAt"),
                "errorMessage": j.get("errorMessage"),
                "stepResults": j.get("stepResults", []),
            }
            for j in (jobs or [])
        ]}

    if name == "get_job_logs":
        job_id = args["job_id"]
        logs = await convex.query("jobs:getLogs", {"jobId": job_id, "limit": 200})
        if not logs:
            return {"logs": []}
        lines = [f"[{l.get('level', 'info')}] {l.get('message', '')}" for l in logs]
        return {"logs": lines, "count": len(lines)}

    if name == "create_config":
        import yaml as _yaml
        parsed = {}
        try:
            parsed = _yaml.safe_load(args["content"]) or {}
        except Exception:
            pass
        config_type = args["config_type"]
        mutation_map = {
            "apis": "configs:createApi",
            "ontologies": "configs:createOntology",
            "pipelines": "configs:createPipeline",
        }
        payload = {
            "name": args["name"],
            "slug": args["slug"],
            "content": args["content"],
            "parsedSpec": parsed,
            "isPublic": False,
            "tags": [],
            "createdAt": int(time.time() * 1000),
            "updatedAt": int(time.time() * 1000),
        }
        if config_type == "ontologies":
            payload["ontologyUri"] = parsed.get("uri", "")
        if config_type == "pipelines":
            steps = parsed.get("steps", [])
            payload["referencedApiSlugs"] = [s["api"] for s in steps if "api" in s]
        await convex.mutation(mutation_map[config_type], payload)
        return {"created": True, "slug": args["slug"], "type": config_type}

    if name == "search_data_registry":
        from app.services import registry_service
        results = await registry_service.search_registry_entries(
            query_text=args["query"],
            provider=args.get("provider"),
            geography=args.get("geography"),
            limit=min(args.get("limit", 10), 20),
        )
        return {"results": results}

    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def _run_project_chat(
    project_id: str,
    user_message: str,
    history: list[dict],
    model: str | None,
) -> AsyncGenerator[dict, None]:
    messages = [{"role": "system", "content": PROJECT_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    new_messages: list[dict] = [{"role": "user", "content": user_message}]

    max_turns = 8
    for _turn in range(max_turns):
        assistant_text = ""
        turn_tool_calls: list[dict] = []

        async for event in llm_service.stream_agent(messages, PROJECT_TOOLS, model=model):
            if event["type"] == "text_delta":
                assistant_text += event["content"]
                yield event
            elif event["type"] == "tool_call":
                turn_tool_calls.append(event)
                yield event
            elif event["type"] == "_turn_end":
                raw_tool_calls = event.get("raw_tool_calls", [])
                assistant_msg: dict = {"role": "assistant", "content": assistant_text or None}
                if raw_tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in raw_tool_calls
                    ]
                messages.append(assistant_msg)
                if assistant_text:
                    new_messages.append({"role": "assistant", "content": assistant_text})

                if not event["has_tool_calls"]:
                    yield {"type": "done", "new_messages": new_messages}
                    return

                for tc_event in turn_tool_calls:
                    try:
                        result = await _execute_project_tool(tc_event["name"], tc_event["args"], project_id)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    yield {"type": "tool_result", "id": tc_event["id"], "name": tc_event["name"], "result": result}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_event["id"],
                        "content": json.dumps(result),
                    })
                turn_tool_calls = []

    yield {"type": "done", "new_messages": new_messages}


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

@router.post("/chat")
async def project_chat(req: ProjectChatRequest):
    async def event_stream():
        try:
            async for event in _run_project_chat(
                req.project_id,
                req.message,
                req.history,
                req.model,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
