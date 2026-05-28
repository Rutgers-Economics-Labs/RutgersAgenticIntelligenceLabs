"""
AI agent service for RAIL.

Implements a streaming, tool-using agent backed by any LiteLLM-compatible model.
The agent can autonomously: discover data sources, create configs, run hydration,
query the ontology, execute SQL, and run Python for ML/statistical analysis.

Yields SSE-ready event dicts throughout execution.
"""
import json
import time
from pathlib import Path
from typing import AsyncGenerator

from app.core.config import settings

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI research assistant for RAIL (Rutgers Agentic Intelligence Labs).
RAIL is a platform for building and querying economic knowledge graphs from structured data sources.

You can autonomously help researchers by:
1. Discovering and configuring data sources (Census, FRED, World Bank, uploaded CSVs)
2. Managing configurations and project files via bash (git, ls, cat, etc.)
3. Running data pipelines via the CLI (`python -m engine.pipeline_runner_cli`)
4. Querying the knowledge graph via SQL (DuckDB) or ontology search
5. Running statistical analysis with Python: panel regression, DiD, clustering, time-series

For semantic search across the repository or documents, use `lgrep` in bash.

## Operating with Bash
You have a `run_bash` tool and the `rail` CLI is installed. Use them to:
- **Search Registry**: `rail search "topic"` (replaces registry tools)
- **Query Data**: `rail query sql "SELECT..."` or `rail query entities ClassName`
- **Run Pipelines**: `rail hydrate --pipeline slug`
- **Time Series**: `rail series SERIES_ID`
- **File Management**: `ls`, `cat`, `git` for configs and reports.
- **Semantic Search**: `lgrep` for searching the repository.

The knowledge graph uses these core classes: State, County, Municipality, Individual, Measure.

When a researcher asks a question:
- Think step-by-step about what data is needed
- Use your tools to get, create, or run what's needed
- Explain your findings clearly with concrete numbers

Always show your reasoning. When you write code or SQL, explain the results after seeing them.

## Semantic Search
For semantic search across the project repo or documentation, use `lgrep` via `run_bash`. This is more effective than keyword search for finding relevant code patterns or research context.

## Python Analysis
When using `execute_python`, the `rail` package (from the private `rail-py` library) is available. Use it to interact with the platform's ontology and data sources directly within your scripts.

Never invent CSV paths, table names, or column names — call get_sql_schema or describe_database first, then run_sql or execute_python to verify.
To save maps or HTML reports, write files under OUTPUT_DIR in execute_python; saved files are returned as artifacts you can reference.
Be concise and research-focused."""

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format — LiteLLM normalizes to each provider)
# ---------------------------------------------------------------------------

ALL_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "discover_sources",
            "description": "Search the shared connector template registry for data sources relevant to a topic. Use this to find what data providers are available before creating a new API config.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic or provider to search for"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags e.g. ['economics', 'fred', 'census']"
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Save a research report or analysis artifact to platform storage. Returns a storage URL. Use after producing a complete analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Report title"},
                    "content": {"type": "string", "description": "Markdown report body"},
                    "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command in the project repository. Use this for file management, git operations, running pipeline CLIs, and semantic search with `lgrep`.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                },
                "required": ["command"],
            },
        },
    },
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
            "name": "describe_database",
            "description": (
                "Live introspection of the hydrated DuckDB: every table with row counts and column types. "
                "Flags likely geometry/spatial columns (names or types). Use this before mapping or spatial joins "
                "when you need to confirm what is actually in the database."
            ),
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
                "Also available when installed: np, smf, sm, sklearn, plt (matplotlib), folium, geopandas (gpd). "
                "OUTPUT_DIR is a writable folder — save Folium maps (.html), GeoJSON, CSV, or PNG there; "
                "files are uploaded and returned in the artifacts list. "
                "Any DataFrame variable in scope is returned. Matplotlib figures are captured. "
                "Use for: regression, maps, geospatial summaries, clustering, time-series analysis."
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

# Tools merged into `/project-agent/chat` so dashboard + project flows can query DuckDB the same way.
PROJECT_AGENT_DATA_TOOLS: list[dict] = [
    t for t in ALL_TOOLS
    if t["function"]["name"] in (
        "run_sql",
        "get_sql_schema",
        "describe_database",
        "execute_python",
    )
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_duckdb_path(
    *,
    project_slug: str | None = None,
    project_id: str | None = None,
) -> str | None:
    """Return absolute path to the project's DuckDB file, or None if missing/not hydrated."""
    from app.services import project_artifacts_service

    identifier = project_slug or project_id
    if not identifier:
        return None
    try:
        artifacts = await project_artifacts_service.resolve(identifier)
    except Exception:
        return None
    raw = artifacts.duckdb_path
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    return str(p) if p.is_file() else None


