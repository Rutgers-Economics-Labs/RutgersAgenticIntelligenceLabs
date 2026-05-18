from __future__ import annotations

import asyncio
import logging
import time
import json
from pathlib import Path
from typing import Any

from app.services import planner_runtime, planner_service, running_agent_service
from app.runners import session_lifecycle
from app.services.audit_service import audit_gate_status
from app.services.convex_client import convex
from app.services.decision_service import list_decision_events, mark_decision_event, raise_decision_event
from app.services.hydration_registry_service import get_hydration_status
from app.services.integrity_service import evaluate_integrity_gate, summarize_agent_workflow_health
from app.services.auditor_service import build_auditor_statuses
from app.services.reconciliation_service import (
    project_reality_status,
    reconcile_project_reality,
    repair_stale_active_sessions as _repair_stale_active_sessions_impl,
)
from rail.manifest import load_manifest
import yaml

logger = logging.getLogger(__name__)

# State for tracking active autopilot loops per project
_active_autopilots: dict[str, bool] = {}
_autopilot_configs: dict[str, dict[str, Any]] = {}
_wake_events: dict[str, asyncio.Event] = {}

ONTOLOGY_READY_STATES = {"hydrated_on_this_device", "hydrated_on_another_device", "hydrating"}
ONTOLOGY_TASK_SPECS = (
    {
        "title": "Populate ontology pipeline steps for attachable sources",
        "match": ("populate", "pipeline", "source"),
        "status": "ready",
        "agent_role": "data",
        "repo_paths": [".ontology/pipelines", ".ontology/sources", ".ontology/transforms", "research_plan", "topics"],
        "acceptance_criteria": [
            "the default ontology pipeline declares concrete hydration steps for at least one attachable soccer source",
            "each step names a real source config and any required transform or parameterization",
            "pipeline notes distinguish immediately ingestable sources from manual-ingest-only sources",
            "the project is ready to rerun hydration against non-empty pipeline steps",
        ],
        "depends_on_task_ids": [],
        "runner": "codex_cli",
    },
    {
        "title": "Hydrate project ontology and register active artifacts",
        "match": ("hydrate", "ontology", "artifact"),
        "status": "ready",
        "agent_role": "data",
        "repo_paths": [".ontology", "research_plan", "artifacts"],
        "acceptance_criteria": [
            "the hydration pipeline executes for this project and produces ontology artifacts on disk",
            "active ontology artifact paths are registered so project artifact resolution succeeds",
            "hydration status reports reusable or current-device artifacts instead of not_hydrated",
            "ontology graph or class endpoints stop returning HTTP 428 for this project",
        ],
        "depends_on_task_ids": [],
        "runner": "codex_cli",
    },
    {
        "title": "Verify hydrated ontology health before research",
        "match": ("verify", "ontology", "health"),
        "status": "backlog",
        "agent_role": "health",
        "repo_paths": ["research_plan", ".ontology", "artifacts"],
        "acceptance_criteria": [
            "project-scoped ontology endpoints return success for classes or graph queries",
            "core domain entity classes and/or hydrated tables are present and non-empty",
            "health notes record any remaining hydration or lineage risks",
            "the task remains blocked or needs_changes if ontology-backed research is still impossible",
        ],
        "depends_on_task_ids": ["hydrate"],
        "runner": "codex_cli",
    },
    {
        "title": "Launch ontology-backed research after hydration",
        "match": ("ontology-backed", "research"),
        "status": "backlog",
        "agent_role": "planner",
        "repo_paths": ["research_plan", "topics", "artifacts"],
        "acceptance_criteria": [
            "planner creates or promotes downstream research tasks that explicitly depend on hydrated ontology artifacts",
            "no final analytical claim or dashboard is treated as complete unless ontology-backed queries are available",
            "project direction is updated from pre-hydration planning to ontology-backed research execution",
        ],
        "depends_on_task_ids": ["health"],
        "runner": "default",
    },
    {
        "title": "Propose ontology-answerable follow-up questions",
        "match": ("follow-up", "ontology", "question"),
        "status": "backlog",
        "agent_role": "planner",
        "repo_paths": ["research_plan", "topics", "artifacts"],
        "acceptance_criteria": [
            "planner produces 3-5 related research questions grounded in the current ontology coverage",
            "each question is classified as current_ontology, requires_expansion, or blocked_by_data",
            "question proposals record what ontology expansion would unlock higher-value follow-up work",
        ],
        "depends_on_task_ids": ["health"],
        "runner": "default",
    },
)

def trigger_wake(project_slug: str):
    """Wake up the autopilot loop for a project."""
    if project_slug in _wake_events:
        _wake_events[project_slug].set()

def _update_config(project_slug: str, **kwargs):
    if project_slug not in _autopilot_configs:
        _autopilot_configs[project_slug] = {}
    _autopilot_configs[project_slug].update(kwargs)


def _dependency_ids(task: dict[str, Any]) -> list[str]:
    deps = task.get("dependsOnTaskIds") or []
    return [str(dep) for dep in deps if dep]


def _dependencies_satisfied(task: dict[str, Any], task_by_id: dict[str, dict[str, Any]]) -> bool:
    for dep_id in _dependency_ids(task):
        dep = task_by_id.get(dep_id)
        if not dep or dep.get("status") != "done":
            return False
    return True


def _is_ontology_project(project: dict[str, Any]) -> bool:
    root = project.get("localRepoPath")
    if not root:
        return False
    if project.get("approach") == "ontology-first":
        return True
    return (Path(root).resolve() / ".ontology").exists()


def _pipeline_has_steps(project: dict[str, Any]) -> bool:
    root = project.get("localRepoPath")
    if not root:
        return False
    try:
        manifest = load_manifest(root)
    except Exception:
        return False
    slug = project.get("pipelineConfigSlug") or manifest.hydration.default_pipeline
    if not slug:
        return False
    pipeline_path = Path(root).resolve() / manifest.hydration.pipelines_dir / f"{slug}.yaml"
    if not pipeline_path.exists():
        return False
    try:
        payload = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(payload.get("steps"))


def _duckdb_has_populated_rows(duckdb_path: str | None) -> bool:
    if not duckdb_path:
        return False
    try:
        import duckdb  # type: ignore
    except Exception:
        return False
    try:
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        if not tables:
            conn.close()
            return False
        for (table_name,) in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]
            except Exception:
                continue
            if isinstance(count, int) and count > 0:
                conn.close()
                return True
        conn.close()
    except Exception:
        return False
    return False


def _ontology_has_populated_rows(project: dict[str, Any]) -> bool:
    return _duckdb_has_populated_rows(project.get("activeOntologyDuckdbPath"))


def _hydration_duckdb_path(hydration: dict[str, Any]) -> str | None:
    reusable = hydration.get("reusableArtifact") or {}
    if reusable.get("duckdbArtifactPath"):
        return str(reusable["duckdbArtifactPath"])

    current_artifacts = hydration.get("currentDeviceArtifacts") or []
    for artifact in current_artifacts:
        if (
            artifact.get("duckdbArtifactPath")
            and artifact.get("isCurrentCommit")
            and artifact.get("isCurrentManifest")
        ):
            return str(artifact["duckdbArtifactPath"])
    for artifact in current_artifacts:
        if artifact.get("duckdbArtifactPath"):
            return str(artifact["duckdbArtifactPath"])
    return None


def _matches_task(task: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [
            str(task.get("_id") or ""),
            str(task.get("title") or ""),
            str(task.get("description") or ""),
        ]
    ).lower()
    return all(needle in haystack for needle in needles)


