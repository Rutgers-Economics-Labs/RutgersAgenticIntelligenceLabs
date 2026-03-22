"""
AI agent service for RAIL.

Implements a streaming, tool-using agent backed by any LiteLLM-compatible model.
The agent can autonomously: discover data sources, create configs, run hydration,
query the ontology, execute SQL, and run Python for ML/statistical analysis.

Yields SSE-ready event dicts throughout execution.
"""
import json
import time
from typing import AsyncGenerator

from app.core.config import settings

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI research assistant for RAIL (Rutgers Agentic Intelligence Labs).
RAIL is a platform for building and querying economic knowledge graphs from structured data sources.

You can autonomously help researchers by:
1. Discovering and configuring data sources (Census, FRED, World Bank, uploaded CSVs)
2. Writing YAML configs for API sources, ontology schemas, and hydration pipelines
3. Running data pipelines that populate a knowledge graph (OWL ontology backed by SQLite)
4. Querying the knowledge graph via SQL (DuckDB) or ontology search
5. Running statistical analysis with Python: panel regression, DiD, clustering, time-series

The knowledge graph uses these core classes: State, County, Municipality, Individual, Measure.

When a researcher asks a question:
- Think step-by-step about what data is needed
- Use your tools to get, create, or run what's needed
- Explain your findings clearly with concrete numbers