async def _build_context_snapshot(project_slug: str) -> dict:
    from app.services import planner_service
    from app.services import sql_service

    try:
        project = await planner_service.resolve_project_reference(project_slug)
    except Exception:
        project = None
    if not project:
        return {}

    context = {"project": project, "ontology": {}, "data_sources": [], "pipelines": []}

    duck = await _resolve_duckdb_path(project_slug=project_slug)
    if duck:
        context["ontology"]["schema_ddl"] = sql_service.get_schema_ddl(duckdb_path=duck)
        tables = sql_service.list_tables(duckdb_path=duck)
        counts = []
        for t in tables:
            try:
                r = sql_service.run_query(f'SELECT COUNT(*) AS n FROM "{t}"', duckdb_path=duck)
                n = r["rows"][0].get("n") if r.get("rows") else None
                counts.append({"name": t, "instance_count": n})
            except Exception:
                counts.append({"name": t, "instance_count": None})
        context["ontology"]["classes"] = counts

    return context

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

async def _execute_tool(
    name: str,
    args: dict,
    project_slug: str | None = None,
    *,
    project_id: str | None = None,
) -> dict:
    """Execute a named tool and return a JSON-serialisable result dict."""

    if name == "discover_sources":
        from app.services import connector_service
        results = await connector_service.list_templates(
            q=args["query"],
            tags=args.get("tags"),
        )
        return {"results": [{"slug": r["slug"], "name": r["name"], "description": r["description"]} for r in results[:10]]}

    if name == "generate_report":
        from app.services.storage_service import StorageService
        import time, json as _json
        storage = StorageService()
        job_id = f"report_{int(time.time())}"
        filename = f"{args['title'].lower().replace(' ', '_')}.md"
        content = args["content"]

        # Write to temp file and upload
        import tempfile, pathlib
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        storage_key = await storage.upload(job_id, filename, tmp_path)
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        return {"storage_key": storage_key, "title": args["title"], "filename": filename}

    if name == "run_bash":
        import subprocess
        cmd = args["command"]
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return {
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:2000],
                "returncode": result.returncode
            }
        except Exception as e:
            return {"error": f"Failed to run bash: {str(e)}"}

    if name == "search_data_registry":
        from app.services import registry_service
        results = await registry_service.search_registry_entries(
            query_text=args["query"],
            provider=args.get("provider"),
            geography=args.get("geography"),
            limit=min(args.get("limit", 10), 20),
        )
        return {"results": results}

    elif name == "query_ontology":
        from app.services import ontology_service
        class_name = args["class_name"]
        search = args.get("search", "")
        limit = min(args.get("limit", 20), 100)
        result = await ontology_service._run(
            None, ontology_service.list_instances, class_name, 1, limit, search
        )
        # Trim properties for token efficiency
        items = result.get("items", [])
        return {"total": result.get("total", 0), "items": items[:limit]}

    elif name == "run_sql":
        from app.services import sql_service
        from app.services.convex_client import convex

        duck = await _resolve_duckdb_path(project_slug=project_slug, project_id=project_id)
        if not duck:
            return {
                "error": (
                    "No hydrated DuckDB for this project. Link an ontology, run hydration, "
                    "and wait until a DuckDB export exists (activeOntologyDuckdbPath)."
                ),
            }

        # Create a job for the agent's SQL query
        job_result = await convex.mutation("executions:create", {
            "type": "sql",
            "input": args["query"],
            "triggeredBy": "agent",
            "createdAt": int(time.time() * 1000)
        })
        job_id = job_result["jobId"]

        try:
            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "running",
                "startedAt": int(time.time() * 1000)
            })

            import asyncio
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None,
                lambda q=args["query"], d=duck: sql_service.run_query(q, duckdb_path=d),
            )

            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "success",
                "finishedAt": int(time.time() * 1000),
                "result": res
            })
            return res
        except Exception as e:
            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "failed",
                "finishedAt": int(time.time() * 1000),
                "errorMessage": str(e)
            })
            return {"error": str(e)}

    elif name == "get_sql_schema":
        from app.services import sql_service

        duck = await _resolve_duckdb_path(project_slug=project_slug, project_id=project_id)
        if not duck:
            return {"error": "No hydrated DuckDB for this project. Run hydration first."}
        return sql_service.get_schema(duckdb_path=duck)

    elif name == "describe_database":
        from app.services import sql_service

        duck = await _resolve_duckdb_path(project_slug=project_slug, project_id=project_id)
        if not duck:
            return {"error": "No hydrated DuckDB for this project. Run hydration first."}
        schema = sql_service.get_schema(duckdb_path=duck)
        tables_out: list[dict] = []
        for table, cols in schema.items():
            row_count = None
            try:
                r = sql_service.run_query(f'SELECT COUNT(*) AS n FROM "{table}"', duckdb_path=duck)
                if r.get("rows"):
                    row_count = r["rows"][0].get("n")
            except Exception:
                pass
            columns_out = []
            for c in cols:
                typ = (c.get("type") or "").upper()
                cname = (c.get("name") or "").lower()
                geometry_hint = (
                    "GEOM" in typ
                    or "GEOGRAPHY" in typ
                    or "WKB" in typ
                    or "WKT" in typ
                    or any(
                        x in cname
                        for x in (
                            "geom",
                            "geometry",
                            "wkt",
                            "shape",
                            "outline",
                            "the_geom",
                            "latitude",
                            "longitude",
                            "lat",
                            "lon",
                            "lng",
                        )
                    )
                )
                columns_out.append({
                    "name": c["name"],
                    "type": c.get("type"),
                    "geometry_hint": geometry_hint,
                })
            tables_out.append({"name": table, "row_count": row_count, "columns": columns_out})
        return {"tables": tables_out}

    elif name == "execute_python":
        from app.services import subprocess_code_runner
        from app.services.convex_client import convex
        from app.services.execution_manager import execution_manager
        import asyncio

        if not settings.execute_python_enabled:
            return {
                "error": "Python execution is disabled (RAIL_EXECUTE_ENABLED=false).",
            }

        duck = await _resolve_duckdb_path(project_slug=project_slug, project_id=project_id)
        if not duck:
            return {
                "error": (
                    "No hydrated DuckDB for this project. Run hydration first so Python can query "
                    "the same database."
                ),
            }

        # Create a job for the agent's Python code
        job_result = await convex.mutation("executions:create", {
            "type": "code",
            "input": args["code"],
            "triggeredBy": "agent",
            "createdAt": int(time.time() * 1000)
        })
        job_id = job_result["jobId"]

        # Create execution task — upload HTML/GeoJSON/etc. written to OUTPUT_DIR
        task = asyncio.create_task(
            subprocess_code_runner.run_user_code(
                args["code"],
                120,  # Default timeout for agent
                upload_artifacts=True,
                duckdb_path=duck,
                job_id=job_id,
            )
        )

        # Register with manager
        execution_manager.register_job(job_id, task)

        # Wait for completion (the runner handles status updates)
        return await task

    elif name == "get_series_data":
        from app.services import ontology_service
        data = await ontology_service._run(None, ontology_service.get_series_data, args["series_id"])
        return {"series_id": args["series_id"], "points": data}

    elif name == "search_entities":
        from app.services import ontology_service
        types = args.get("types")
        results = await ontology_service._run(
            None, ontology_service.search_entities, args["query"], types
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
    project_slug: str | None = None,
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

    context_snapshot = None
    if project_slug:
        context_snapshot = await _build_context_snapshot(project_slug)

    if context_snapshot:
        yield {"type": "context_snapshot", "data": context_snapshot}

        # Inject into system prompt
        context_block = f"\n\n## Project Context\n```json\n{json.dumps(context_snapshot, indent=2)}\n```\n"
        system_prompt = SYSTEM_PROMPT + context_block
    else:
        system_prompt = SYSTEM_PROMPT

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    new_messages: list[dict] = [{"role": "user", "content": user_message}]

    allowed = None
    if context_snapshot:
        project_data = context_snapshot.get("project", {})
        allowed = project_data.get("agentAllowedActions")  # None = all allowed

    def _filter_tools(tools: list[dict], allowed: list[str] | None) -> list[dict]:
        if allowed is None:
            return tools
        allowed_set = set(allowed)
        return [t for t in tools if t["function"]["name"] in allowed_set]

    filtered_tools = _filter_tools(ALL_TOOLS, allowed)

    # Agentic loop: keep calling until no tool calls remain
    max_turns = 10
    for _turn in range(max_turns):
        assistant_text = ""
        turn_tool_calls: list[dict] = []  # {id, name, args}

        async for event in llm_service.stream_agent(messages, filtered_tools, model=model):
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
                        result = await _execute_tool(tc_event["name"], tc_event["args"], project_slug=project_slug)
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