def _matches_task_identity(task: dict[str, Any], needles: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [
            str(task.get("_id") or ""),
            str(task.get("title") or ""),
        ]
    ).lower()
    return all(needle in haystack for needle in needles)


def _find_existing_task(tasks: list[dict[str, Any]], needles: tuple[str, ...]) -> dict[str, Any] | None:
    for task in tasks:
        if _matches_task(task, needles):
            return task
    return None


def _parse_ontology_follow_up_questions(project: dict[str, Any]) -> list[dict[str, Any]]:
    root = project.get("localRepoPath")
    if not root:
        return []
    path = Path(str(root)).resolve() / "research_plan" / "ontology_answerable_follow_up_questions.md"
    if not path.exists():
        return []

    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            if current:
                questions.append(current)
            current = {"title": line[4:].strip(), "classification": None}
            continue
        if current is None:
            continue
        if line.startswith("- Classification:"):
            marker = line.split("`")
            if len(marker) >= 2:
                current["classification"] = marker[1].strip()
            else:
                current["classification"] = line.removeprefix("- Classification:").strip()
    if current:
        questions.append(current)
    return questions


async def _repair_stale_active_sessions(project: dict[str, Any]) -> dict[str, Any]:
    return await _repair_stale_active_sessions_impl(project)


async def _ensure_ontology_lifecycle_tasks(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    if not _is_ontology_project(project):
        return False
    try:
        hydration = await get_hydration_status(project=project)
    except Exception as exc:
        logger.warning("Autopilot could not read hydration status for %s: %s", project.get("slug"), exc)
        return False

    state = hydration.get("state")
    pipeline_has_steps = _pipeline_has_steps(project)
    ontology_has_rows = _duckdb_has_populated_rows(_hydration_duckdb_path(hydration)) or _ontology_has_populated_rows(project)
    needs_pipeline_population = not pipeline_has_steps
    hydrated_but_empty = state in ONTOLOGY_READY_STATES and not ontology_has_rows
    if state in ONTOLOGY_READY_STATES and not needs_pipeline_population and not hydrated_but_empty:
        return False

    board = await planner_service.ensure_main_board(project)
    changed = False
    created_or_found: dict[str, str] = {}
    live_tasks = list(tasks)

    for spec in ONTOLOGY_TASK_SPECS:
        if spec["match"] == ("populate", "pipeline", "source") and not needs_pipeline_population:
            continue
        existing = _find_existing_task(live_tasks, spec["match"])
        depends = []
        for dependency in spec["depends_on_task_ids"]:
            resolved = created_or_found.get(dependency)
            if resolved:
                depends.append(resolved)
        if existing is None:
            task = await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=spec["title"],
                description=(
                    spec["title"]
                    + ". This ontology-first project cannot be treated as complete until hydration succeeds, "
                    + "ontology health is verified, and downstream research is explicitly reopened from the hydrated ontology."
                ),
                status=spec["status"],
                agent_role=spec["agent_role"],
                repo_paths=spec["repo_paths"],
                acceptance_criteria=spec["acceptance_criteria"],
                depends_on_task_ids=depends,
                runner=spec["runner"],
            )
            existing = task
            live_tasks.append(task)
            changed = True
        created_or_found["hydrate" if "hydrate" in spec["match"] else "health" if "health" in spec["match"] else "research" if "research" in spec["match"] else "followup"] = str(existing["_id"])

    hydrate_task = _find_existing_task(live_tasks, ("hydrate", "ontology", "artifact"))
    if hydrate_task and hydrate_task.get("status") in {"done", "cancelled", "blocked"}:
        await planner_service.update_task(
            str(hydrate_task["_id"]),
            project=project,
            status="ready",
            blockerCategory=None,
            approvalState="granted",
            latestRunSummary=(
                f"Reopened by Autopilot because hydration state is `{state}`"
                + (", pipeline has no executable steps" if needs_pipeline_population else "")
                + (", and hydrated ontology is still empty" if hydrated_but_empty else "")
                + "."
            ),
        )
        changed = True

    pipeline_task = _find_existing_task(live_tasks, ("populate", "pipeline", "source"))
    if needs_pipeline_population and pipeline_task and pipeline_task.get("status") in {"done", "cancelled", "blocked"}:
        await planner_service.update_task(
            str(pipeline_task["_id"]),
            project=project,
            status="ready",
            blockerCategory=None,
            approvalState="granted",
            latestRunSummary="Reopened by Autopilot because the default ontology pipeline still has no executable steps.",
        )
        changed = True

    if changed:
        await planner_service.sync_planner_files(project, board)
        logger.info(
            "Autopilot: ensured ontology lifecycle tasks for %s (state=%s, pipeline_has_steps=%s, ontology_has_rows=%s)",
            project.get("slug"),
            state,
            pipeline_has_steps,
            ontology_has_rows,
        )
    return changed


async def _ensure_ontology_expansion_tasks(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    if not _is_ontology_project(project):
        return False
    questions = _parse_ontology_follow_up_questions(project)
    if not questions:
        return False

    board = await planner_service.ensure_main_board(project)
    changed = False
    live_tasks = list(tasks)
    for question in questions:
        classification = str(question.get("classification") or "").strip().lower()
        title = str(question.get("title") or "").strip()
        if not title:
            continue
        if classification == "requires_expansion":
            task_title = f"Expand ontology coverage for: {title}"
            if any(str(task.get("title") or "") == task_title for task in live_tasks):
                continue
            task = await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    f"Create the ontology expansion needed to answer: {title}. "
                    "This should result in concrete source, pipeline, transform, or ontology-verification work."
                ),
                status="ready",
                agent_role="data",
                repo_paths=[".ontology/sources", ".ontology/pipelines", ".ontology/transforms", "research_plan", "topics"],
                acceptance_criteria=[
                    "the missing ontology coverage is translated into concrete source or pipeline work",
                    "the task records which source, transform, or relationship expansion is required",
                    "follow-on ontology verification work is identified if hydration changes are needed",
                ],
                runner="codex_cli",
            )
            live_tasks.append(task)
            changed = True
        elif classification == "blocked_by_data":
            task_title = f"Resolve data blocker for: {title}"
            if any(str(task.get("title") or "") == task_title for task in live_tasks):
                continue
            task = await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    f"Investigate and document the missing data access needed to answer: {title}. "
                    "Record the missing source, access blocker, and what would unblock ontology expansion."
                ),
                status="ready",
                agent_role="research",
                repo_paths=["research_plan", "topics", ".ontology/sources"],
                acceptance_criteria=[
                    "the missing source or access blocker is documented explicitly",
                    "the task records whether the blocker is licensing, permissions, provenance, or coverage",
                    "the repo contains the next recommended expansion path if the blocker can be resolved",
                ],
                runner="codex_cli",
            )
            live_tasks.append(task)
            changed = True

    if changed:
        await planner_service.sync_planner_files(project, board)
        logger.info("Autopilot: ensured ontology expansion tasks for %s", project.get("slug"))
    return changed


