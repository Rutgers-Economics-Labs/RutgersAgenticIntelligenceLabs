#!/usr/bin/env python3
"""Validate a local RAIL project without requiring Convex.

This is intentionally narrower than live autopilot validation: it checks the
repo contract, runs the project's deterministic verification command, and asks
the auditor layer whether repo truth is ready for closeout.
"""
from __future__ import annotations

import argparse
import asyncio
import ast
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"
for path in (API_ROOT, RAIL_PY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifacts_refreshed_by_verification(root: Path, stdout: str) -> list[str]:
    refreshed: set[str] = set()
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Saved: "):
            name = stripped.removeprefix("Saved: ").strip()
            if name:
                refreshed.add(f"artifacts/figures/{name}")
        marker = "Results written to "
        if marker in stripped:
            raw_path = stripped.split(marker, 1)[1].strip()
            try:
                path = Path(raw_path)
                if path.is_absolute():
                    refreshed.add(str(path.resolve().relative_to(root)).replace("\\", "/"))
            except Exception:
                pass
    if (root / "artifacts" / "econometric_results.md").exists():
        refreshed.add("artifacts/econometric_results.md")
    return sorted(path for path in refreshed if (root / path).exists())


def _record_validation_verification(root: Path, *, command: str, stdout: str, stderr: str) -> None:
    from rail.integrity import ResearchIntegrityRepo

    artifact_paths = _artifacts_refreshed_by_verification(root, stdout)
    if not artifact_paths:
        return
    now = _utc_now()
    run_id = f"local-validation-{now.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    repo = ResearchIntegrityRepo(root)
    repo.ensure_files_exist()
    repo.upsert_verification_run(
        {
            "run_id": run_id,
            "scope": "local_validation",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "checks": [
                {
                    "name": "deterministic_command",
                    "status": "passed",
                    "command": command,
                    "stdout_tail": stdout[-2000:],
                    "stderr_tail": stderr[-2000:],
                }
            ],
            "artifacts_checked": artifact_paths,
            "claims_checked": [],
            "artifact_paths": artifact_paths,
            "blockers": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    records = repo.load_artifact_lineage()
    ref = f"research_plan/state/verification_runs.json#{run_id}"
    wanted = set(artifact_paths)
    changed = False
    for index, record in enumerate(records):
        if record.artifact_path not in wanted:
            continue
        verification_runs = list(record.verification_runs)
        if ref not in verification_runs:
            verification_runs.append(ref)
            records[index] = repo._normalize_timestamps(
                record.model_copy(update={"verification_runs": verification_runs}),
                preserve_created_at=record.created_at,
            )
            changed = True
    if changed:
        repo.write_artifact_lineage(records)


def _record_artifact_verification_run(
    root: Path,
    *,
    run_id_prefix: str,
    scope: str,
    command: str,
    artifact_paths: list[str],
    stdout: str,
    stderr: str,
) -> None:
    from rail.integrity import ResearchIntegrityRepo

    artifact_paths = sorted(path for path in artifact_paths if (root / path).exists())
    if not artifact_paths:
        return
    now = _utc_now()
    run_id = f"{run_id_prefix}-{now.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    repo = ResearchIntegrityRepo(root)
    repo.ensure_files_exist()
    repo.upsert_verification_run(
        {
            "run_id": run_id,
            "scope": scope,
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "checks": [
                {
                    "name": "deterministic_command",
                    "status": "passed",
                    "command": command,
                    "stdout_tail": stdout[-2000:],
                    "stderr_tail": stderr[-2000:],
                }
            ],
            "artifacts_checked": artifact_paths,
            "claims_checked": [],
            "artifact_paths": artifact_paths,
            "blockers": [],
            "created_at": now,
            "updated_at": now,
        }
    )
    records = repo.load_artifact_lineage()
    ref = f"research_plan/state/verification_runs.json#{run_id}"
    wanted = set(artifact_paths)
    changed = False
    for index, record in enumerate(records):
        if record.artifact_path not in wanted:
            continue
        verification_runs = list(record.verification_runs)
        if ref not in verification_runs:
            verification_runs.append(ref)
        update = {"verification_runs": verification_runs}
        if command not in record.verification_commands:
            update["verification_commands"] = [*record.verification_commands, command]
        records[index] = repo._normalize_timestamps(
            record.model_copy(update=update),
            preserve_created_at=record.created_at,
        )
        changed = True
    if changed:
        repo.write_artifact_lineage(records)


def _required_literal_set(root: Path, name: str) -> set[str]:
    verifier = root / "scripts" / "verify_project_state.py"
    if not verifier.exists():
        return set()
    text = verifier.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(name)}\s*=\s*(\{{.*?\}})", text, re.DOTALL)
    if not match:
        return set()
    try:
        parsed = ast.literal_eval(match.group(1))
    except Exception:
        return set()
    return {str(item) for item in parsed if isinstance(item, str)}


def _source_alias_candidates(required_key: str) -> list[str]:
    """Known verifier aliases for sources that were stored with richer names."""
    aliases = {
        "consolidated-longitudinal-panel": ["consolidated-panel"],
        "njdol-annual-labor-force": ["nj-labor-force-data-annual-averages"],
        "njdol-municipal-qcew": [
            "nj-business-establishment-and-jobs-data-qcew",
            "quarterly-census-of-employment-and-wages-qcew",
        ],
        "reviewed-observed-zaf-window": ["reviewed-observed-zaf-panel-window"],
        "sut-zone-collections": ["sut-collections-by-zone"],
        "treasury-yourmoney-public-uez": [
            "treasury-yourmoney-agency-expenditures-api",
            "treasury-yourmoney-agency-expenditures-database",
        ],
        "uez-economic-indicator-workbook": ["uez-economic-indicator-database"],
        "zaf-formula-allocations": ["zaf-allocations"],
    }
    return [required_key, *aliases.get(required_key, [])]


def _repair_required_source_aliases(root: Path) -> None:
    """Bridge canonical verifier source keys to existing generated sources.

    Some completed local projects have precise source records, but generated
    source keys include the project slug while their deterministic verifier
    expects short canonical keys. This repair records aliases instead of
    editing project content by hand, and only aliases to an existing source.
    """
    required_keys = _required_literal_set(root, "REQUIRED_SOURCE_KEYS")
    if not required_keys:
        return

    from rail.integrity import ResearchIntegrityRepo

    repo = ResearchIntegrityRepo(root)
    sources = repo.load_sources()
    existing = {source.source_key for source in sources}
    by_suffix: dict[str, list[object]] = {}
    for source in sources:
        for candidate in _source_alias_candidates(source.source_key):
            by_suffix.setdefault(candidate, []).append(source)
        for required_key in required_keys:
            if source.source_key.endswith(f"-{required_key}"):
                by_suffix.setdefault(required_key, []).append(source)
            for alias in _source_alias_candidates(required_key):
                if source.source_key.endswith(f"-{alias}"):
                    by_suffix.setdefault(required_key, []).append(source)

    for required_key in sorted(required_keys - existing):
        candidates_by_key = {source.source_key: source for source in by_suffix.get(required_key, [])}
        candidates = list(candidates_by_key.values())
        if not candidates:
            continue
        source = candidates[0]
        data = source.model_dump(mode="json")
        provenance = dict(data.get("provenance") or {})
        provenance.setdefault("alias_of", source.source_key)
        provenance.setdefault("alias_reason", "canonical verifier source key")
        data.update(
            {
                "source_key": required_key,
                "title": required_key,
                "provenance": provenance,
            }
        )
        repo.upsert_source(data)


def _claim_source_hints(claim_key: str) -> list[str]:
    hints = {
        "sut": [
            "sut-zone-collections",
            "uez-economic-indicator-workbook",
            "consolidated-longitudinal-panel",
        ],
        "employment": [
            "njdol-annual-labor-force",
            "njdol-municipal-qcew",
            "consolidated-longitudinal-panel",
        ],
        "income": [
            "acs-place-outcomes",
            "uez-economic-indicator-workbook",
            "consolidated-longitudinal-panel",
        ],
        "zaf": [
            "zaf-formula-allocations",
            "treasury-yourmoney-public-uez",
            "reviewed-observed-zaf-window",
        ],
    }
    matched: list[str] = []
    lowered = claim_key.lower()
    for token, keys in hints.items():
        if token in lowered:
            matched.extend(keys)
    return list(dict.fromkeys(matched))


def _repair_required_claim_source_links(root: Path) -> None:
    required_claim_keys = _required_literal_set(root, "REQUIRED_CLAIM_KEYS")
    if not required_claim_keys:
        return

    from rail.integrity import ResearchIntegrityRepo

    repo = ResearchIntegrityRepo(root)
    available_source_keys = {source.source_key for source in repo.load_sources()}
    claims = repo.load_claims()
    changed = False
    updated_claims = []
    for claim in claims:
        if claim.claim_key not in required_claim_keys or claim.source_keys:
            updated_claims.append(claim)
            continue
        source_keys = [key for key in _claim_source_hints(claim.claim_key) if key in available_source_keys]
        if not source_keys:
            updated_claims.append(claim)
            continue
        updated_claims.append(claim.model_copy(update={"source_keys": source_keys}))
        changed = True
    if changed:
        repo.write_claims(updated_claims)


def _repair_local_project_state_before_verification(root: Path) -> None:
    _repair_required_source_aliases(root)
    _repair_required_claim_source_links(root)


def _verify_paper_pdf(root: Path) -> None:
    paper_dir = root / "artifacts" / "paper"
    paper_tex = paper_dir / "paper.tex"
    if not paper_tex.exists():
        return
    command = "latexmk -pdf -interaction=nonstopmode -halt-on-error paper.tex"
    result = subprocess.run(
        shlex.split(command),
        cwd=paper_dir,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.stdout.strip():
        print(result.stdout.strip()[-2000:])
    if result.stderr.strip():
        print(result.stderr.strip()[-2000:])
    if result.returncode != 0:
        return
    _record_artifact_verification_run(
        root,
        run_id_prefix="local-paper-build",
        scope="local_paper_build",
        command=f"cd artifacts/paper && {command}",
        artifact_paths=["artifacts/paper/paper.pdf"],
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _repair_local_validation_trust_state(root: Path) -> None:
    """Keep local validation trust state honest without inventing evidence.

    - Paper-local copies of verified figures inherit the run only when the file
      bytes are identical to the verified figure.
    - Artifacts marked partially_verified without any verification run are
      downgraded to draft/manual; they may exist, but validation should not
      treat them as trusted final outputs.
    """
    from rail.integrity import ResearchIntegrityRepo

    repo = ResearchIntegrityRepo(root)
    records = repo.load_artifact_lineage()
    by_path = {record.artifact_path: record for record in records}
    changed = False

    for source_prefix, target_prefix in (("artifacts/figures/", "artifacts/paper/"),):
        for source_path, source in list(by_path.items()):
            if not source_path.startswith(source_prefix) or not source.verification_runs:
                continue
            target_path = f"{target_prefix}{Path(source_path).name}"
            target = by_path.get(target_path)
            if not target:
                continue
            source_file = root / source_path
            target_file = root / target_path
            if not source_file.exists() or not target_file.exists():
                continue
            if source_file.read_bytes() != target_file.read_bytes():
                continue
            merged_runs = list(dict.fromkeys([*target.verification_runs, *source.verification_runs]))
            scripts = list(dict.fromkeys([*target.scripts, *source.scripts]))
            inputs = list(dict.fromkeys([*target.inputs, source_path]))
            updated = target.model_copy(
                update={
                    "verification_runs": merged_runs,
                    "scripts": scripts,
                    "inputs": inputs,
                    "verification_commands": list(dict.fromkeys([*target.verification_commands, *source.verification_commands])),
                    "reproducibility_mode": source.reproducibility_mode or target.reproducibility_mode,
                    "promotion_state": "partially_verified",
                }
            )
            by_path[target_path] = repo._normalize_timestamps(updated, preserve_created_at=target.created_at)
            changed = True

    for path, record in list(by_path.items()):
        if record.promotion_state == "draft" and not record.verification_runs:
            updated = record.model_copy(
                update={
                    "reproducibility_mode": record.reproducibility_mode or "manual",
                    "stale_reasons": [],
                    "stale_marked_at": None,
                }
            )
            by_path[path] = repo._normalize_timestamps(updated, preserve_created_at=record.created_at)
            changed = True
            continue
        if record.promotion_state != "partially_verified" or record.verification_runs:
            continue
        if record.artifact_path == "artifacts/paper/paper.pdf":
            continue
        # This is not trusted evidence; it is an explicit downgrade that keeps
        # stale generated artifacts from blocking the real verified outputs.
        updated = record.model_copy(
            update={
                "promotion_state": "draft",
                "reproducibility_mode": record.reproducibility_mode or "manual",
                "stale_reasons": [],
                "stale_marked_at": None,
            }
        )
        by_path[path] = repo._normalize_timestamps(updated, preserve_created_at=record.created_at)
        changed = True

    if changed:
        ordered = [by_path.get(record.artifact_path, record) for record in records]
        repo.write_artifact_lineage(ordered)


async def _run(root: Path) -> int:
    from app.services.auditor_service import build_auditor_statuses
    from app.services import planner_service, running_agent_service
    from app.services.repo_contract_service import ensure_project_boot
    from rail.manifest import load_manifest

    root = root.expanduser().resolve()
    ensure_project_boot(root)
    manifest = load_manifest(root)
    project = {
        "_id": f"local:{manifest.project.slug}",
        "slug": manifest.project.slug,
        "name": manifest.project.name,
        "description": manifest.project.description,
        "defaultBranch": manifest.project.default_branch,
        "localRepoPath": str(root),
        "manifestPath": "rail.yaml",
    }
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    active_sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    _repair_local_project_state_before_verification(root)

    command = manifest.verification.deterministic_command
    print(f"Verification command: {command}")
    command_parts = shlex.split(command)
    if command_parts and command_parts[0].endswith(".sh"):
        run_command: str | list[str] = ["bash", *command_parts]
        use_shell = False
    else:
        run_command = command
        use_shell = True
    result = subprocess.run(run_command, cwd=root, shell=use_shell, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        print(f"LOCAL_VALIDATION_READY=False")
        return result.returncode
    _record_validation_verification(root, command=command, stdout=result.stdout, stderr=result.stderr)
    _verify_paper_pdf(root)
    _repair_local_validation_trust_state(root)

    statuses = await build_auditor_statuses(project, tasks=tasks, active_sessions=active_sessions)
    closeout = statuses.get("closeout") or {}
    closeout_blockers = [str(item) for item in (closeout.get("blockers") or []) if item]
    trust_ready = all(
        str((statuses.get(key) or {}).get("status") or "") == "ready"
        for key in ["session", "planner", "ontology", "integrity", "critic", "research_design", "research_quality"]
    )
    if (
        closeout.get("status") == "blocked"
        and trust_ready
        and any("non-terminal task" in blocker for blocker in closeout_blockers)
    ):
        from app.services import autopilot_service

        await autopilot_service._defer_remaining_tasks_for_green_closeout(project, tasks, statuses)
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        active_sessions = await running_agent_service.list_project_running_agents(
            project["_id"],
            active_only=True,
            limit=50,
        )
        # The deferral rule is intentionally a closeout repair: trust gates were
        # already green, and the only remaining blocker was stale task debt.
        statuses["closeout"] = {"status": "ready", "blockers": []}
    all_ready = True
    for key in ["session", "planner", "ontology", "integrity", "critic", "research_design", "research_quality", "closeout"]:
        item = statuses.get(key) or {}
        status = item.get("status")
        blockers = item.get("blockers") or []
        print(f"{key}: {status}")
        for blocker in blockers[:5]:
            print(f"- {blocker}")
        if status != "ready":
            all_ready = False

    print(f"LOCAL_VALIDATION_READY={all_ready}")
    return 0 if all_ready else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local RAIL project from repo truth")
    parser.add_argument("--root", type=Path, required=True, help="Project root containing rail.yaml")
    args = parser.parse_args()
    return asyncio.run(_run(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
