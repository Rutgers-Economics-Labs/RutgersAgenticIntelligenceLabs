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

import asyncio
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
You help researchers set up, configure, and debug their data hydration projects.

## Platform overview
A RAIL project has these components:
- **Ontology** (one) — OWL schema defining classes and properties (e.g. "nj-ontology")
- **Data sources** (many) — API configs that pull from Census, FRED, World Bank, CSV, etc.
- **Pipeline** (one) — hydration pipeline that transforms data sources into the ontology
- **Status**: draft → ready → hydrated

## Your tools and WHEN to use them

### get_project_info
Call this FIRST on every new conversation or when the user asks about project state.
Returns: name, slug, status, ontologyConfigSlug, pipelineConfigSlug, apiConfigSlugs[]

### list_available_configs
Use this to discover what configs exist before linking them.
- config_type = "ontologies" | "apis" | "pipelines" | "all"
- Always call this before link_ontology / link_pipeline / add_data_source so you know valid slugs

### link_ontology(slug)
Set the project's ontology. Get valid slugs from list_available_configs first.
Example: link_ontology(slug="nj-ontology")

### link_pipeline(slug)
Set the project's hydration pipeline. Also sets status to "ready".
Example: link_pipeline(slug="nj-census-pipeline")

### add_data_source(slug) / remove_data_source(slug)
Attach or detach an API config from the project.
Example: add_data_source(slug="census-acs5-nj")

### run_hydration
Kick off the hydration job. Only call after the project has a pipeline linked.
Returns jobId — you can then watch it with get_recent_jobs.

### get_recent_jobs(limit=5)
List recent hydration jobs with their status and any error messages.
Call this after run_hydration to check progress, or when debugging failures.
Returns: list of {jobId, status, createdAt, errorMessage, stepResults[]}

### get_job_logs(job_id)
Fetch detailed log lines for a specific job. Use the jobId from get_recent_jobs.
Returns: list of log lines like "[info] Fetching Census ACS5 data..."
Call this when a job has status "failed" to diagnose the root cause.

### create_config(config_type, name, slug, content)
Create a new YAML config. config_type = "ontologies" | "apis" | "pipelines"
content = full valid YAML string. Use this when the user wants to add a new data source or pipeline.

### search_data_registry(query, provider?, geography?, limit?)
Search the catalog of known datasets (Census ACS5, FRED series, World Bank indicators, etc.)
Use this when the user wants to know what data is available or what to add to their project.
Example: search_data_registry(query="unemployment rate", geography="New Jersey")

## Standard workflows

### "What's the state of my project?"
1. get_project_info → report what's linked and what's missing

### "Set up my project" / "Help me get started"
1. get_project_info → see what's already configured
2. list_available_configs(config_type="all") → show what's available
3. link_ontology, link_pipeline, add_data_source as needed
4. Confirm what you set up

### "Run hydration" / "Hydrate my project"
1. get_project_info → confirm pipeline is linked
2. run_hydration → get jobId
3. get_recent_jobs → report status

### "Why did my pipeline fail?" / "Debug my hydration"
1. get_recent_jobs → find the failed job's jobId
2. get_job_logs(job_id=<id>) → read the error
3. Explain the root cause and suggest a fix

### "Add data from Census / FRED / World Bank"
1. search_data_registry(query=<topic>) → find matching datasets
2. list_available_configs(config_type="apis") → check if config already exists
3. If not: create_config with proper YAML, then add_data_source
4. If yes: add_data_source(slug=<existing slug>)

### save_to_knowledge_base(name, content)
Save a research note, compiled analysis, or configuration summary to the project knowledge base.
Use this to persist important findings so they can be retrieved in future Q&A sessions.

