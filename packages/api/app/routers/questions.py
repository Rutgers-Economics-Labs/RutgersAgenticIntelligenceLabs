"""
Natural-language Q&A agent for RAIL.

The agent:
  1. Checks the project schema to understand available data
  2. Determines if the question can be answered
  3. If yes → runs SQL / Python and returns structured results
  4. If no  → calls report_scope_exceeded with what's missing
"""

import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import llm_service
from app.services import planner_service

router = APIRouter(prefix="/questions", tags=["questions"])


SYSTEM_PROMPT = """You are a research data analyst for RAIL. Your job is to answer questions
using the project's knowledge graph data. You are precise, direct, and cite your findings with numbers.

## Workflow — follow this exactly
1. Call get_schema first to understand what tables and columns are available.
2. Search context documents if the question might require background knowledge.
3. Decide: can this question be answered with the available data?
   - YES → write and run SQL or Python to answer it, then summarize clearly.
   - NO  → call report_scope_exceeded describing exactly what data is missing.
4. If running Python, always print key numbers and create charts for trends.

## Output style
- Lead with the direct answer, then show the supporting data.
- Use concrete numbers (not just "higher" — say "23% higher").
- If results are empty or zero, say so clearly rather than making something up.
- For complex analysis use Python; for lookups and aggregations use SQL.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Get available tables and columns. ALWAYS call this first.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_context",
            "description": "Search uploaded research papers, reports, and documents for relevant background knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"},
                    "project_id": {"type": "string", "description": "Project ID for scoped docs"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Execute a SQL query against the DuckDB knowledge graph. Use for aggregations and lookups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "project_id": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": (
                "Run Python for statistical analysis and visualizations. "
                "Available: sql(query)→DataFrame, get_table(name)→DataFrame, pd, np, plt, smf, sklearn."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "project_id": {"type": "string"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_data_registry",
            "description": "Search the catalog of available data sources to find what could answer the question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "provider": {"type": "string", "enum": ["census", "fred", "worldbank", "bls"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_scope_exceeded",
            "description": (
                "Call this when the question CANNOT be answered with current project data. "
                "Be specific about what data is missing and what would need to be added."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Plain-English explanation of why this can't be answered now",
                    },
                    "missing_data": {
                        "type": "string",
                        "description": "Specific data that would be needed (e.g. 'monthly CPI by state 2010-2024')",
                    },
                    "suggested_sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Data source slugs or names from the registry that could provide this data",
                    },
                },
                "required": ["explanation", "missing_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_knowledge_base",
            "description": (
                "Save a piece of text, analysis result, or research note to the project knowledge base "
                "so it can be retrieved in future queries. Use this to persist important findings, "
                "compiled statistics, or synthesized information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "A descriptive title for this document (e.g. 'NJ Unemployment Summary 2024')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text content to save",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Project ID to scope this document. Omit to save globally.",
                    },
                },
                "required": ["name", "content"],
            },
        },
    },
]


async def _resolve_project_record(project_id: str | None) -> dict | None:
    if not project_id:
        return None
    project = None
    try:
        project = await convex.query("projects:get", {"slug": project_id})
    except Exception:
        project = None
    if not project:
        try:
            project = await convex.query("projects:getById", {"projectId": project_id})
        except Exception:
            project = None
    if not project:
        candidate_slugs = [project_id]
        if isinstance(project_id, str) and project_id.startswith("local:"):
            candidate_slugs.append(project_id.removeprefix("local:"))
        for candidate in candidate_slugs:
            try:
                project = await planner_service.get_project_by_slug(candidate)
                if project:
                    break
            except Exception:
                project = None
    return project if isinstance(project, dict) else None


async def _resolve_project_slug(project_id: str | None) -> str | None:
    project = await _resolve_project_record(project_id)
    slug = str((project or {}).get("slug") or "").strip()
    if slug:
        return slug
    if project_id:
        fallback = str(project_id).removeprefix("local:").strip()
        return fallback or None
    return None


async def _execute_tool(name: str, args: dict) -> dict:
    project_id = args.get("project_id")

    if name == "get_schema":
        from app.services import sql_service
        try:
            schema = sql_service.get_schema()
            if project_id:
                from app.services import project_artifacts_service

                artifacts = await project_artifacts_service.resolve(project_id)
                sql_service.set_path(artifacts.duckdb_path)
                schema = sql_service.get_schema()
            return schema
        except Exception as e:
            return {"error": str(e), "tables": []}

    if name == "search_context":
        docs = await convex.query("context:list", {"projectId": project_id} if project_id else {})
        if not docs:
            return {"results": [], "message": "No context documents uploaded yet"}
        query = args.get("query", "").lower()
        results = []
        for doc in docs:
            content = doc.get("content", "")
            if query and query not in content.lower() and query not in doc.get("name", "").lower():
                continue
            # Return a snippet around the first match
            idx = content.lower().find(query) if query else 0
            start = max(0, idx - 100)
            snippet = content[start: start + 600].strip()
            results.append({"name": doc["name"], "type": doc["type"], "snippet": snippet})
        return {"results": results[:5]}

    if name == "run_sql":
        from app.services import sql_service, project_artifacts_service
        if project_id:
            try:
                artifacts = await project_artifacts_service.resolve(project_id)
                sql_service.set_path(artifacts.duckdb_path)
            except Exception:
                pass
        try:
            return sql_service.run_query(args["query"])
        except Exception as e:
            return {"error": str(e)}

    if name == "execute_python":
        from app.services import subprocess_code_runner
        from app.core.config import settings
        if not settings.execute_python_enabled:
            return {"error": "Python execution is disabled"}
        if project_id:
            from app.services import sql_service, project_artifacts_service
            try:
                artifacts = await project_artifacts_service.resolve(project_id)
                sql_service.set_path(artifacts.duckdb_path)
                schema = sql_service.get_schema()
            except Exception:
                pass
        try:
            return await subprocess_code_runner.run_user_code(args["code"], timeout=120)
        except Exception as e:
            return {"error": str(e)}

    if name == "search_data_registry":
        from app.services import registry_service
        results = await registry_service.search_registry_entries(
            query_text=args["query"],
            provider=args.get("provider"),
            limit=8,
        )
        return {"results": results}

    if name == "report_scope_exceeded":
        # Just return the structured data — frontend handles this specially
        return {
            "__scope_exceeded__": True,
            "explanation": args.get("explanation", ""),
            "missing_data": args.get("missing_data", ""),
            "suggested_sources": args.get("suggested_sources", []),
        }

    if name == "save_to_knowledge_base":
        payload = {
            "name": args["name"],
            "type": "text",
            "content": args["content"],
        }
        pid = args.get("project_id") or project_id
        project_slug = await _resolve_project_slug(pid)
        if project_slug:
            payload["projectSlug"] = project_slug
        try:
            doc_id = await convex.mutation("context:create", payload)
            return {"saved": True, "id": doc_id, "name": args["name"]}
        except Exception as e:
            return {"saved": False, "error": str(e)}

    return {"error": f"Unknown tool: {name}"}


async def _run_question(
    question: str,
    project_id: str | None,
    model: str | None,
) -> AsyncGenerator[dict, None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if project_id:
        messages.append({
            "role": "user",
            "content": f"[Context: project_id={project_id}]\n\n{question}",
        })
    else:
        messages.append({"role": "user", "content": question})

    for _turn in range(12):
        turn_tool_calls: list[dict] = []

        async for event in llm_service.stream_agent(messages, TOOLS, model=model):
            if event["type"] == "text_delta":
                yield event
            elif event["type"] == "tool_call":
                turn_tool_calls.append(event)
                yield event
            elif event["type"] == "_turn_end":
                raw_tool_calls = event.get("raw_tool_calls", [])
                assistant_text = event.get("text", "")
                assistant_msg: dict = {"role": "assistant", "content": assistant_text or None}
                if raw_tool_calls:
                    assistant_msg["tool_calls"] = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                        for tc in raw_tool_calls
                    ]
                messages.append(assistant_msg)

                if not event["has_tool_calls"]:
                    yield {"type": "done"}
                    return

                for tc_event in turn_tool_calls:
                    result = await _execute_tool(tc_event["name"], tc_event["args"])
                    yield {"type": "tool_result", "id": tc_event["id"],
                           "name": tc_event["name"], "result": result}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_event["id"],
                        "content": json.dumps(result, default=str),
                    })

    yield {"type": "done"}


class AskRequest(BaseModel):
    question: str
    project_id: str | None = None
    model: str | None = None


@router.post("/ask")
async def ask_question(req: AskRequest):
    async def event_stream():
        try:
            async for event in _run_question(req.question, req.project_id, req.model):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
