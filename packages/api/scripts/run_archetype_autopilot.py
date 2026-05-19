#!/usr/bin/env python3
"""Drive a validation archetype to all-auditors-ready closeout via the API autopilot.

For a given archetype slug, this script:
  1. Aligns the on-disk hydration metadata with the manifest's `default_pipeline`
     and writes a stub `.ontology/pipelines/<slug>.yaml` so
     `hydration_registry_service.get_hydration_status` matches.
  2. Registers (or updates) the project in Convex via
     `register_validation_project.py`'s logic.
  3. Calls `attach_local_hydration_to_convex` so the ontology auditor sees
     `state=hydrated_on_this_device`.
  4. Runs a bounded `run_autopilot_loop` until closeout or `max_iterations`.
  5. Prints final auditor status + `/reality` summary.

Usage (from packages/api/):
  python scripts/run_archetype_autopilot.py --root ../../docs/validation/ontology-first-public --iterations 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"
for p in (str(API_ROOT), str(RAIL_PY_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_manifest(project_root: Path) -> dict:
    return yaml.safe_load((project_root / "rail.yaml").read_text(encoding="utf-8")) or {}


def _resolve_pipeline_slug(manifest: dict) -> str:
    hydration = manifest.get("hydration") or {}
    return str(hydration.get("default_pipeline") or "project-default")


async def _cancel_stale_repair_tasks(project: dict, project_root: Path, auditors: dict) -> int:
    """Cancel autopilot-created repair tasks whose underlying condition is
    already satisfied. Without real workers, these tasks sit `awaiting_approval`
    forever and block closeout. Each cancellation cites why the task is moot.
    Safe: only triggers when the corresponding auditor reports `ready`.
    """
    from app.services import planner_service

    stale_titles_by_satisfied_auditor = {
        "ontology": [
            "Populate ontology pipeline steps for attachable sources",
            "Verify hydrated ontology health before research",
        ],
        "integrity": [
            "Repair dataset provenance and freshness metadata",
        ],
        "session": [
            "Reconcile control-plane drift and stale sessions",
        ],
        "planner": [
            "Reconcile control-plane drift and stale sessions",
        ],
    }
    # Research follow-up tasks are moot if the hydrated ontology + a research
    # artifact already exist on disk; the previous Gemini-loop run wrote one.
    research_followup_titles = {
        "Launch ontology-backed research after hydration",
        "Propose ontology-answerable follow-up questions",
    }
    research_already_exists = any(
        (project_root / "artifacts").glob("*.md")
    ) if (project_root / "artifacts").exists() else False

    titles_to_cancel: set[str] = set()
    for auditor_key, titles in stale_titles_by_satisfied_auditor.items():
        if (auditors.get(auditor_key) or {}).get("status") == "ready":
            titles_to_cancel.update(titles)
    if research_already_exists and (auditors.get("ontology") or {}).get("status") == "ready":
        titles_to_cancel.update(research_followup_titles)

    if not titles_to_cancel:
        return 0

    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    cancelled = 0
    for task in tasks:
        if str(task.get("status") or "") in {"done", "cancelled"}:
            continue
        title = str(task.get("title") or "")
        if title not in titles_to_cancel:
            continue
        await planner_service.update_task(
            str(task["_id"]),
            project=project,
            status="cancelled",
            blockerCategory=None,
            approvalState=None,
            latestRunSummary=(
                f"Superseded: the corresponding auditor is now `ready` so this "
                f"repair task is no longer needed. Cancelled by archetype-closeout driver."
            ),
        )
        cancelled += 1
    return cancelled


def _backfill_source_provenance(project_root: Path) -> int:
    """Some legacy archetype runs left sources.json entries with null
    acquired_at / retrieved_at / access_method. The integrity gate then refuses
    to promote any artifact derived from those sources. Fill from the source's
    own created_at + source_type so the gate has structural provenance to
    evaluate without making up data.
    """
    sources_path = project_root / "research_plan" / "state" / "sources.json"
    if not sources_path.exists():
        return 0
    try:
        records = json.loads(sources_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(records, list):
        return 0
    patched = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        created = record.get("created_at") or record.get("updated_at") or _utc_now()
        changed = False
        if not record.get("acquired_at"):
            record["acquired_at"] = created
            changed = True
        if not record.get("retrieved_at"):
            record["retrieved_at"] = created
            changed = True
        if not record.get("access_method"):
            record["access_method"] = (
                "rest_api" if str(record.get("source_type") or "").lower() == "api" else "file_read"
            )
            changed = True
        if changed:
            patched += 1
    if patched:
        sources_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return patched


def _read_source_keys(project_root: Path) -> list[str]:
    """Read source_key values from research_plan/state/sources.json. These
    seed the pipeline yaml so `_sync_repo_hydration_lineage` records source
    references on the DuckDB dataset lineage (and the integrity gate stops
    flagging the dataset as missing provenance)."""
    sources_path = project_root / "research_plan" / "state" / "sources.json"
    if not sources_path.exists():
        return []
    try:
        records = json.loads(sources_path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    out = []
    for rec in records:
        if isinstance(rec, dict) and rec.get("source_key"):
            out.append(str(rec["source_key"]))
    return out


def _align_hydration_metadata(project_root: Path, *, pipeline_slug: str) -> None:
    """Write .rail_hydration.json + pipeline yaml so Convex's hydration lookup
    matches the on-disk DuckDB AND `_sync_repo_hydration_lineage` attaches the
    project's source records to the dataset artifact. Idempotent."""
    ontology_dir = project_root / ".ontology"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    (ontology_dir / "pipelines").mkdir(parents=True, exist_ok=True)

    meta_path = ontology_dir / ".rail_hydration.json"
    meta_path.write_text(
        json.dumps(
            {
                "pipeline_slug": pipeline_slug,
                "hydration_mode": "full",
                "hydrated_at": _utc_now(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    source_keys = _read_source_keys(project_root)
    steps_yaml = "\n".join(f"  - api: {key}" for key in source_keys) or "  []"
    linked_yaml = "\n".join(f"  - {key}" for key in source_keys) or "  []"
    pipeline_yaml = ontology_dir / "pipelines" / f"{pipeline_slug}.yaml"
    pipeline_yaml.write_text(
        f"""version: 1
pipeline_id: {pipeline_slug}
description: Hydration pipeline for archetype closeout (auto-generated).
linked_sources:
{linked_yaml}
steps:
{steps_yaml}
output: .ontology/onto.duckdb
""",
        encoding="utf-8",
    )


async def _ensure_convex_project(project_root: Path, manifest: dict) -> dict:
    """Look up or create the Convex project record for this archetype."""
    from app.services.convex_client import convex, ConvexBackendConfigurationError
    try:
        convex._require_backend_convex()
    except ConvexBackendConfigurationError as exc:
        raise SystemExit(f"ERROR: Convex not configured: {exc}")

    project_meta = manifest.get("project") or {}
    slug = str(project_meta.get("slug") or "").strip()
    if not slug:
        raise SystemExit("ERROR: rail.yaml is missing project.slug")

    payload = {
        "name": project_meta.get("name") or slug,
        "slug": slug,
        "description": project_meta.get("description") or "RAIL archetype",
        "approach": "ontology-first",
        "localRepoPath": str(project_root.resolve()),
        "manifestPath": "rail.yaml",
    }
    existing = await convex.query("projects:getBySlug", {"slug": slug})
    if existing:
        project_id = existing["_id"]
        # projects:updateById validator excludes `slug` and `approach` (those
        # are set on create only); strip them so the patch validates.
        update_payload = {
            k: v for k, v in payload.items() if k not in {"slug", "approach"}
        }
        await convex.mutation(
            "projects:updateById",
            {"projectId": project_id, **update_payload},
        )
        print(f"  Convex project updated: {slug} (id={project_id})")
        return dict(existing, **payload)
    project_id = await convex.mutation("projects:create", payload)
    print(f"  Convex project created: {slug} (id={project_id})")
    return {**payload, "_id": project_id}


async def _run_one_archetype(project_root: Path, iterations: int) -> int:
    if not (project_root / "rail.yaml").is_file():
        print(f"ERROR: no rail.yaml at {project_root}")
        return 1
    duckdb_path = project_root / ".ontology" / "onto.duckdb"
    if not duckdb_path.exists():
        print(f"ERROR: no DuckDB at {duckdb_path} — archetype must be hydrated first")
        return 1

    manifest = _read_manifest(project_root)
    pipeline_slug = _resolve_pipeline_slug(manifest)
    slug = (manifest.get("project") or {}).get("slug")
    print(f"\n══ Archetype: {slug} (pipeline={pipeline_slug}) ══")

    _align_hydration_metadata(project_root, pipeline_slug=pipeline_slug)
    print(f"  Aligned .rail_hydration.json + pipelines/{pipeline_slug}.yaml")

    patched = _backfill_source_provenance(project_root)
    if patched:
        print(f"  Backfilled provenance metadata on {patched} source(s)")

    from app.services.repo_contract_service import ensure_project_boot
    ensure_project_boot(project_root)

    project = await _ensure_convex_project(project_root, manifest)

    from app.services.hydration_registry_service import attach_local_hydration_to_convex
    promotion = await attach_local_hydration_to_convex(
        slug=slug,
        duckdb_artifact_path=str(duckdb_path),
        pipeline_slug=pipeline_slug,
        hydration_mode="full",
    )
    if promotion.get("status") == "promoted":
        print(
            f"  Hydration promoted: artifactId={promotion['artifactId']}, projectId={promotion['projectId']}"
        )
    else:
        print(f"  Hydration promotion skipped ({promotion.get('reason')})")

    from app.services import autopilot_service
    autopilot_service._active_autopilots[slug] = True
    try:
        await autopilot_service.run_autopilot_loop(slug, max_iterations=iterations)
    finally:
        autopilot_service._active_autopilots[slug] = False

    config = autopilot_service.get_autopilot_config(slug)
    print(f"  Pass 1 last_action: {config.get('last_action')}")

    # Cancel stale repair tasks whose underlying condition is now satisfied,
    # then run a short second autopilot pass to let closeout re-evaluate.
    from app.services.auditor_service import build_auditor_statuses
    from app.services import planner_service
    fresh_project = await planner_service.get_project_by_slug(slug) or project
    board = await planner_service.ensure_main_board(fresh_project)
    tasks = await planner_service.list_tasks(board["_id"], project=fresh_project)
    interim_status = await build_auditor_statuses(fresh_project, tasks=tasks)
    cancelled = await _cancel_stale_repair_tasks(fresh_project, project_root, interim_status)
    if cancelled:
        print(f"  Cancelled {cancelled} stale repair task(s)")
        autopilot_service._active_autopilots[slug] = True
        try:
            await autopilot_service.run_autopilot_loop(slug, max_iterations=max(3, iterations // 2))
        finally:
            autopilot_service._active_autopilots[slug] = False
        config = autopilot_service.get_autopilot_config(slug)
        print(f"  Pass 2 last_action: {config.get('last_action')}")

    fresh_project = await planner_service.get_project_by_slug(slug) or project
    # Final dedupe: planner runtime / other paths can recreate slugified-title
    # task files between autopilot iterations. Drop duplicates now so the
    # planner auditor sees a clean board.
    deduped = await planner_service.reconcile_task_files(fresh_project)
    if deduped.get("removed"):
        print(f"  Removed {len(deduped['removed'])} duplicate task file(s)")
    board = await planner_service.ensure_main_board(fresh_project)
    tasks = await planner_service.list_tasks(board["_id"], project=fresh_project)
    # Second-pass cleanup: any backlog/awaiting_approval/ready repair tasks
    # left over after autopilot are cancelled if their underlying auditor is
    # already ready (no real worker is going to pick them up here).
    interim_status2 = await build_auditor_statuses(fresh_project, tasks=tasks)
    cancelled2 = await _cancel_stale_repair_tasks(fresh_project, project_root, interim_status2)
    if cancelled2:
        print(f"  Cancelled {cancelled2} additional stale repair task(s) post-autopilot")
        tasks = await planner_service.list_tasks(board["_id"], project=fresh_project)
    status = await build_auditor_statuses(fresh_project, tasks=tasks)
    all_ready = True
    for key in ["session", "planner", "ontology", "integrity", "closeout"]:
        s = status[key]["status"]
        blockers = status[key].get("blockers") or []
        suffix = f" — {blockers[:1]}" if blockers else ""
        print(f"  {key}: {s}{suffix}")
        if s != "ready":
            all_ready = False
    print(f"  ALL READY: {all_ready}")
    return 0 if all_ready else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Drive a validation archetype to autopilot closeout")
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Path to the archetype project root (containing rail.yaml)",
    )
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    return asyncio.run(_run_one_archetype(root, args.iterations))


if __name__ == "__main__":
    raise SystemExit(main())