Always show your reasoning. When you write code or SQL, explain the results after seeing them.
Be concise and research-focused."""

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format — LiteLLM normalizes to each provider)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_data_registry",
            "description": (
                "Search the catalog of known data sources by topic, geography, or provider. "
                "Use this before creating an API config to find the correct series ID or endpoint."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for a known data source"},
                    "provider": {
                        "type": "string",
                        "enum": ["census", "fred", "worldbank", "bls"],
                        "description": "Optional provider filter",
                    },
                    "geography": {
                        "type": "string",
                        "enum": ["national", "state", "county", "msa"],
                        "description": "Optional geography filter",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_configs",
            "description": "List available API sources, ontology schemas, and pipeline configs stored in the platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {
                        "type": "string",
                        "enum": ["apis", "ontologies", "pipelines", "all"],
                        "description": "Which config type to list. Default 'all'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_config",
            "description": (
                "Create a new YAML config in the platform (API source, ontology schema, or pipeline). "
                "Use this to set up new data sources or pipelines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "config_type": {
                        "type": "string",
                        "enum": ["apis", "ontologies", "pipelines"],
                    },
                    "name": {"type": "string", "description": "Human-readable name"},
                    "slug": {"type": "string", "description": "Unique identifier (kebab-case)"},
                    "content": {"type": "string", "description": "Full YAML content"},
                },
                "required": ["config_type", "name", "slug", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_pipeline",
            "description": (
                "Trigger a hydration pipeline by slug. This fetches data and populates the knowledge graph. "
                "Returns the job ID and final status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_slug": {
                        "type": "string",
                        "description": "Slug of the pipeline config to run",
                    }
                },
                "required": ["pipeline_slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ontology",
            "description": "Query instances of an ontology class. Returns a list of entities with their properties.",
            "parameters": {
                "type": "object",
                "properties": {
                    "class_name": {
                        "type": "string",
                        "description": "OWL class name (e.g. State, County, Municipality, Measure)",
                    },
                    "search": {
                        "type": "string",
                        "description": "Optional keyword filter on entity names",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20)",
                        "default": 20,
                    },
                },
                "required": ["class_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Execute a SQL query against the DuckDB knowledge graph export. "
                "Tables correspond to OWL classes (State, County, Municipality, Measure, etc.). "
                "Use get_sql_schema first if you need to know the column names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "DuckDB SQL query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sql_schema",
            "description": "Get the DuckDB schema (table names and column names/types). Use this before writing SQL.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": (
                "Execute Python code with access to the knowledge graph data. "
                "Available helpers: sql(query) → DataFrame, get_table(name) → DataFrame, list_tables(). "
                "Also available: pd, np, smf (statsmodels), sm, sklearn, plt (matplotlib). "
                "Any DataFrame variable in scope is returned. Matplotlib figures are captured. "
                "Use for: regression, DiD, clustering, time-series analysis, custom transforms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_series_data",
            "description": "Fetch time-series data for a specific measure series ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "series_id": {
                        "type": "string",
                        "description": "Series identifier (e.g. NJUR, GDP_NJ)",
                    }
                },
                "required": ["series_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "Keyword search across all ontology entities. Returns matching entity summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional filter by class name(s)",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def _execute_tool(name: str, args: dict) -> dict:
    """Execute a named tool and return a JSON-serialisable result dict."""

    if name == "search_data_registry":
        from app.services import registry_service
        results = await registry_service.search_registry_entries(
            query_text=args["query"],
            provider=args.get("provider"),
            geography=args.get("geography"),
            limit=min(args.get("limit", 10), 20),
        )
        return {"results": results}

    if name == "list_configs":
        from app.services.convex_client import convex
        config_type = args.get("config_type", "all")
        result: dict = {}
        if config_type in ("apis", "all"):
            result["apis"] = await convex.query("configs:listApis", {})
        if config_type in ("ontologies", "all"):
            result["ontologies"] = await convex.query("configs:listOntologies", {})
        if config_type in ("pipelines", "all"):
            result["pipelines"] = await convex.query("configs:listPipelines", {})
        # Trim to just name/slug/tags for token efficiency
        for key in result:
            result[key] = [{"name": c["name"], "slug": c["slug"]} for c in (result[key] or [])]
        return result

    elif name == "create_config":
        from app.services.convex_client import convex
        config_type = args["config_type"]
        mutation_map = {
            "apis": "configs:createApi",
            "ontologies": "configs:createOntology",
            "pipelines": "configs:createPipeline",
        }
        import yaml as _yaml
        parsed = {}
        try:
            parsed = _yaml.safe_load(args["content"]) or {}
        except Exception:
            pass
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

    elif name == "run_pipeline":
        import asyncio
        from app.services.convex_client import convex
        from app.routers.jobs import _trigger_job  # internal helper

        pipeline_slug = args["pipeline_slug"]
        result = await _trigger_job(pipeline_slug)
        job_id = result["jobId"]

        # Poll until done (max 10 min)
        for _ in range(120):
            await asyncio.sleep(5)
            job = await convex.query("jobs:get", {"jobId": job_id})
            status = job.get("status", "unknown")
            if status in ("success", "failed", "cancelled"):
                return {"jobId": job_id, "status": status}
        return {"jobId": job_id, "status": "timeout", "message": "Job still running after 10 min"}

    elif name == "query_ontology":
        from app.services import ontology_service
        class_name = args["class_name"]
        search = args.get("search", "")
        limit = min(args.get("limit", 20), 100)
        result = await ontology_service._run(
            ontology_service.list_instances, class_name, 1, limit, search
        )
        # Trim properties for token efficiency
        items = result.get("items", [])
        return {"total": result.get("total", 0), "items": items[:limit]}

    elif name == "run_sql":
        from app.services import sql_service
        return sql_service.run_query(args["query"])

    elif name == "get_sql_schema":
        from app.services import sql_service
        return sql_service.get_schema()

    elif name == "execute_python":
        from app.services import code_runner
        return code_runner.run_code(args["code"])

    elif name == "get_series_data":
        from app.services import ontology_service
        data = await ontology_service._run(ontology_service.get_series_data, args["series_id"])
        return {"series_id": args["series_id"], "points": data}

    elif name == "search_entities":
        from app.services import ontology_service
        types = args.get("types")
        results = await ontology_service._run(
            ontology_service.search_entities, args["query"], types
        )
        return {"results": results}

    else:
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

async def run_chat(
    user_message: str,
    history: list[dict],
    model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Run the agent for one user message.

    `history` is the prior conversation (list of {role, content} dicts).
    Yields SSE event dicts:
      {"type": "text_delta",   "content": str}
      {"type": "tool_call",    "id": str, "name": str, "args": dict}
      {"type": "tool_result",  "id": str, "name": str, "result": any}
      {"type": "done",         "new_messages": list[dict]}
    """
    from app.services import llm_service

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    new_messages: list[dict] = [{"role": "user", "content": user_message}]

    # Agentic loop: keep calling until no tool calls remain
    max_turns = 10
    for _turn in range(max_turns):
        assistant_text = ""
        turn_tool_calls: list[dict] = []  # {id, name, args}

        async for event in llm_service.stream_agent(messages, TOOLS, model=model):
            if event["type"] == "text_delta":
                assistant_text += event["content"]
                yield event

            elif event["type"] == "tool_call":
                turn_tool_calls.append(event)
                yield event

            elif event["type"] == "_turn_end":
                # Build assistant message from this turn
                raw_tool_calls = event.get("raw_tool_calls", [])
                assistant_msg: dict = {"role": "assistant", "content": assistant_text or None}
                if raw_tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in raw_tool_calls
                    ]
                messages.append(assistant_msg)
                if assistant_text:
                    new_messages.append({"role": "assistant", "content": assistant_text})

                if not event["has_tool_calls"]:
                    # No more tools — we're done
                    yield {"type": "done", "new_messages": new_messages}
                    return

                # Execute each tool call and feed results back
                for tc_event in turn_tool_calls:
                    try:
                        result = await _execute_tool(tc_event["name"], tc_event["args"])
                    except Exception as exc:
                        result = {"error": str(exc)}

                    yield {"type": "tool_result", "id": tc_event["id"],
                           "name": tc_event["name"], "result": result}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_event["id"],
                        "content": json.dumps(result, default=str),
                    })

    # Safety: if we hit max_turns
    yield {"type": "done", "new_messages": new_messages}