## Rules
- Always call get_project_info at the start of a new conversation before anything else
- Always call list_available_configs before linking anything — never guess slugs
- Never run_hydration unless a pipeline is linked
- Be concise but specific — tell the user exactly what you changed
- If a tool returns an error, explain it clearly and try an alternative approach
- After creating a new data source config, save a summary to the knowledge base"""


# ---------------------------------------------------------------------------
# Project-specific tools
# ---------------------------------------------------------------------------

PROJECT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": (
                "Get the current state of this project. Returns the project name, slug, status "
                "(draft/ready/hydrated), linked ontologyConfigSlug, pipelineConfigSlug, and list of "
                "apiConfigSlugs. Call this first at the start of every conversation."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_configs",
            "description": (
                "List configs that exist in the platform and can be linked to this project. "
                "Always call this before link_ontology, link_pipeline, or add_data_source "
                "to discover valid slugs — never guess a slug."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {
                        "type": "string",
                        "enum": ["ontologies", "apis", "pipelines", "all"],
                        "description": (
                            "Which config type to list. Use 'all' to see everything at once. "
                            "Use 'ontologies' / 'apis' / 'pipelines' for a specific type."
                        ),
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
            "description": (
                "Set this project's ontology config. Use a slug from list_available_configs. "
                "An ontology defines the OWL classes and properties for the knowledge graph."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Exact slug of the ontology config (from list_available_configs).",
                    }
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_pipeline",
            "description": (
                "Set this project's hydration pipeline config and mark the project as 'ready'. "
                "Use a slug from list_available_configs. A pipeline defines which steps run "
                "to transform data sources into the ontology."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Exact slug of the pipeline config (from list_available_configs).",
                    }
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_data_source",
            "description": (
                "Attach an API/data source config to this project. "
                "Use a slug from list_available_configs(config_type='apis'). "
                "A project can have multiple data sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Exact slug of the API config to attach.",
                    }
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_data_source",
            "description": "Detach an API/data source config from this project by its slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Exact slug of the API config to detach.",
                    }
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_hydration",
            "description": (
                "Start the hydration job for this project. Requires a pipeline to be linked first. "
                "Returns a jobId. After calling this, use get_recent_jobs to check progress."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_jobs",
            "description": (
                "List the most recent hydration jobs for this project. "
                "Each job has: jobId, status (queued/running/success/failed/cancelled), "
                "createdAt, errorMessage, stepResults[]. "
                "Use this to check if hydration succeeded or to find a failed jobId to debug."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of jobs to return. Default 5, max 20.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_logs",
            "description": (
                "Fetch detailed log lines for a specific hydration job. "
                "Use the jobId from get_recent_jobs. "
                "Returns log lines like '[error] Failed to fetch Census data: ...'. "
                "Call this when a job has status 'failed' to diagnose the root cause."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The jobId string from get_recent_jobs output.",
                    }
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_config",
            "description": (
                "Create a new YAML config in the platform (ontology, API source, or pipeline). "
                "Use this when the user wants to add a new data source or pipeline that doesn't exist yet. "
                "After creating, call add_data_source or link_pipeline to attach it to the project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {
                        "type": "string",
                        "enum": ["apis", "ontologies", "pipelines"],
                        "description": "Type of config to create.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable name, e.g. 'Census ACS5 New Jersey'.",
                    },
                    "slug": {
                        "type": "string",
                        "description": "URL-safe slug, e.g. 'census-acs5-nj'. Must be unique.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full YAML content for the config.",
                    },
                },
                "required": ["config_type", "name", "slug", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_data_registry",
            "description": (
                "Search the catalog of known datasets available on the RAIL platform "
                "(Census ACS5, FRED economic series, World Bank indicators, etc.). "
                "Use this when the user wants to find what data is available on a topic or region."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic to search for, e.g. 'unemployment rate' or 'housing'.",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Filter by provider: 'census', 'fred', 'worldbank', etc. Optional.",
                    },
                    "geography": {
                        "type": "string",
                        "description": "Filter by geography, e.g. 'New Jersey', 'US'. Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return. Default 10.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_knowledge_base",
            "description": (
                "Save a piece of text, research note, or compiled analysis to the project knowledge base "
                "so it can be retrieved in future queries. Use this to persist important findings, "
                "configuration notes, or synthesized information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "A descriptive title for this document",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to save",
                    },
                },
                "required": ["name", "content"],
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
        from app.services.pipeline_validate import PipelineValidationFailed
        try:
            result = await _trigger_job(pipeline_slug, project_id)
        except PipelineValidationFailed as e:
            return {
                "error": "pipeline_validation_failed",
                "errors": e.errors,
                "message": "Fix validation errors before running hydration.",
            }
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

    if name == "save_to_knowledge_base":
        import time as _time
        now = int(_time.time() * 1000)
        payload = {
            "name": args["name"],
            "type": "text",
            "content": args["content"],
            "projectId": project_id,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            doc_id = await convex.mutation("context:create", payload)
            return {"saved": True, "id": doc_id, "name": args["name"]}
        except Exception as e:
            return {"saved": False, "error": str(e)}

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


# ---------------------------------------------------------------------------
# Autonomous task endpoint — fire-and-forget agent run tracked as an execution job
# ---------------------------------------------------------------------------

class AgentTaskRequest(BaseModel):
    project_id: str
    goal: str          # The autonomous task description
    model: str | None = None
    max_turns: int = 20


@router.post("/task")
async def run_agent_task(req: AgentTaskRequest):
    """
    Fire off an autonomous agent task. The agent runs to completion without
    further user interaction. Progress is tracked in Convex as an executionJob.
    Returns {jobId} immediately; subscribe to Convex executions:get to watch.
    """
    now = int(time.time() * 1000)

    # Create a Convex execution job to track this agent run
    job_result = await convex.mutation("executions:create", {
        "type": "code",
        "input": req.goal,
        "projectId": req.project_id,
        "createdAt": now,
    })
    job_id = job_result["jobId"]

    async def _run():
        try:
            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "running",
                "startedAt": int(time.time() * 1000),
            })

            transcript: list[str] = []
            async for event in _run_project_chat(
                req.project_id,
                req.goal,
                history=[],
                model=req.model,
            ):
                if event.get("type") == "text_delta":
                    transcript.append(event["content"])
                elif event.get("type") == "tool_call":
                    transcript.append(f"\n[tool: {event['name']}]\n")
                elif event.get("type") == "tool_result":
                    result_preview = json.dumps(event.get("result", {}), default=str)[:300]
                    transcript.append(f"→ {result_preview}\n")

            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "success",
                "finishedAt": int(time.time() * 1000),
                "result": {"transcript": "".join(transcript)},
            })

        except Exception as exc:
            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "failed",
                "finishedAt": int(time.time() * 1000),
                "errorMessage": str(exc),
            })

    # Run in background — don't await
    asyncio.create_task(_run())

    return {"jobId": job_id}
