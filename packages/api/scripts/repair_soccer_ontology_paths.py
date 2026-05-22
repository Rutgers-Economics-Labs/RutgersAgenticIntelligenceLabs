#!/usr/bin/env python3
"""Repair Convex activeOntologyDbPath for the European Soccer project.

Promotion previously stored ontology.yaml in activeOntologyDbPath; this script
points it at the real SQLite quadstore (onto.db).

Run from packages/api/:
  uv run python scripts/repair_soccer_ontology_paths.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).parents[1]
REPO_ROOT = Path(__file__).parents[3]

for p in (str(API_ROOT),):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.convex_client import convex  # noqa: E402

PROJECT_ID = "js7fsbgzc2ygjfw4x8e4rqy5rs86v3y1"
PROJECT_SLUG = "european-soccer-competitive-ecosystem-analysis"
ONTO_DB = (
    REPO_ROOT
    / "generated_projects"
    / PROJECT_SLUG
    / ".ontology"
    / "onto.db"
).resolve()


async def main() -> None:
    if not ONTO_DB.exists():
        raise SystemExit(f"Missing quadstore: {ONTO_DB}")

    project = await convex.query("projects:getById", {"projectId": PROJECT_ID})
    if not project:
        raise SystemExit(f"Project not found in Convex: {PROJECT_ID}")

    patch: dict[str, object] = {
        "projectId": PROJECT_ID,
        "activeOntologyDbPath": str(ONTO_DB),
    }
    duckdb_path = project.get("activeOntologyDuckdbPath")
    if duckdb_path:
        patch["activeOntologyDuckdbPath"] = duckdb_path

    before = project.get("activeOntologyDbPath")
    await convex.mutation("projects:updateById", patch)
    print(f"activeOntologyDbPath: {before!r} -> {ONTO_DB}")


if __name__ == "__main__":
    asyncio.run(main())