async def _ensure_project_reality_repair_tasks(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    reality = await project_reality_status(project, tasks=tasks, active_sessions=[])
    details = reality.get("details") or {}
    ontology_drift = details.get("ontologyArtifactDrift") or {}
    artifact_drift = details.get("artifactRegistryDrift") or {}
    if not ontology_drift.get("hasDrift") and not artifact_drift.get("hasDrift"):
        return False

    board = await planner_service.ensure_main_board(project)
    changed = False
    live_tasks = list(tasks)

    if ontology_drift.get("hasDrift"):
        task_title = "Repair active ontology artifact pointer drift"
        if not any(str(task.get("title") or "") == task_title for task in live_tasks):
            task = await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Reconcile the project's active ontology pointers with the current hydration artifact registry. "
                    "Ensure the project record points at the correct current DuckDB/ontology artifacts."
                ),
                status="ready",
                agent_role="data",
                repo_paths=[".ontology", "research_plan"],
                acceptance_criteria=[
                    "the active ontology pointer drift is reconciled against the hydration registry",
                    "the project points at the expected current ontology artifacts",
                    "the repair records the previous and updated artifact paths if they changed",
                ],
                runner="codex_cli",
            )
            live_tasks.append(task)
            changed = True

    if artifact_drift.get("hasDrift"):
        task_title = "Reconcile artifact registry drift"
        if not any(str(task.get("title") or "") == task_title for task in live_tasks):
            task = await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair drift between artifacts on disk and artifact lineage records. "
                    "Either register untracked final artifacts with explicit lineage or remove stale lineage entries for missing files."
                ),
                status="ready",
                agent_role="health",
                repo_paths=["artifacts", "research_plan/state", "research_plan"],
                acceptance_criteria=[
                    "untracked artifacts on disk are either registered with lineage or explicitly removed",
                    "artifact lineage entries for missing files are reconciled or cleared",
                    "project reality no longer reports artifact registry drift after the repair",
                ],
                runner="codex_cli",
            )
            live_tasks.append(task)
            changed = True

    if changed:
        await planner_service.sync_planner_files(project, board)
        logger.info("Autopilot: ensured project reality repair tasks for %s", project.get("slug"))
    return changed


async def _ensure_integrity_repair_tasks(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    root = planner_service.project_root_from_record(project)
    if root is None:
        return False
    workflow = summarize_agent_workflow_health(root)
    data = workflow.get("data") or {}
    coding = workflow.get("coding") or {}
    health = workflow.get("health") or {}
    datasets_missing_provenance = [str(item) for item in (data.get("datasetsMissingProvenance") or []) if str(item).strip()]
    datasets_missing_freshness = [str(item) for item in (data.get("datasetsMissingFreshness") or []) if str(item).strip()]
    artifacts_missing_lineage = [str(item) for item in (coding.get("artifactsMissingLineage") or []) if str(item).strip()]
    artifacts_missing_verification_commands = [str(item) for item in (coding.get("artifactsMissingVerificationCommands") or []) if str(item).strip()]
    artifacts_missing_verification = [str(item) for item in (coding.get("artifactsMissingVerification") or []) if str(item).strip()]
    missing_evidence_claims = [str(item) for item in (health.get("missingEvidenceClaims") or []) if str(item).strip()]
    stale_sources = [str(item) for item in (health.get("staleSources") or []) if str(item).strip()]
    failed_verification_runs = [str(item) for item in (health.get("failedVerificationRuns") or []) if str(item).strip()]
    reproducibility_gaps = [str(item) for item in (health.get("reproducibilityGaps") or []) if str(item).strip()]
    inadmissible_sources = [str(item) for item in (health.get("inadmissibleSources") or []) if str(item).strip()]
    if (
        not inadmissible_sources
        and not missing_evidence_claims
        and not stale_sources
        and not failed_verification_runs
        and not reproducibility_gaps
        and not datasets_missing_provenance
        and not datasets_missing_freshness
        and not artifacts_missing_lineage
        and not artifacts_missing_verification_commands
        and not artifacts_missing_verification
    ):
        return False

    board = await planner_service.ensure_main_board(project)
    live_titles = {str(task.get("title") or "") for task in tasks}
    changed = False

    if datasets_missing_provenance or datasets_missing_freshness:
        task_title = "Repair dataset provenance and freshness metadata"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair dataset metadata gaps before trusted promotion. "
                    "Datasets should retain source provenance and freshness metadata so downstream analyses can be audited."
                ),
                status="ready",
                agent_role="data",
                repo_paths=["research_plan/state", ".ontology/sources", ".ontology/pipelines", "artifacts"],
                acceptance_criteria=[
                    "datasets missing provenance are linked to explicit source records",
                    "datasets missing freshness metadata record a current freshness state or are left explicitly blocked",
                    "trusted datasets no longer depend on missing provenance or freshness metadata",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    if artifacts_missing_lineage or artifacts_missing_verification_commands or artifacts_missing_verification:
        task_title = "Repair analysis lineage and verification metadata"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair analysis artifact metadata before trusted promotion. "
                    "Deterministic analyses should declare their inputs, scripts, verification commands, and verification runs."
                ),
                status="ready",
                agent_role="coding",
                repo_paths=["research_plan/state", "artifacts", "topics"],
                acceptance_criteria=[
                    "analysis artifacts missing lineage declare their scripts and inputs",
                    "deterministic analyses record verification commands where applicable",
                    "analysis artifacts no longer rely on missing verification runs for trusted promotion",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    if missing_evidence_claims:
        task_title = "Repair unsupported claims and verification evidence"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair unsupported or weakly evidenced claims before trusted promotion. "
                    "Each affected claim should gain explicit evidence links, or the dependent artifacts should be downgraded "
                    "so unsupported narrative does not remain in trusted outputs."
                ),
                status="ready",
                agent_role="health",
                repo_paths=["research_plan/state", "artifacts", "topics"],
                acceptance_criteria=[
                    "each unsupported claim is either linked to explicit evidence or downgraded from trusted outputs",
                    "dependent artifacts no longer rely on unsupported or semantic-suggestion-only claims for trusted promotion",
                    "the repair records which claims changed and what evidence or downgrade action was applied",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    if stale_sources:
        task_title = "Refresh stale sources or rerun dependent analyses"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair stale-source trust blockers before trusted promotion. "
                    "Refresh the stale sources where possible, or rerun and downgrade dependent analyses until freshness is restored."
                ),
                status="ready",
                agent_role="health",
                repo_paths=["research_plan/state", ".ontology/sources", "artifacts", "topics"],
                acceptance_criteria=[
                    "each stale source is refreshed or explicitly documented as still stale",
                    "dependent artifacts are rerun, downgraded, or left blocked until fresh source state is restored",
                    "the repair records which sources were refreshed and which artifacts were affected",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    if failed_verification_runs:
        task_title = "Resolve failed verification runs before trusted promotion"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair failed or blocked verification runs before trusted promotion. "
                    "Fix the underlying reproducibility or analysis issues, rerun verification, and record the passing result."
                ),
                status="ready",
                agent_role="health",
                repo_paths=["research_plan/state", "artifacts", "topics"],
                acceptance_criteria=[
                    "each failed or blocked verification run is either rerun successfully or explicitly superseded",
                    "underlying reproducibility or analysis issues are fixed before the rerun is recorded",
                    "trusted artifacts no longer depend on failed verification runs",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    if reproducibility_gaps:
        task_title = "Repair reproducibility metadata for trusted artifacts"
        if task_title not in live_titles:
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task_title,
                description=(
                    "Repair reproducibility gaps before trusted promotion. "
                    "Trusted artifacts should declare their scripts, inputs, and verification path so they can be rerun and audited."
                ),
                status="ready",
                agent_role="health",
                repo_paths=["research_plan/state", "artifacts", "topics"],
                acceptance_criteria=[
                    "artifacts with reproducibility gaps declare the required scripts, inputs, and metadata",
                    "verification commands or equivalent reproducibility instructions are recorded where applicable",
                    "trusted artifacts no longer depend on unresolved reproducibility gaps",
                ],
                runner="codex_cli",
            )
            live_titles.add(task_title)
            changed = True

    task_title = "Resolve inadmissible sources for trusted outputs"
    if inadmissible_sources and task_title not in live_titles:
        await planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title=task_title,
            description=(
                "Repair source admissibility blockers that prevent trusted promotion. "
                "Each inadmissible source should be upgraded to an admissible state with real evidence, "
                "or the dependent claims and artifacts should be downgraded so they are no longer treated as trusted outputs."
            ),
            status="ready",
            agent_role="health",
            repo_paths=["research_plan/state", ".ontology/sources", "artifacts", "topics"],
            acceptance_criteria=[
                "every inadmissible source is either repaired to an admissible state or explicitly removed from trusted promotion paths",
                "affected claims and artifacts are downgraded, rerouted, or re-evidenced so integrity no longer reports inadmissible sources",
                "the repair notes why each source was inadmissible and what changed",
            ],
            runner="codex_cli",
        )
        changed = True

    if changed:
        await planner_service.sync_planner_files(project, board)
        logger.info(
            "Autopilot: ensured integrity repair tasks for %s (dataset_provenance=%s, dataset_freshness=%s, analysis_lineage=%s, analysis_verification_commands=%s, analysis_verification_runs=%s, claims=%s, stale_sources=%s, failed_verification_runs=%s, reproducibility_gaps=%s, inadmissible_sources=%s)",
            project.get("slug"),
            len(datasets_missing_provenance),
            len(datasets_missing_freshness),
            len(artifacts_missing_lineage),
            len(artifacts_missing_verification_commands),
            len(artifacts_missing_verification),
            len(missing_evidence_claims),
            len(stale_sources),
            len(failed_verification_runs),
            len(reproducibility_gaps),
            len(inadmissible_sources),
        )
    return changed


