"""
Research subagent powered by Gemini + Google Search grounding.

The planner spawns one subagent per focus area. Each subagent:
  1. Uses Gemini with Google Search to research a specific topic
  2. Runs multiple agentic turns (search → read → refine → write)
  3. Writes structured findings to research/findings/{slug}/findings.md
  4. Returns a summary dict for the planner to include in its response

Usage (from planner_runtime):
    results = await run_research_agents(project, agents=[
        {"focus": "PJM Data Miner 2", "queries": ["PJM data miner 2 API docs", ...]},
        {"focus": "FERC Form 1",       "queries": ["FERC Form 1 download portal", ...]},
    ])
"""
from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from pathlib import Path
from typing import Any

import google.generativeai as genai
import google.ai.generativelanguage as glm

from app.core.config import settings

log = logging.getLogger(__name__)

_FINDINGS_SCHEMA = """\
# {focus} — Research Findings

## Summary
{summary}

## Data Sources Found

{sources}

## Access & Authentication
{access}

## Data Formats
{formats}

## Notes
{notes}

## Search Sources
{citations}
"""

_SYSTEM_PROMPT = """\
You are a focused research agent working on an economic research project.
Your job is to thoroughly research ONE specific data source or topic.
Use Google Search to find accurate, up-to-date information.

After researching, write a structured findings document covering:
1. What this data source is and what it contains
2. Exact URLs, API endpoints, or download portals
3. Access requirements (API key, registration, cost, rate limits)
4. Data format (JSON, CSV, XML, etc.) and update frequency
5. Sample fields or schema if available
6. Any known limitations or quirks

Be specific and factual. Include actual URLs. If you find conflicting info, note it.
Do not hallucinate URLs — only include ones you confirmed via search.
"""


def _make_model() -> genai.GenerativeModel:
    api_key = settings.google_api_key
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set — needed for Gemini research subagents")
    genai.configure(api_key=api_key)

    google_search_tool = glm.Tool(
        google_search_retrieval=glm.GoogleSearchRetrieval(
            dynamic_retrieval_config=glm.DynamicRetrievalConfig(
                mode=glm.DynamicRetrievalConfig.Mode.MODE_DYNAMIC,
                dynamic_threshold=0.3,
            )
        )
    )
    return genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        tools=[google_search_tool],
        system_instruction=_SYSTEM_PROMPT,
    )


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].rstrip("-") or "topic"


def _extract_citations(response) -> str:
    """Pull grounding source URLs from the Gemini response metadata."""
    lines: list[str] = []
    try:
        for candidate in response.candidates:
            meta = getattr(candidate, "grounding_metadata", None)
            if not meta:
                continue
            for chunk in getattr(meta, "grounding_chunks", []):
                web = getattr(chunk, "web", None)
                if web:
                    uri = getattr(web, "uri", "")
                    title = getattr(web, "title", "")
                    if uri:
                        lines.append(f"- [{title or uri}]({uri})")
    except Exception:
        pass
    return "\n".join(lines) if lines else "No grounding sources recorded."


async def _run_single_agent(
    *,
    focus: str,
    queries: list[str],
    output_dir: Path,
    extra_context: str = "",
) -> dict[str, Any]:
    """Run one Gemini research subagent synchronously in a thread pool."""

    def _sync_run() -> dict[str, Any]:
        model = _make_model()
        chat = model.start_chat()

        query_list = "\n".join(f"- {q}" for q in queries)
        prompt = textwrap.dedent(f"""
            Research topic: **{focus}**

            {("Additional context:\n" + extra_context + "\n") if extra_context else ""}
            Please research the following questions:
            {query_list}

            Use Google Search to find accurate information. After gathering information,
            write a comprehensive findings document following the structured format in your instructions.
            Include specific URLs, API endpoints, and access details.
        """).strip()

        try:
            response = chat.send_message(prompt)
            text = response.text or ""
            citations = _extract_citations(response)
        except Exception as exc:
            log.error("Gemini research agent failed for '%s': %s", focus, exc)
            return {"focus": focus, "error": str(exc), "output_path": None}

        # Write findings to disk
        slug = _slug(focus)
        findings_dir = output_dir / slug
        findings_dir.mkdir(parents=True, exist_ok=True)
        findings_path = findings_dir / "findings.md"
        findings_path.write_text(
            f"# {focus} — Research Findings\n\n"
            f"{text}\n\n"
            f"---\n## Search Sources\n{citations}\n",
            encoding="utf-8",
        )

        # Also save raw response for debugging
        (findings_dir / "raw_response.txt").write_text(text, encoding="utf-8")

        summary = text[:400].replace("\n", " ").strip()
        return {
            "focus": focus,
            "output_path": str(findings_path.relative_to(output_dir.parent)),
            "summary": summary,
            "citations_count": citations.count("- ["),
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_run)


async def run_research_agents(
    project: dict[str, Any],
    agents: list[dict[str, Any]],
    *,
    output_subdir: str = "research/findings",
    extra_context: str = "",
) -> list[dict[str, Any]]:
    """
    Run multiple research subagents in parallel.

    Each item in `agents` should have:
      - focus: str   — topic name (used as folder name too)
      - queries: list[str]  — specific questions to research

    Returns list of result dicts with focus, output_path, summary, error.
    """
    from app.services import planner_service

    root = planner_service.project_root_from_record(project)
    if root is None:
        return [{"error": "Project has no localRepoPath"}]

    output_dir = root / output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = [
        _run_single_agent(
            focus=agent["focus"],
            queries=agent.get("queries", [agent["focus"]]),
            output_dir=output_dir,
            extra_context=extra_context,
        )
        for agent in agents
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"focus": agents[i]["focus"], "error": str(r)})
        else:
            out.append(r)

    return out
