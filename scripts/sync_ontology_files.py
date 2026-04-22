#!/usr/bin/env python3
"""
Fetch ontology, pipeline, and data-source configs from Convex for each project
and write them into the project's .ontology/ directory, then commit + push.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

CONVEX_URL  = "https://animated-caterpillar-927.convex.cloud"
CONVEX_AUTH = os.environ["CONVEX_DEPLOY_KEY"]

PROJECTS = [
    {
        "name":              "Synthetic Test",
        "slug":              "synthetic",
        "dir":               Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-synthetic-test"),
        "ontology_slug":     "synthetic",
        "pipeline_slug":     None,
        "api_slugs":         [],
    },
    {
        "name":              "Academic",
        "slug":              "academic",
        "dir":               Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-academic"),
        "ontology_slug":     "academic",
        "pipeline_slug":     "academic_hydration",
        "api_slugs":         [
            "academic_courses", "academic_departments", "academic_faculty",
            "academic_grants", "academic_phd_students", "academic_publications",
            "academic_universities",
        ],
    },
    {
        "name":              "SAD",
        "slug":              "sad",
        "dir":               Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-sad"),
        "ontology_slug":     "core",
        "pipeline_slug":     "nj_hydration",
        "api_slugs":         [
            "fred_housing", "fred_income", "fred_nj_housing", "fred_nj_income",
            "fred_nj_unemployment", "fred_state_gdp", "fred_unemployment",
            "fred_us_cpi", "fred_us_gdp", "municipality_map", "nj_county_geo",
            "sample_individuals", "world_bank_gdp", "world_bank_population",
            "census_municipalities",
        ],
    },
]


def convex_query(path: str, args: dict) -> dict:
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
        raise RuntimeError(f"Query {path} failed: {data}")
    return data["value"]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(path.parents[3])}")


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr.strip()}")
    if result.stdout.strip():
        print(f"    › {result.stdout.strip()}")


def sync_project(p: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {p['name']}  ({p['slug']})")
    print(f"{'='*60}")

    onto_dir     = p["dir"] / ".ontology"
    sources_dir  = onto_dir / "sources"
    pipeline_dir = onto_dir / "pipelines"

    # ── 1. Ontology YAML ──────────────────────────────────────────
    print(f"\n  Fetching ontology: {p['ontology_slug']}")
    onto = convex_query("configs:getOntology", {"slug": p["ontology_slug"]})
    if onto:
        write(onto_dir / "ontology.yaml", onto["content"])
    else:
        print(f"  ⚠ Ontology '{p['ontology_slug']}' not found in Convex")

    # ── 2. Pipeline YAML ─────────────────────────────────────────
    if p["pipeline_slug"]:
        print(f"\n  Fetching pipeline: {p['pipeline_slug']}")
        pipe = convex_query("configs:getPipeline", {"slug": p["pipeline_slug"]})
        if pipe:
            write(pipeline_dir / f"{p['pipeline_slug']}.yaml", pipe["content"])
        else:
            print(f"  ⚠ Pipeline '{p['pipeline_slug']}' not found in Convex")

    # ── 3. Data source / API config YAMLs ────────────────────────
    if p["api_slugs"]:
        print(f"\n  Fetching {len(p['api_slugs'])} data source configs…")
        for slug in p["api_slugs"]:
            api = convex_query("configs:getApi", {"slug": slug})
            if api:
                write(sources_dir / f"{slug}.yaml", api["content"])
            else:
                print(f"  ⚠ API config '{slug}' not found in Convex")

    # ── 4. Commit + push ─────────────────────────────────────────
    print(f"\n  Committing…")
    run(["git", "add", ".ontology/"], cwd=p["dir"])
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=p["dir"]
    )
    if diff.returncode != 0:
        run(
            ["git", "commit", "-m", "feat: add ontology, pipeline, and data source configs"],
            cwd=p["dir"],
        )
        print("  Pushing…")
        run(["git", "push"], cwd=p["dir"])
        print("  ✓ Pushed")
    else:
        print("  Nothing changed, skipping commit.")


if __name__ == "__main__":
    for project in PROJECTS:
        sync_project(project)
    print("\n✓ All projects synced.")
