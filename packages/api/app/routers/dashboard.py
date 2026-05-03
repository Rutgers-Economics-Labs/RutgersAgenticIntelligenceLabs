"""
AI dashboard generation: given a project's research brief + DuckDB schema,
prompt the LLM to produce self-contained HTML panels that query live data.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.convex_client import convex
from app.services import sql_service
from app.services.llm_service import complete

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["dashboard"])

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """You are a data visualization expert generating an interactive stakeholder dashboard.
The dashboard accompanies a policy research paper and will be read by policymakers and the public.

You will produce self-contained HTML panels. Each panel must:
1. Load Chart.js 4 from CDN exactly: https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js
2. Fetch data with:
   fetch('/api/rail-sql', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({query: 'SELECT ...'})
   })
   Response shape: {"columns": ["col1",...], "rows": [[v1,...], ...], "rowCount": N}
3. Render a labeled, readable chart.

Visual rules:
- body background: transparent. Font: Inter, system-ui, sans-serif.
- Primary color: #cc0000. Text: #111111. Muted: #6b6b6b. Border: #d8d8d4.
- Remove Chart.js default padding (use layout.padding: 8).
- Show a "Loading data…" message while fetching.
- If rowCount is 0 show "No data available." in muted gray.
- Do not use external stylesheets besides the Chart.js CDN.

Respond with ONLY a raw JSON array — no markdown fences, no prose before or after:
[
  {
    "id": "snake_case_id",
    "title": "Panel Title",
    "description": "One sentence: what this shows and why it matters.",
    "width": "half",
    "height": 280,
    "html": "<!DOCTYPE html>..."
  }
]

width is "full" (spans both columns) or "half" (one column).
Use "full" for line charts / time-series. Use "half" for bar charts and stat cards.
Generate 5–7 panels that best convey the research findings to a non-technical audience.
Use ONLY tables and columns present in the DuckDB schema below.
Prefer concise SQL — avoid JOINs unless necessary.
"""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/{slug}/dashboard/generate")
async def generate_dashboard(slug: str):
    # 1. Project record
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    # 2. DuckDB schema
    if not sql_service.is_ready():
        raise HTTPException(
            503,
            "DuckDB not ready — run a hydration job first so the database is populated.",
        )
    schema_ddl = sql_service.get_schema_ddl()
    if not schema_ddl.strip():
        raise HTTPException(
            503,
            "DuckDB schema is empty — run hydration to populate the database.",
        )

    # 3. Research brief from disk
    brief_text = _load_brief(project)

    # 4. Call LLM
    user_msg = (
        f"DuckDB Schema:\n{schema_ddl}\n\n"
        f"Research Brief:\n{brief_text[:8000]}\n\n"
        "Generate the dashboard panels now."
    )
    response = await complete(
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=14000,
    )

    raw = (response.choices[0].message.content or "").strip()

    # Strip any accidental markdown fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

    try:
        panels = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Dashboard JSON parse failed: %s\nFirst 600 chars: %s", exc, raw[:600])
        raise HTTPException(500, f"LLM returned malformed JSON: {exc}")

    return {
        "panels": panels,
        "projectName": project.get("name", slug),
        "slug": slug,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_brief(project: dict) -> str:
    local_repo = project.get("localRepoPath")
    if local_repo:
        for candidate in [
            "research_plan/current_plan.md",
            "research_plan/research_brief.md",
            "research_brief.md",
            "README.md",
        ]:
            p = Path(local_repo) / candidate
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
    return (
        f"Project: {project.get('name', 'unknown')}\n"
        f"Description: {project.get('description', '')}"
    )
