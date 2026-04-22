#!/usr/bin/env python3
"""
Fetch all remaining Convex configs (connectors, ontology templates, unlinked
ontologies/pipelines/sources) and write them into the appropriate repos,
then commit and push.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

CONVEX_URL  = "https://animated-caterpillar-927.convex.cloud"
CONVEX_AUTH = os.environ["CONVEX_DEPLOY_KEY"]

PROJECTS_DIR = Path("/Users/akashdubey/Documents/CodingProjects/RAIL")

REPOS = {
    "sad":     PROJECTS_DIR / "RAIL-sad",
    "starter": PROJECTS_DIR / "RAIL-Census-Ontology-Starter",
}


# ── Convex helpers ────────────────────────────────────────────────────────────

def convex_query(path: str, args: dict) -> list | dict | None:
    body = json.dumps({"path": path, "args": args}).encode()
    req = urllib.request.Request(
        f"{CONVEX_URL}/api/query",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Convex {CONVEX_AUTH}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "success":
        raise RuntimeError(f"Query {path} failed: {data.get('errorMessage', data)}")
    return data["value"]


# ── File helpers ──────────────────────────────────────────────────────────────

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote  {path.relative_to(PROJECTS_DIR)}")


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr.strip()}")
    if result.stdout.strip():
        print(f"    › {result.stdout.strip()}")


def commit_and_push(repo: Path, message: str) -> None:
    run(["git", "add", "."], cwd=repo)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if diff.returncode != 0:
        run(["git", "commit", "-m", message], cwd=repo)
        run(["git", "push"], cwd=repo)
        print(f"  ✓ pushed  {repo.name}")
    else:
        print(f"  — nothing new in {repo.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:

    # ── 1. RAIL-sad: NJ-adjacent unlinked configs ─────────────────────────────
    print("\n" + "="*60)
    print("  RAIL-sad — NJ pipeline + census sources")
    print("="*60)

    sad = REPOS["sad"]

    # nj_gis_hydration pipeline
    pipe = convex_query("configs:getPipeline", {"slug": "nj_gis_hydration"})
    if pipe:
        write(sad / ".ontology/pipelines/nj_gis_hydration.yaml", pipe["content"])

    # census_counties + census_states API configs
    for slug in ("census_counties", "census_states"):
        api = convex_query("configs:getApi", {"slug": slug})
        if api:
            write(sad / f".ontology/sources/{slug}.yaml", api["content"])

    commit_and_push(sad, "feat: add NJ GIS pipeline and census sources")

    # ── 2. RAIL-Census-Ontology-Starter: shared library ───────────────────────
    print("\n" + "="*60)
    print("  RAIL-Census-Ontology-Starter — shared library")
    print("="*60)

    starter = REPOS["starter"]

    # Connectors
    print("\n  [connectors]")
    connectors = convex_query("connectors:list", {})
    for c in (connectors or []):
        write(starter / f".ontology/connectors/{c['slug']}.yaml", c["content"])

    # Ontology templates
    print("\n  [ontology templates]")
    templates = convex_query("ontologyTemplates:list", {})
    for t in (templates or []):
        key = t.get("slug") or t.get("name", "unknown").lower().replace(" ", "-")
        write(starter / f".ontology/templates/{key}.yaml", t["content"])

    # Unlinked ontologies
    print("\n  [unlinked ontologies]")
    for slug in ("us_macroeconomic", "world_economic"):
        onto = convex_query("configs:getOntology", {"slug": slug})
        if onto:
            write(starter / f".ontology/ontologies/{slug}.yaml", onto["content"])

    # Unlinked pipelines
    print("\n  [unlinked pipelines]")
    for slug in ("us_national_indicators", "us_state_economics", "world_gdp"):
        pipe = convex_query("configs:getPipeline", {"slug": slug})
        if pipe:
            write(starter / f".ontology/pipelines/{slug}.yaml", pipe["content"])

    # Unlinked API configs (not in any project)
    # census_counties + census_states are already in sad; also write them here as canonical copies
    print("\n  [shared API sources]")
    all_apis = convex_query("configs:listApis", {})
    project_api_slugs = {
        "academic_courses", "academic_departments", "academic_faculty", "academic_grants",
        "academic_phd_students", "academic_publications", "academic_universities",
        "fred_housing", "fred_income", "fred_nj_housing", "fred_nj_income",
        "fred_nj_unemployment", "fred_state_gdp", "fred_unemployment", "fred_us_cpi",
        "fred_us_gdp", "municipality_map", "nj_county_geo", "sample_individuals",
        "world_bank_gdp", "world_bank_population", "census_municipalities",
    }
    for api in (all_apis or []):
        if api["slug"] not in project_api_slugs:
            write(starter / f".ontology/sources/{api['slug']}.yaml", api["content"])

    commit_and_push(starter, "feat: add connectors, ontology templates, and shared configs library")

    print("\n✓ All legacy configs synced.")


if __name__ == "__main__":
    main()
