"""
Research subagent powered by Gemini 2.5 Flash + Google Search grounding.

The planner spawns one subagent per focus area. Each subagent:
  1. Uses Gemini with live Google Search to research a specific topic
  2. Writes structured findings to research/findings/{slug}/findings.md
  3. Returns a summary dict for the planner to include in its response

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
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a focused research agent working on an economic policy research project.
Your job is to thoroughly research ONE specific data source or topic using Google Search.

After researching, write a structured findings document covering:
1. What this data source is and what it contains
2. Exact URLs, API endpoints, or download portals
3. Access requirements (API key, registration, cost, rate limits)
4. Data format (JSON, CSV, XML, etc.) and update frequency
5. Sample fields or schema if available
6. Any known limitations or quirks

Be specific and factual. Include actual URLs you found via search.
Do not hallucinate URLs — only include ones confirmed via search results.
Structure your response with clear markdown headings.
"""


def _make_client() -> genai.Client:
    api_key = settings.google_api_key
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set — needed for Gemini research subagents")
    return genai.Client(api_key=api_key)


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:60].rstrip("-") or "topic"


def _extract_citations(response) -> str:
    lines: list[str] = []
    try:
        for candidate in (response.candidates or []):
            meta = getattr(candidate, "grounding_metadata", None)
            if not meta:
                continue
            for chunk in getattr(meta, "grounding_chunks", []) or []:
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
        client = _make_client()
        query_list = "\n".join(f"- {q}" for q in queries)
        prompt_parts = [
            f"Research topic: **{focus}**\n",
        ]
        if extra_context:
            prompt_parts.append(f"Additional context:\n{extra_context}\n")
        prompt_parts.append(
            f"Please research the following questions:\n{query_list}\n\n"
            "Use Google Search to find accurate information. Write a comprehensive "
            "findings document with specific URLs, API endpoints, and access details."
        )
        prompt = "\n".join(prompt_parts)

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            text = response.text or ""
            citations = _extract_citations(response)
        except Exception as exc:
            log.error("Gemini research agent failed for '%s': %s", focus, exc)
            return {"focus": focus, "error": str(exc), "output_path": None}

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
      - focus: str          — topic name (used as folder name too)
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