async def _ensure_ontology_repair_task(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> bool:
    ontology = (auditors or {}).get("ontology") or {}
    if ontology.get("status") != "blocked":
        return False

    task_title = "Repair ontology readiness blockers"
    if any(str(task.get("title") or "") == task_title for task in tasks):
        return False

    board = await planner_service.ensure_main_board(project)
    await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=task_title,
        description=(
            "Repair ontology blockers that still prevent ontology-backed work. "
            "This includes hydration failures, empty artifacts, broken active pointers, or missing ontology-health verification."
        ),
        status="ready",
        agent_role="data",
        repo_paths=[".ontology", "research_plan", "artifacts"],
        acceptance_criteria=[
            "ontology blockers are traced to a concrete hydration, artifact, or verification issue",
            "the active ontology artifact is hydrated, current, and usable for ontology-backed work",
            "the ontology auditor no longer reports readiness blockers after the repair",
        ],
        runner="codex_cli",
    )
    await planner_service.sync_planner_files(project, board)
    logger.info("Autopilot: ensured ontology repair task for %s", project.get("slug"))
    return True


async def _reconcile_ontology_lifecycle_state(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    if not _is_ontology_project(project):
        return False
    try:
        hydration = await get_hydration_status(project=project)
    except Exception as exc:
        logger.warning("Autopilot could not reconcile ontology lifecycle state for %s: %s", project.get("slug"), exc)
        return False

    state = hydration.get("state")
    duckdb_path = _hydration_duckdb_path(hydration) or project.get("activeOntologyDuckdbPath")
    ontology_has_rows = _duckdb_has_populated_rows(duckdb_path)
    if state not in ONTOLOGY_READY_STATES or not ontology_has_rows:
        return False

    board = await planner_service.ensure_main_board(project)
    changed = False

    async def _update(task: dict[str, Any], **fields: Any) -> None:
        nonlocal changed
        await planner_service.update_task(str(task["_id"]), project=project, **fields)
        task.update(fields)
        changed = True

    for task in tasks:
        if _matches_task_identity(task, ("hydrate", "ontology", "artifact")) or _matches_task_identity(task, ("rerun", "hydration", "pipeline")):
            if task.get("status") != "done":
                await _update(
                    task,
                    status="done",
                    blockerCategory=None,
                    approvalState=None,
                    latestRunSummary=(
                        f"Hydration succeeded with state `{state}` and registered populated ontology artifacts"
                        + (f" at `{duckdb_path}`." if duckdb_path else ".")
                    ),
                )
        elif _matches_task_identity(task, ("reconcile", "hydrated", "empty")):
            if task.get("status") not in {"done", "cancelled"}:
                await _update(
                    task,
                    status="done",
                    blockerCategory=None,
                    approvalState=None,
                    latestRunSummary=(
                        "Superseded by successful hydration rerun: the active ontology artifact now contains populated rows."
                    ),
                )
        elif _matches_task_identity(task, ("diagnose", "publish", "hydration", "artifact")) or _matches_task_identity(task, ("repair", "hydration", "provenance", "freshness")):
            if task.get("status") not in {"done", "cancelled"}:
                await _update(
                    task,
                    status="done",
                    blockerCategory=None,
                    approvalState=None,
                    latestRunSummary=(
                        "Superseded by successful hydration rerun: populated ontology artifacts are registered and the earlier publish/provenance blocker path has been cleared."
                    ),
                )
        elif _matches_task_identity(task, ("implement", "first", "pass", "pipeline")):
            if task.get("status") not in {"done", "cancelled"}:
                await _update(
                    task,
                    status="done",
                    blockerCategory=None,
                    approvalState=None,
                    latestRunSummary=(
                        "Superseded by the committed non-empty soccer pipeline and successful hydration rerun."
                    ),
                )
        elif _matches_task_identity(task, ("verify", "non-empty", "ontology")) or _matches_task_identity(task, ("verify", "ontology", "health")):
            if task.get("status") in {"backlog", "blocked", "awaiting_approval", "cancelled"}:
                await _update(
                    task,
                    status="ready",
                    blockerCategory=None,
                    approvalState="granted",
                    latestRunSummary=(
                        f"Hydration state is `{state}` and the active ontology artifact contains populated rows; verification can proceed."
                    ),
                )

    if changed:
        await planner_service.sync_planner_files(project, board)
        logger.info(
            "Autopilot: reconciled ontology lifecycle state for %s (state=%s, duckdb_path=%s)",
            project.get("slug"),
            state,
            duckdb_path,
        )
    return changed


def _task_priority(task: dict[str, Any]) -> tuple[int, str]:
    boost = int(task.get("_autopilotPriorityBoost") or 0)
    weight = {"high": 0, "medium": 1, "low": 2, None: 3}.get(task.get("priority"), 3)
    return (boost, weight, str(task.get("_id") or ""))


def _has_ready_task_title(tasks: list[dict[str, Any]], title: str) -> bool:
    for task in tasks:
        if str(task.get("title") or "") != title:
            continue
        if str(task.get("status") or "") not in {"ready", "running"}:
            continue
        return True
    return False


def _should_skip_planner_for_ready_repair(tasks: list[dict[str, Any]], auditors: dict[str, Any] | None) -> bool:
    auditors = auditors or {}
    ready_tasks = [task for task in tasks if str(task.get("status") or "") == "ready" and task.get("approvalState") != "pending"]
    filtered_ready = _filter_ready_tasks_for_auditors(ready_tasks, auditors)
    if (auditors.get("ontology") or {}).get("status") == "blocked" and filtered_ready:
        return True
    if (auditors.get("integrity") or {}).get("status") == "blocked" and filtered_ready:
        return True
    if (auditors.get("closeout") or {}).get("status") == "blocked" and _has_ready_task_title(tasks, "Resolve closeout blockers"):
        return True
    if _control_plane_auditor_gate(auditors).get("blocked") and _has_ready_task_title(tasks, "Reconcile control-plane drift and stale sessions"):
        return True
    return False


def _apply_auditor_priority_boosts(
    ready_tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not ready_tasks:
        return []
    auditors = auditors or {}
    boosted: list[dict[str, Any]] = [dict(task) for task in ready_tasks]
    ontology_blocked = (auditors.get("ontology") or {}).get("status") == "blocked"
    integrity_blocked = (auditors.get("integrity") or {}).get("status") == "blocked"
    closeout_blocked = (auditors.get("closeout") or {}).get("status") == "blocked"
    control_plane_blocked = _control_plane_auditor_gate(auditors).get("blocked")

    for task in boosted:
        title = str(task.get("title") or "").lower()
        boost = 0
        if control_plane_blocked and title == "reconcile control-plane drift and stale sessions":
            boost = min(boost, -30)
        if ontology_blocked:
            if any(token in title for token in ("repair ontology", "repair ontology readiness", "repair ontology readiness blockers")):
                boost = min(boost, -25)
            elif any(token in title for token in ("hydrate", "pipeline", "source", "ontology health")):
                boost = min(boost, -20)
        if integrity_blocked and any(
            token in title
            for token in (
                "repair unsupported claims",
                "refresh stale sources",
                "resolve failed verification",
                "repair reproducibility",
                "resolve inadmissible sources",
                "repair dataset provenance",
                "repair analysis lineage",
            )
        ):
            boost = min(boost, -10)
        if closeout_blocked and any(token in title for token in ("resolve closeout blockers", "reconcile control-plane", "repair closeout")):
            boost = min(boost, -5)
        if boost:
            task["_autopilotPriorityBoost"] = boost
    return boosted


def _task_matches_ontology_repair_work(task: dict[str, Any]) -> bool:
    title = str(task.get("title") or "").strip().lower()
    role = str(task.get("agentRole") or task.get("agent_role") or "").strip().lower()
    if title == "repair ontology readiness blockers":
        return True
    if title in {
        "populate ontology pipeline steps for attachable sources",
        "hydrate project ontology and register active artifacts",
        "verify hydrated ontology health before research",
    }:
        return True
    if role in {"data", "health"} and any(token in title for token in ("hydrate", "pipeline", "source", "health", "repair ontology")):
        return True
    return False


def _task_matches_integrity_repair_work(task: dict[str, Any]) -> bool:
    title = str(task.get("title") or "").strip().lower()
    return title in {
        "repair unsupported claims and verification evidence",
        "refresh stale sources or rerun dependent analyses",
        "resolve failed verification runs before trusted promotion",
        "repair reproducibility metadata for trusted artifacts",
        "resolve inadmissible sources for trusted outputs",
        "repair dataset provenance and freshness metadata",
        "repair analysis lineage and verification metadata",
    }


def _filter_ready_tasks_for_auditors(
    ready_tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not ready_tasks:
        return []
    ontology_auditor = (auditors or {}).get("ontology") or {}
    filtered = _apply_auditor_priority_boosts(ready_tasks, auditors)
    if _control_plane_auditor_gate(auditors).get("blocked"):
        filtered = [
            task for task in filtered
            if str(task.get("title") or "") == "Reconcile control-plane drift and stale sessions"
        ]
    if ontology_auditor.get("status") == "blocked":
        filtered = [task for task in filtered if _task_matches_ontology_repair_work(task)]

    integrity_auditor = (auditors or {}).get("integrity") or {}
    if integrity_auditor.get("status") == "blocked":
        filtered = [task for task in filtered if _task_matches_integrity_repair_work(task)]
    return filtered


def _task_allowed_for_auditors(
    task: dict[str, Any],
    auditors: dict[str, Any] | None,
) -> bool:
    return bool(_filter_ready_tasks_for_auditors([task], auditors))


def _control_plane_auditor_gate(auditors: dict[str, Any] | None) -> dict[str, Any]:
    session_auditor = (auditors or {}).get("session") or {}
    planner_auditor = (auditors or {}).get("planner") or {}
    blockers: list[str] = []
    if session_auditor.get("status") == "blocked":
        blockers.extend(str(item) for item in (session_auditor.get("blockers") or []) if item)
    if planner_auditor.get("status") == "blocked":
        blockers.extend(str(item) for item in (planner_auditor.get("blockers") or []) if item)
    if not blockers:
        return {"blocked": False, "blockers": []}
    return {"blocked": True, "blockers": list(dict.fromkeys(blockers))}


async def _ensure_control_plane_repair_tasks(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> bool:
    gate = _control_plane_auditor_gate(auditors)
    if not gate.get("blocked"):
        return False

    board = await planner_service.ensure_main_board(project)
    task_title = "Reconcile control-plane drift and stale sessions"
    if any(str(task.get("title") or "") == task_title for task in tasks):
        return False

    await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=task_title,
        description=(
            "Repair persistent control-plane blockers such as stale runtime sessions, duplicate task files, "
            "task/session state mismatches, stale or missing post-run audits, non-canonical running-agent session statuses, non-canonical running-agent session roles, non-canonical running-agent session runners, non-canonical secret policy role mappings, or non-canonical role config aliases so autopilot can safely advance from audited truth."
        ),
        status="ready",
        agent_role="health",
        repo_paths=["research_plan", "research_plan/state", ".ontology"],
        acceptance_criteria=[
            "stale runtime sessions are finalized or cancelled from durable session truth",
            "duplicate task files, task/session mismatches, stale session audits, running-agent status drift, running-agent role drift, running-agent runner drift, secret policy role drift, and role config alias drift are reconciled",
            "session and planner auditors no longer report control-plane blockers after the repair",
        ],
        runner="codex_cli",
    )
    await planner_service.sync_planner_files(project, board)
    logger.info("Autopilot: ensured control-plane repair task for %s", project.get("slug"))
    return True


async def _ensure_closeout_repair_task(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> bool:
    closeout = (auditors or {}).get("closeout") or {}
    if closeout.get("status") != "blocked":
        return False

    board = await planner_service.ensure_main_board(project)
    task_title = "Resolve closeout blockers"
    if any(str(task.get("title") or "") == task_title for task in tasks):
        return False

    await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=task_title,
        description=(
            "Repair remaining closeout blockers so the project can complete cleanly. "
            "This includes unresolved ontology, integrity, final-artifact, or follow-up-question obligations that still block finalization."
        ),
        status="ready",
        agent_role="health",
        repo_paths=["research_plan", "research_plan/state", "artifacts", ".ontology"],
        acceptance_criteria=[
            "closeout blockers are documented and resolved or explicitly rerouted into durable planner work",
            "final artifacts, ontology state, and integrity state satisfy closeout requirements",
            "the closeout auditor no longer reports blockers after the repair",
        ],
        runner="codex_cli",
    )
    await planner_service.sync_planner_files(project, board)
    logger.info("Autopilot: ensured closeout repair task for %s", project.get("slug"))
    return True


def _planner_turn_message(auditors: dict[str, Any] | None) -> str:
    base = (
        "[AUTOPILOT MODE] Analyze the project state. If any tasks are 'ready', use launch_task_runner to start them. "
        "If tasks recently finished, analyze findings. If everything is done, synthesize the final report. "
        "Always move the project forward."
    )
    auditors = auditors or {}
    ontology = auditors.get("ontology") or {}
    integrity = auditors.get("integrity") or {}
    closeout = auditors.get("closeout") or {}

    if ontology.get("status") == "blocked":
        return (
            "[AUTOPILOT MODE] Ontology readiness is blocked. Focus only on hydration, source attachment, pipeline repair, "
            "or ontology health verification tasks. Do not plan or synthesize downstream research until ontology blockers are cleared."
        )
    if integrity.get("status") == "blocked":
        return (
            "[AUTOPILOT MODE] Integrity is blocked. Focus only on provenance repair, evidence collection, verification, "
            "claim cleanup, or other trust-repair tasks. Do not plan final synthesis or promote analytical outputs until integrity blockers are cleared."
        )
    if closeout.get("status") == "blocked":
        return (
            "[AUTOPILOT MODE] Closeout is blocked. Focus only on clearing remaining closeout blockers such as unfinished tasks, "
            "active sessions, ontology issues, or integrity issues. Do not create new speculative research branches."
        )
    return base


async def _launch_ready_task(project: dict[str, Any], ready_tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not ready_tasks:
        return None
    candidate = sorted(ready_tasks, key=_task_priority)[0]
    result = await planner_runtime._execute_planner_tool(
        project,
        "launch_task_runner",
        {"task_id": str(candidate["_id"])},
    )
    return result


async def _launch_ready_tasks_if_available(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
    project_slug: str,
) -> bool:
    ready_tasks = [t for t in tasks if t["status"] == "ready" and t.get("approvalState") != "pending"]
    ready_tasks = _filter_ready_tasks_for_auditors(ready_tasks, auditors)
    if not ready_tasks:
        return False

    cancelled_task_ids = {str(t["_id"]) for t in tasks if t.get("status") == "cancelled"}
    for event in await list_decision_events(project, status="open"):
        referenced_cancelled = [
            ref.removeprefix("task:")
            for ref in event.evidenceRefs
            if ref.startswith("task:")
        ]
        if event.type == "no_ready_tasks":
            await mark_decision_event(project, event._id, "handled")
        elif (
            event.type == "task_cancelled_with_dependents"
            and referenced_cancelled
            and not any(task_id in cancelled_task_ids for task_id in referenced_cancelled)
        ):
            await mark_decision_event(project, event._id, "handled")
    try:
        launch_result = await _launch_ready_task(project, ready_tasks)
    except Exception as exc:
        logger.error("Autopilot: Failed to launch ready task for %s: %s", project_slug, exc)
        launch_result = {"error": str(exc)}
    if launch_result and not launch_result.get("error"):
        logger.info("Autopilot: Launched ready task for %s", project_slug)
        return True
    if launch_result and launch_result.get("error"):
        logger.info("Autopilot: Ready task launch deferred for %s: %s", project_slug, launch_result.get("error"))
    return False


async def _reload_tasks_and_auditors(
    project: dict[str, Any],
    board_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    tasks = await planner_service.list_tasks(board_id, project=project)
    active_worker = await running_agent_service.find_active_worker(project["_id"])
    auditor_sessions = [active_worker] if active_worker else []
    auditors = await build_auditor_statuses(project, tasks=tasks, active_sessions=auditor_sessions)
    return tasks, active_worker, auditors


async def _poll_active_worker_if_present(
    project: dict[str, Any],
    active_worker: dict[str, Any] | None,
    project_slug: str,
) -> str | None:
    if not active_worker:
        return None
    session_id = active_worker["_id"]
    if active_worker.get("status") == "awaiting_input":
        await raise_decision_event(
            project,
            source="autopilot",
            event_type="awaiting_input",
            severity="needs_planner",
            summary=(
                f"Worker session {session_id} is awaiting input. "
                "Decide whether to answer, reroute, cancel, or ask the user."
            ),
            evidence_refs=[f"runner_session:{session_id}"],
            recommended_actions=[
                "Inspect worker question",
                "Answer if policy-safe",
                "Ask user if sensitive or ambiguous",
            ],
        )
    _update_config(project_slug, last_action=f"Polling active worker session: {session_id}")
    logger.info("Autopilot: Waiting for worker %s (%s) to complete...", session_id, active_worker.get("role"))
    try:
        await session_lifecycle.poll_session_until_done(
            session_id,
            project_id=project["_id"],
            max_polls=100,
            poll_interval_seconds=5,
        )
        logger.info("Worker %s finished.", active_worker["_id"])
        return "polled"
    except Exception as exc:
        logger.error("Error polling worker in autopilot: %s", exc)
        await asyncio.sleep(10)
        return "error"


async def _mark_project_completed(project: dict[str, Any]) -> None:
    project_id = project.get("_id") or project.get("projectId")
    if not project_id:
        return
    local_repo_path = project.get("localRepoPath")
    repo_root = Path(local_repo_path).resolve() if local_repo_path else None
    derived_status = "draft"
    if project.get("lastHydratedAt") or project.get("activeOntologyDuckdbPath") or project.get("status") == "hydrated":
        derived_status = "hydrated"
    elif project.get("pipelineConfigSlug"):
        derived_status = "ready"
    elif repo_root is not None:
        pipeline_roots = (
            repo_root / ".ontology" / "pipelines",
            repo_root / "configs" / "pipelines",
        )
        if any(root.is_dir() and any(root.glob("*.yaml")) for root in pipeline_roots):
            derived_status = "ready"
    try:
        await convex.mutation(
            "projects:updateById",
            {
                "projectId": project_id,
                "status": derived_status,
            },
        )
    except Exception as exc:
        logger.warning("Failed to mark project %s terminal status %s: %s", project.get("slug"), derived_status, exc)


async def _ontology_health_gate(project: dict[str, Any]) -> dict[str, Any]:
    if not _is_ontology_project(project):
        return {"blocked": False, "reason": None}
    try:
        hydration = await get_hydration_status(project=project)
    except Exception as exc:
        return {"blocked": True, "reason": f"Could not read hydration status: {exc}"}
    state = hydration.get("state")
    duckdb_path = _hydration_duckdb_path(hydration) or project.get("activeOntologyDuckdbPath")
    if state not in ONTOLOGY_READY_STATES:
        return {"blocked": True, "reason": f"Ontology hydration state is `{state}`."}
    if not _duckdb_has_populated_rows(duckdb_path) and not _ontology_has_populated_rows(project):
        return {"blocked": True, "reason": "Ontology artifact exists but does not contain populated rows."}
    return {"blocked": False, "reason": None}


async def _closeout_gate(project: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    if not project_root or not project_root.exists():
        return {"blocked": True, "reason": "Project repo root is unavailable for closeout."}

    active_sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    if active_sessions:
        return {"blocked": True, "reason": f"{len(active_sessions)} active session(s) still exist."}

    unfinished = [task for task in tasks if task.get("status") not in {"done", "cancelled"}]
    if unfinished:
        return {"blocked": True, "reason": f"{len(unfinished)} non-terminal task(s) remain."}

    ontology_gate = await _ontology_health_gate(project)
    if ontology_gate.get("blocked"):
        return ontology_gate

    manifest = load_manifest(project_root)
    integrity_gate = evaluate_integrity_gate(project_root, manifest, action="closeout")
    if integrity_gate.get("blocked"):
        reasons = integrity_gate.get("reasons") or []
        return {"blocked": True, "reason": str(reasons[0] if reasons else "Integrity closeout gate is blocked.")}

    return {"blocked": False, "reason": None}

async def start_autopilot(project_slug: str, auto_approve: bool = False):
    """
    Starts the autopilot loop for a project if not already running.
    """
    _autopilot_configs[project_slug] = {"auto_approve": auto_approve}
    
    if _active_autopilots.get(project_slug):
        logger.info(f"Autopilot already running for {project_slug}")
        return
    
    if project_slug not in _wake_events:
        _wake_events[project_slug] = asyncio.Event()
        
    _active_autopilots[project_slug] = True
    try:
        await run_autopilot_loop(project_slug)
    finally:
        _active_autopilots[project_slug] = False
        _wake_events.pop(project_slug, None)

async def stop_autopilot(project_slug: str):
    """
    Stops the autopilot loop for a project.
    """
    _active_autopilots[project_slug] = False

async def run_autopilot_loop(project_slug: str):
    """
    God Mode: Continuously run the planner and agents until the project is done.
    """
    logger.info(f"Starting Autopilot God Mode for project: {project_slug}")
    
    project = await planner_service.get_project_by_slug(project_slug)
    max_iterations = 40
    consecutive_idle_turns = 0
    
    for i in range(max_iterations):
        if not _active_autopilots.get(project_slug):
            logger.info(f"Autopilot stopped for {project_slug}")
            break
            
        logger.info(f"Autopilot iteration {i+1}/{max_iterations} for {project_slug}")
        project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
        reconciliation = await reconcile_project_reality(project)
        if reconciliation.get("removedTaskFiles"):
            _update_config(
                project_slug,
                last_action="Reconciled duplicate task files",
                last_turn_result=", ".join(reconciliation["removedTaskFiles"][:5]),
            )
        if reconciliation.get("updatedTaskIds"):
            _update_config(
                project_slug,
                last_action="Reconciled task states from session truth",
                last_turn_result=", ".join(reconciliation["updatedTaskIds"][:5]),
            )
        if reconciliation.get("repairedSessionIds"):
            _update_config(
                project_slug,
                last_action="Reconciled stale active sessions",
                last_turn_result=", ".join(reconciliation["repairedSessionIds"][:5]),
            )
        if reconciliation.get("repairedAuditSessionIds"):
            _update_config(
                project_slug,
                last_action="Rebuilt stale post-run audits",
                last_turn_result=", ".join(reconciliation["repairedAuditSessionIds"][:5]),
            )
        audit_gate = audit_gate_status(project_root) if project_root and project_root.exists() else {"blocked": False}
        if audit_gate.get("blocked"):
            _update_config(
                project_slug,
                last_action="Waiting for audited truth",
                last_turn_result=str(audit_gate.get("reason") or "Audit gate blocked autopilot."),
            )
            await raise_decision_event(
                project,
                source="autopilot",
                event_type="audit_required_before_advance",
                severity="needs_planner",
                summary=str(audit_gate.get("reason") or "Audit gate blocked autopilot."),
                evidence_refs=[f"runner_session:{session_id}" for session_id in (audit_gate.get("staleSessionIds") or [])[:8]],
                recommended_actions=[
                    "Finalize or rerun post-run audit",
                    "Reconcile session state against repo outputs",
                    "Advance only after audited truth is refreshed",
                ],
            )
            _wake_events[project_slug].clear()
            try:
                await asyncio.wait_for(_wake_events[project_slug].wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
            continue
        
        config = _autopilot_configs.get(project_slug, {})

        board = await planner_service.ensure_main_board(project)
        tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
        if await _ensure_ontology_lifecycle_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _ensure_ontology_expansion_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _ensure_project_reality_repair_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _ensure_integrity_repair_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _ensure_ontology_repair_task(project, tasks, auditors):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _reconcile_ontology_lifecycle_state(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        if await _ensure_control_plane_repair_tasks(project, tasks, auditors):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
        control_plane_gate = _control_plane_auditor_gate(auditors)
        if control_plane_gate.get("blocked"):
            if _has_ready_task_title(tasks, "Reconcile control-plane drift and stale sessions"):
                logger.info("Autopilot: control-plane repair task is ready; bypassing wait gate to allow repair launch.")
            else:
                blockers = control_plane_gate.get("blockers") or []
                _update_config(
                    project_slug,
                    last_action="Waiting for control-plane repair",
                    last_turn_result=str(blockers[0] if blockers else "Control-plane auditors blocked autopilot."),
                )
                await raise_decision_event(
                    project,
                    source="autopilot",
                    event_type="control_plane_auditor_blocked",
                    severity="needs_planner",
                    summary=str(blockers[0] if blockers else "Control-plane auditors blocked autopilot."),
                    evidence_refs=[f"project:{project.get('slug')}"],
                    recommended_actions=[
                        "Repair stale sessions or planner drift",
                        "Rerun reconciliation until session and planner auditors are clear",
                        "Advance only after control-plane blockers are removed",
                    ],
                )
                _wake_events[project_slug].clear()
                try:
                    await asyncio.wait_for(_wake_events[project_slug].wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue

        all_done = all(t["status"] in ["done", "cancelled"] for t in tasks)
        if all_done and tasks:
            closeout_auditor = auditors.get("closeout") or {}
            if closeout_auditor.get("status") == "blocked":
                if await _ensure_closeout_repair_task(project, tasks, auditors):
                    tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                    consecutive_idle_turns = 0
                    continue
                closeout_auditor = auditors.get("closeout") or {}
                blockers = closeout_auditor.get("blockers") or []
                await raise_decision_event(
                    project,
                    source="autopilot",
                    event_type="closeout_gate_blocked",
                    severity="needs_planner",
                    summary=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                    evidence_refs=[f"project:{project.get('slug')}"],
                    recommended_actions=[
                        "Repair closeout blockers",
                        "Refresh ontology or integrity state",
                        "Advance only after closeout gate passes",
                    ],
                )
                _update_config(
                    project_slug,
                    last_action="Waiting for closeout repair",
                    last_turn_result=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                )
                if not _active_autopilots.get(project_slug):
                    break
                _wake_events[project_slug].clear()
                try:
                    await asyncio.wait_for(_wake_events[project_slug].wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue
            else:
                logger.info("Autopilot: All tasks are completed. Project goal reached.")
                _update_config(
                    project_slug,
                    last_action="Completed",
                    last_turn_result="All planner tasks reached terminal status and closeout gate passed.",
                )
                await _mark_project_completed(project)
                break

        # 2. Check if a worker is already running before doing any new planning or launch work.
        _update_config(project_slug, last_action="Checking for active worker sessions...")
        poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
        if poll_result:
            if poll_result == "polled":
                consecutive_idle_turns = 0
            continue

        if await _launch_ready_tasks_if_available(project, tasks, auditors, project_slug):
            consecutive_idle_turns = 0
            continue

        # 3. Run the planner to see what it wants to do, unless a blocked auditor already has a ready repair task.
        if _should_skip_planner_for_ready_repair(tasks, auditors):
            _update_config(
                project_slug,
                last_action="Skipping planner turn for ready repair task",
                last_turn_result="Blocked auditor already has matching ready remediation work.",
            )
        else:
            _update_config(project_slug, last_action="Running Planner: Determining next task...")
            try:
                await planner_runtime.run_planner_turn(
                    project=project,
                    user_message=_planner_turn_message(auditors),
                    persist=False # Do not spam the chat thread
                )
                tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                _update_config(project_slug, last_turn_result="Planner turn completed.")
                logger.info("Planner turn complete.")
            except Exception as e:
                logger.error(f"Planner turn failed in autopilot: {e}")
                _update_config(project_slug, last_action="Idle (Recovering from error)", last_turn_result=f"Error: {e}")
                await asyncio.sleep(60)
                continue
            
        # 4. Check tasks on the board to see if we are actually making progress
        # If everything is 'done' or 'cancelled', we are finished
        all_done = all(t["status"] in ["done", "cancelled"] for t in tasks)
        if all_done and tasks:
            closeout_auditor = auditors.get("closeout") or {}
            if closeout_auditor.get("status") == "blocked":
                if await _ensure_closeout_repair_task(project, tasks, auditors):
                    tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                    consecutive_idle_turns = 0
                    continue
                closeout_auditor = auditors.get("closeout") or {}
                blockers = closeout_auditor.get("blockers") or []
                await raise_decision_event(
                    project,
                    source="autopilot",
                    event_type="closeout_gate_blocked",
                    severity="needs_planner",
                    summary=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                    evidence_refs=[f"project:{project.get('slug')}"],
                    recommended_actions=[
                        "Repair closeout blockers",
                        "Refresh ontology or integrity state",
                        "Advance only after closeout gate passes",
                    ],
                )
                _update_config(
                    project_slug,
                    last_action="Waiting for closeout repair",
                    last_turn_result=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                )
                if not _active_autopilots.get(project_slug):
                    break
                _wake_events[project_slug].clear()
                try:
                    await asyncio.wait_for(_wake_events[project_slug].wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue
            else:
                logger.info("Autopilot: All tasks are completed. Project goal reached.")
                _update_config(
                    project_slug,
                    last_action="Completed",
                    last_turn_result="All planner tasks reached terminal status and closeout gate passed.",
                )
                await _mark_project_completed(project)
                break

        task_by_id = {str(t["_id"]): t for t in tasks}

        if config.get("auto_approve") and not control_plane_gate.get("blocked"):
            promoted: list[str] = []
            approvals = await planner_service.list_approvals(project)
            for task in tasks:
                status = task.get("status")
                if status not in {"ready", "awaiting_approval", "backlog", "blocked"}:
                    continue
                if status == "ready" and task.get("approvalState") != "pending":
                    continue
                if status == "blocked" and task.get("blockerCategory") == "publish_failure":
                    continue
                if not _dependencies_satisfied(task, task_by_id):
                    continue
                promotion_view = {
                    "_id": task.get("_id"),
                    "title": task.get("title"),
                    "status": "ready",
                    "agentRole": task.get("agentRole") or task.get("agent_role"),
                    "agent_role": task.get("agent_role") or task.get("agentRole"),
                    "priority": task.get("priority"),
                }
                if not _task_allowed_for_auditors(promotion_view, auditors):
                    continue
                if task.get("approvalState") == "pending":
                    task_id = str(task["_id"])
                    pending_approval = next(
                        (
                            item
                            for item in approvals
                            if item.get("taskId") == task_id and item.get("status") == "pending"
                        ),
                        None,
                    )
                    if pending_approval is None:
                        approval_id = await planner_service.create_approval(
                            project=project,
                            task_id=task_id,
                            agent_session_id=None,
                            approval_type="run_task",
                            status="pending",
                            requested_by_role="planner",
                        )
                    else:
                        approval_id = pending_approval["_id"]
                    await planner_service.resolve_approval(
                        project=project,
                        approval_id=approval_id,
                        status="granted",
                        granted_by_user_id="autopilot",
                        resolution_note="Auto-approved by Autopilot because dependencies are satisfied.",
                    )
                await planner_service.update_task(
                    str(task["_id"]),
                    project=project,
                    status="ready",
                    runner=task.get("runner") or "cursor_cli",
                    approval_state="granted",
                    latestRunSummary="Promoted by Autopilot because dependencies are satisfied.",
                )
                promoted.append(str(task["_id"]))
            if promoted:
                logger.info("Autopilot: Promoted task(s): %s", ", ".join(promoted))
                await planner_service.sync_planner_files(project, board)
                for event in await list_decision_events(project, status="open"):
                    if event.type == "no_ready_tasks":
                        await mark_decision_event(project, event._id, "handled")
                tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                consecutive_idle_turns = 0

        cancelled_with_dependents = [
            t for t in tasks
            if t.get("status") == "cancelled"
            and any(t["_id"] in (candidate.get("dependsOnTaskIds") or []) for candidate in tasks)
        ]
        if cancelled_with_dependents:
            event = await raise_decision_event(
                project,
                source="autopilot",
                event_type="task_cancelled_with_dependents",
                severity="needs_planner",
                summary=(
                    "A cancelled task is still required by downstream work: "
                    + ", ".join(t["_id"] for t in cancelled_with_dependents[:5])
                    + ". Decide whether to requeue it, replace it, or change downstream dependencies."
                ),
                evidence_refs=[f"task:{t['_id']}" for t in cancelled_with_dependents[:5]],
                recommended_actions=[
                    "Requeue required cancelled task",
                    "Create replacement task",
                    "Ask user whether to skip dependency",
                ],
            )
            if config.get("auto_approve"):
                requeued: list[str] = []
                for task in cancelled_with_dependents:
                    requeue_view = {
                        "_id": task.get("_id"),
                        "title": task.get("title"),
                        "status": "ready",
                        "agentRole": task.get("agentRole") or task.get("agent_role"),
                        "agent_role": task.get("agent_role") or task.get("agentRole"),
                        "priority": task.get("priority"),
                    }
                    if not _task_allowed_for_auditors(requeue_view, auditors):
                        continue
                    await planner_service.update_task(
                        str(task["_id"]),
                        project=project,
                        status="ready",
                        runner=task.get("runner") or "cursor_cli",
                        approval_state="granted",
                        latestRunSummary="Requeued by Autopilot because downstream tasks still depend on it.",
                    )
                    requeued.append(str(task["_id"]))
                if requeued:
                    await mark_decision_event(project, event._id, "handled")
                    await planner_service.sync_planner_files(project, board)
                    tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                    consecutive_idle_turns = 0

        poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
        if poll_result:
            if poll_result == "polled":
                consecutive_idle_turns = 0
            continue
            
        # Check if we have ready tasks that became available after planner/promotion/requeue work.
        if await _launch_ready_tasks_if_available(project, tasks, auditors, project_slug):
            consecutive_idle_turns = 0
            continue

        ready_tasks = [t for t in tasks if t["status"] == "ready" and t.get("approvalState") != "pending"]
        ready_tasks = _filter_ready_tasks_for_auditors(ready_tasks, auditors)
        if not ready_tasks:
            consecutive_idle_turns += 1
            logger.info(f"Autopilot: No ready tasks. Idle turns: {consecutive_idle_turns}")
            unfinished = [t for t in tasks if t.get("status") not in {"done", "cancelled"}]
            if unfinished:
                await raise_decision_event(
                    project,
                    source="autopilot",
                    event_type="no_ready_tasks",
                    severity="needs_planner",
                    summary=(
                        f"No ready tasks are available, but {len(unfinished)} unfinished task(s) remain. "
                        "Decide whether dependencies are satisfied, tasks should be promoted, or the user is needed."
                    ),
                    evidence_refs=[f"task:{t['_id']}" for t in unfinished[:8]],
                    recommended_actions=[
                        "Promote dependency-satisfied backlog tasks",
                        "Create missing prerequisite task",
                        "Ask user for project direction",
                    ],
                )
            if consecutive_idle_turns >= 3:
                logger.info("Autopilot: Stalled or finished (3 consecutive idle turns). Stopping.")
                break
            # Give the planner a chance to think/refine, or wait for a wake-up event
            _wake_events[project_slug].clear()
            try:
                await asyncio.wait_for(_wake_events[project_slug].wait(), timeout=60.0)
                logger.info(f"Autopilot: Waking up due to event for {project_slug}")
            except asyncio.TimeoutError:
                pass
        else:
            consecutive_idle_turns = 0
            # If the planner didn't launch it, we'll try to nudge it again next iteration
            await asyncio.sleep(2)

    logger.info(f"Autopilot loop finished for {project_slug}")
    _active_autopilots[project_slug] = False

def is_autopilot_active(project_slug: str) -> bool:
    return _active_autopilots.get(project_slug, False)

def get_autopilot_config(project_slug: str) -> dict[str, Any]:
    return _autopilot_configs.get(project_slug, {})
