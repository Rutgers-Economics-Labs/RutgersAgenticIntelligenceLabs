from __future__ import annotations

import asyncio
import logging
import time
import json
from pathlib import Path
from typing import Any

from app.services import planner_runtime, planner_service, running_agent_service
from app.services import goal_service
from app.runners import session_lifecycle
from app.services.audit_service import audit_gate_status
from app.services.convex_client import convex
from app.services.decision_service import list_decision_events, mark_decision_event, raise_decision_event
from app.services.hydration_registry_service import get_hydration_status
from app.services.integrity_service import evaluate_integrity_gate, summarize_agent_workflow_health
from app.services.auditor_service import build_auditor_statuses
from app.services import command_center_service
from app.services.reconciliation_service import (
    project_reality_status,
    ensure_execution_lane_available,
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
        "title": "Populate ontology pipeline steps for project sources",
        "match": ("populate", "pipeline", "source"),
        "status": "ready",
        "agent_role": "data",
        "repo_paths": [".ontology/pipelines", ".ontology/sources", ".ontology/transforms", "research_plan", "topics"],
        "acceptance_criteria": [
            "the default ontology pipeline declares concrete hydration steps for at least one project-relevant source",
            "each step names a real source config and any required transform or parameterization",
            "at least one source actually fetches data (via api, url, or remote handler) rather than registering a local metadata stub as its source — a source whose only data is a single-row catalog CSV does not count",
            "pipeline notes distinguish immediately ingestable sources from manual-ingest-only sources",
            "do not introduce unrelated cross-project harnesses, placeholder datasets, smoke-test fixtures, or out-of-domain fallback sources just to satisfy hydration",
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


def _wake_event(project_slug: str) -> asyncio.Event:
    event = _wake_events.get(project_slug)
    if event is None:
        event = asyncio.Event()
        _wake_events[project_slug] = event
    return event

def _update_config(project_slug: str, **kwargs):
    if project_slug not in _autopilot_configs:
        _autopilot_configs[project_slug] = {}
    _autopilot_configs[project_slug].update(kwargs)


def _desired_autopilot_enabled(project_slug: str) -> bool:
    return bool(_autopilot_configs.get(project_slug, {}).get("desired_enabled"))


def _goal_mode_enabled(project: dict[str, Any]) -> bool:
    try:
        return bool(goal_service.load_goal_bundle(project))
    except Exception:
        return False


def _record_goal_gate_failure(
    project: dict[str, Any],
    *,
    failure_class: str,
    summary: str,
    root_cause_hypothesis: str,
    reusable_lesson: str,
    next_repair_action: str,
    retry_eligible: bool = True,
) -> None:
    if not _goal_mode_enabled(project):
        return
    goal_service.record_failure(
        project,
        failure_class=failure_class,
        summary=summary,
        root_cause_hypothesis=root_cause_hypothesis,
        reusable_lesson=reusable_lesson,
        next_repair_action=next_repair_action,
        retry_eligible=retry_eligible,
        phase_override="blocked",
    )


async def _persist_autopilot_state(project_slug: str, *, enabled: bool, auto_approve: bool | None = None) -> None:
    try:
        project = await planner_service.get_project_by_slug(project_slug)
    except Exception as exc:
        logger.warning("Failed to load project %s while persisting autopilot state: %s", project_slug, exc)
        return
    local_repo_path = str(project.get("localRepoPath") or "").strip()
    if not local_repo_path:
        return
    try:
        repo_root = Path(local_repo_path).resolve()
        state_path = repo_root / ".rail" / "autopilot_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"enabled": enabled}
        if auto_approve is not None:
            payload["autoApprove"] = auto_approve
        state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to persist autopilot state for %s: %s", project_slug, exc)


async def _disable_autopilot_desired_state(project_slug: str, *, auto_approve: bool | None = None) -> None:
    _update_config(project_slug, desired_enabled=False)
    await _persist_autopilot_state(project_slug, enabled=False, auto_approve=auto_approve)


async def ensure_autopilot_running(project_slug: str) -> dict[str, Any]:
    """Revive a desired autopilot loop if the process forgot it or it exited."""
    desired_enabled = _desired_autopilot_enabled(project_slug)
    auto_approve = bool(_autopilot_configs.get(project_slug, {}).get("auto_approve", False))
    try:
        project = await planner_service.get_project_by_slug(project_slug)
    except Exception as exc:
        logger.warning("Unable to inspect autopilot desired state for %s: %s", project_slug, exc)
        return {
            "desired_enabled": desired_enabled,
            "auto_approve": auto_approve,
            "active": is_autopilot_active(project_slug),
        }
    local_repo_path = str(project.get("localRepoPath") or "").strip()
    if local_repo_path:
        try:
            payload = json.loads(
                (Path(local_repo_path).resolve() / ".rail" / "autopilot_state.json").read_text(encoding="utf-8")
            )
            if isinstance(payload, dict):
                desired_enabled = bool(payload.get("enabled", desired_enabled))
                auto_approve = bool(payload.get("autoApprove", auto_approve))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("Failed to read persisted autopilot state for %s: %s", project_slug, exc)
    desired_enabled = bool(project.get("autopilotEnabled", desired_enabled))
    auto_approve = bool(project.get("autopilotAutoApprove", auto_approve))
    _update_config(project_slug, desired_enabled=desired_enabled, auto_approve=auto_approve)
    active = is_autopilot_active(project_slug)
    if desired_enabled and not active:
        logger.info("Reviving desired autopilot loop for %s", project_slug)
        asyncio.create_task(start_autopilot(project_slug, auto_approve))
    return {
        "desired_enabled": desired_enabled,
        "auto_approve": auto_approve,
        "active": active,
    }


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


def _is_ontology_data_bootstrap_phase(
    project: dict[str, Any],
    *,
    hydration: dict[str, Any] | None = None,
) -> bool:
    """True when ontology projects still need more source/data work before health-heavy repair loops.

    Early ontology phases should favor data ingestion, pipeline population, and hydration over
    deterministic health verification. This keeps autopilot from over-triggering health agents
    before the ontology contains enough real project-scoped data to validate meaningfully.
    """
    if not _is_ontology_project(project):
        return False

    state = str((hydration or {}).get("state") or "").strip().lower()
    if state and state not in ONTOLOGY_READY_STATES:
        return True
    if not _pipeline_has_steps(project):
        return True

    duckdb_path = _hydration_duckdb_path(hydration or {})
    ontology_has_rows = _duckdb_has_populated_rows(duckdb_path) or _ontology_has_populated_rows(project)
    return not ontology_has_rows


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
    """Delegate to the shared parser so autopilot and auditor agree on classifications.

    Note: the shared parser normalizes legacy classification aliases
    (e.g. `answerable_after_expansion` → `requires_expansion`). Inlining the
    parse previously silently dropped those aliases, so autopilot never
    auto-created the expansion task for them.
    """
    from app.services.question_expansion_service import parse_follow_up_questions

    root = project.get("localRepoPath")
    if not root:
        return []
    return parse_follow_up_questions(Path(str(root)).resolve())


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
    bootstrap_phase = _is_ontology_data_bootstrap_phase(project, hydration=hydration)
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
        if bootstrap_phase and spec["match"] not in {
            ("populate", "pipeline", "source"),
            ("hydrate", "ontology", "artifact"),
        }:
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
            "Autopilot: ensured ontology lifecycle tasks for %s (state=%s, pipeline_has_steps=%s, ontology_has_rows=%s, bootstrap_phase=%s)",
            project.get("slug"),
            state,
            pipeline_has_steps,
            ontology_has_rows,
            bootstrap_phase,
        )
    return changed


async def _ensure_ontology_expansion_tasks(project: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    if not _is_ontology_project(project):
        return False
    questions = _parse_ontology_follow_up_questions(project)
    if not questions:
        return False

    from app.services.question_expansion_service import expansion_task_specs_for_question

    board = await planner_service.ensure_main_board(project)
    changed = False
    live_titles = {str(task.get("title") or "") for task in tasks}

    for question in questions:
        classification = str(question.get("classification") or "").strip().lower()
        title = str(question.get("title") or "").strip()
        if not title:
            continue
        for spec in expansion_task_specs_for_question(title, classification):
            if spec["title"] in live_titles:
                continue
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=spec["title"],
                description=spec["description"],
                status=spec["status"],
                agent_role=spec["agent_role"],
                repo_paths=spec["repo_paths"],
                acceptance_criteria=spec["acceptance_criteria"],
                runner=spec["runner"],
            )
            live_titles.add(spec["title"])
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
    hydration: dict[str, Any] | None = None
    try:
        hydration = await get_hydration_status(project=project) if _is_ontology_project(project) else None
    except Exception:
        hydration = None
    bootstrap_phase = _is_ontology_data_bootstrap_phase(project, hydration=hydration)
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

    if missing_evidence_claims and not bootstrap_phase:
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

    if stale_sources and not bootstrap_phase:
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

    if failed_verification_runs and not bootstrap_phase:
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

    if reproducibility_gaps and not bootstrap_phase:
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
    if inadmissible_sources and not bootstrap_phase and task_title not in live_titles:
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
            "Autopilot: ensured integrity repair tasks for %s (bootstrap_phase=%s, dataset_provenance=%s, dataset_freshness=%s, analysis_lineage=%s, analysis_verification_commands=%s, analysis_verification_runs=%s, claims=%s, stale_sources=%s, failed_verification_runs=%s, reproducibility_gaps=%s, inadmissible_sources=%s)",
            project.get("slug"),
            bootstrap_phase,
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
    existing_task = next(
        (
            task
            for task in tasks
            if str(task.get("title") or "") == task_title
            and str(task.get("status") or "") != "cancelled"
        ),
        None,
    )
    board = await planner_service.ensure_main_board(project)
    if existing_task is not None:
        existing_status = str(existing_task.get("status") or "")
        if existing_status in {"ready", "running", "awaiting_approval"}:
            return False
        await planner_service.update_task(
            str(existing_task["_id"]),
            project=project,
            status="ready",
            blockerCategory=None,
            approvalState="granted",
            latestRunSummary="Reopened by Autopilot because ontology readiness is still blocked.",
        )
        await planner_service.sync_planner_files(project, board)
        logger.info("Autopilot: reopened ontology repair task for %s", project.get("slug"))
        return True

    await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=task_title,
        description=(
            "Repair ontology blockers that still prevent ontology-backed work. "
            "This includes hydration failures, empty artifacts, broken active pointers, or missing ontology-health verification. "
            "Keep the repair strictly within this project's domain and source inventory: do not introduce cross-project smoke tests, "
            "unrelated fallback datasets, or placeholder harnesses simply to make hydration appear non-empty."
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
        # Reality-based reconciliation: the ontology auditor has already
        # certified the project is hydrated with populated rows. Bypass the
        # worker-completion audit gate so prior tasks describing this work
        # can be reconciled to done without a synthetic post-run audit.
        await planner_service.update_task(
            str(task["_id"]),
            project=project,
            audited_reality_bypass=True,
            **fields,
        )
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
                        "Superseded by a successful hydration rerun: the active ontology pipeline now produces populated rows."
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
    hypothesis_boost = -int(task.get("_hypothesisPriorityBoost") or 0)
    return (boost + hypothesis_boost, weight, str(task.get("_id") or ""))


def _has_ready_task_title(tasks: list[dict[str, Any]], title: str) -> bool:
    for task in tasks:
        if str(task.get("title") or "") != title:
            continue
        if str(task.get("status") or "") not in {"ready", "running"}:
            continue
        return True
    return False


def _should_skip_planner_for_ready_repair(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> bool:
    """Skip a planner turn only when a matching repair task is ready to dispatch.

    Under background-health-governance, `_filter_ready_tasks_for_auditors`
    keeps research/data/coding tasks alongside repair tasks when ontology or
    integrity is blocked. Skipping the planner whenever *any* filtered task is
    ready would skip planner on regular research, which is wrong — we only
    want to skip when there's a concrete repair task ready that the planner
    would otherwise just re-plan around.
    """
    auditors = auditors or {}
    ready_tasks = [
        task for task in tasks
        if str(task.get("status") or "") == "ready" and task.get("approvalState") != "pending"
    ]
    if (auditors.get("ontology") or {}).get("status") == "blocked" and any(
        _task_matches_ontology_repair_work(task) for task in ready_tasks
    ):
        return True
    if (auditors.get("integrity") or {}).get("status") == "blocked" and any(
        _task_matches_integrity_repair_work(task) for task in ready_tasks
    ):
        return True
    if (auditors.get("closeout") or {}).get("status") == "blocked" and _has_ready_task_title(tasks, "Resolve closeout blockers"):
        return True
    if _control_plane_auditor_gate(auditors).get("blocked") and _has_ready_task_title(tasks, "Reconcile control-plane drift and stale sessions"):
        return True
    return False


def _apply_auditor_priority_boosts(
    project: dict[str, Any],
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
    if not project.get("localRepoPath"):
        return boosted
    ranked_hypotheses = command_center_service.rank_hypotheses(project)
    ranking_by_id = {str(item.get("id")): item for item in ranked_hypotheses}
    hypothesis_path = Path(str(project.get("localRepoPath") or "")) / "research_plan" / "state" / "hypotheses.json"
    task_links: dict[str, list[str]] = {}
    if hypothesis_path.exists():
        try:
            payload = json.loads(hypothesis_path.read_text(encoding="utf-8"))
        except Exception:
            payload = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                hypothesis_id = str(item.get("id") or item.get("hypothesis_id") or "").strip()
                if not hypothesis_id:
                    continue
                for task_id in item.get("task_ids") or []:
                    task_key = str(task_id).strip()
                    if task_key:
                        task_links.setdefault(task_key, []).append(hypothesis_id)
    for task in boosted:
        task_id = str(task.get("_id") or "")
        linked_ids = task_links.get(task_id, [])
        if not linked_ids:
            continue
        best = max(
            (ranking_by_id.get(item) for item in linked_ids if ranking_by_id.get(item)),
            key=lambda x: float(x.get("computedScore") or 0),
            default=None,
        )
        if best is None:
            continue
        task["_hypothesisPriorityBoost"] = int(round(float(best.get("computedScore") or 0) * 100))
    return boosted


def _task_matches_ontology_repair_work(task: dict[str, Any]) -> bool:
    title = str(task.get("title") or "").strip().lower()
    role = str(task.get("agentRole") or task.get("agent_role") or "").strip().lower()
    if title == "repair ontology readiness blockers":
        return True
    if title in {
        "populate ontology pipeline steps for attachable sources",  # legacy title; match for old projects
        "populate ontology pipeline steps for project sources",
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


def _task_matches_bootstrap_data_work(task: dict[str, Any]) -> bool:
    title = str(task.get("title") or "").strip().lower()
    role = str(task.get("agentRole") or task.get("agent_role") or "").strip().lower()
    if role != "data":
        return False
    return title in {
        "repair ontology readiness blockers",
        "populate ontology pipeline steps for attachable sources",  # legacy title; match for old projects
        "populate ontology pipeline steps for project sources",
        "hydrate project ontology and register active artifacts",
        "repair dataset provenance and freshness metadata",
    }


def _is_audit_repair_task(task: dict[str, Any]) -> bool:
    """True if the task is a platform-maintenance or audit-repair task."""
    title = str(task.get("title") or "").lower()
    return any(needle in title for needle in ["reconcile control-plane", "audit", "integrity repair", "ontology health"])

def _is_promotion_role(task: dict[str, Any]) -> bool:
    """Roles whose output is a trust-boundary action and must respect
    promotion-blocking auditors (ontology/integrity/closeout)."""
    role = str(task.get("agentRole") or task.get("agent_role") or "").strip().lower()
    return role == "artifact"


def _filter_ready_tasks_for_auditors(
    project: dict[str, Any],
    ready_tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Decide which ready tasks autopilot may dispatch this tick.

    Background-health-governance: ontology/integrity audit findings must not
    starve research, data, or coding work. They only deprioritize it (via
    `_apply_auditor_priority_boosts`) and gate promotion-class tasks
    (currently `artifact`-role meta-synthesis / closeout).

    Hard control-plane problems (session/planner auditors blocked) still
    suspend everything except the explicit control-plane repair task —
    those represent runtime safety issues, not learning blockers.
    """
    if not ready_tasks:
        return []
    filtered = _apply_auditor_priority_boosts(project, ready_tasks, auditors)
    if _control_plane_auditor_gate(auditors).get("blocked"):
        # Session/planner auditors flag runtime-safety issues (zombie sessions,
        # drift). Holding off other work until the repair task lands prevents
        # double-spawning on stale state.
        return [
            task for task in filtered
            if str(task.get("title") or "") == "Reconcile control-plane drift and stale sessions"
        ]

    ontology_auditor = (auditors or {}).get("ontology") or {}
    integrity_auditor = (auditors or {}).get("integrity") or {}
    promotion_blocked = (
        ontology_auditor.get("status") == "blocked"
        or integrity_auditor.get("status") == "blocked"
    )
    if not promotion_blocked:
        return filtered

    # Promotion-class tasks (final artifact synthesis, closeout) must wait for
    # ontology + integrity to clear. Everything else — including draft
    # research, data ingestion, and coding work — is allowed to keep running.
    return [task for task in filtered if not _is_promotion_role(task)]


def _task_allowed_for_auditors(
    project: dict[str, Any],
    task: dict[str, Any],
    auditors: dict[str, Any] | None,
) -> bool:
    return bool(_filter_ready_tasks_for_auditors(project, [task], auditors))


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
    existing_task = next(
        (
            task
            for task in tasks
            if str(task.get("title") or "") == task_title
            and str(task.get("status") or "") != "cancelled"
        ),
        None,
    )
    if existing_task is not None:
        existing_status = str(existing_task.get("status") or "")
        if existing_status in {"ready", "running", "awaiting_approval"}:
            return False
        await planner_service.update_task(
            str(existing_task["_id"]),
            project=project,
            status="ready",
            blockerCategory=None,
            approvalState="granted",
            latestRunSummary="Reopened by Autopilot because control-plane auditors remain blocked.",
        )
        await planner_service.sync_planner_files(project, board)
        logger.info("Autopilot: reopened control-plane repair task for %s", project.get("slug"))
        return True

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


async def cancel_stale_repair_tasks(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
) -> int:
    """Cancel autopilot repair tasks whose underlying auditor is already ready."""
    project_root = Path(str(project.get("localRepoPath") or "")).resolve()
    stale_titles_by_auditor = {
        "ontology": [
            "Populate ontology pipeline steps for project sources",
            "Populate ontology pipeline steps for attachable sources",  # legacy title; cancel for old projects
            "Verify hydrated ontology health before research",
        ],
        "integrity": [
            "Repair dataset provenance and freshness metadata",
        ],
    }
    research_followup_titles = {
        "Launch ontology-backed research after hydration",
        "Propose ontology-answerable follow-up questions",
    }
    research_exists = (
        any(project_root.joinpath("artifacts").glob("*.md"))
        if project_root.joinpath("artifacts").is_dir()
        else False
    )

    titles_to_cancel: set[str] = set()
    for auditor_key, titles in stale_titles_by_auditor.items():
        if (auditors or {}).get(auditor_key, {}).get("status") == "ready":
            titles_to_cancel.update(titles)
    control_plane_titles = {"Reconcile control-plane drift and stale sessions"}
    if (
        (auditors or {}).get("session", {}).get("status") == "ready"
        and (auditors or {}).get("planner", {}).get("status") == "ready"
    ):
        titles_to_cancel.update(control_plane_titles)
    if research_exists and (auditors or {}).get("ontology", {}).get("status") == "ready":
        titles_to_cancel.update(research_followup_titles)

    if not titles_to_cancel:
        return 0

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
                "Superseded: the corresponding auditor is now `ready` so this "
                "repair task is no longer needed. Cancelled by autopilot."
            ),
            audited_reality_bypass=True,
        )
        cancelled += 1
    if cancelled:
        board = await planner_service.ensure_main_board(project)
        await planner_service.sync_planner_files(project, board)
    return cancelled


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
    last_result: dict[str, Any] | None = None
    for candidate in sorted(ready_tasks, key=_task_priority):
        try:
            result = await planner_runtime._execute_planner_tool(
                project,
                "launch_task_runner",
                {"task_id": str(candidate["_id"])},
            )
        except Exception as exc:
            result = {
                "error": str(exc),
                "taskId": str(candidate["_id"]),
            }
        last_result = result
        if result and not result.get("error"):
            return result
    return last_result


# ---------------------------------------------------------------------------
# Stuck detection / anti-stall mechanics
# ---------------------------------------------------------------------------
# Prevents repeated audit/repair cycles from consuming the entire autopilot
# run budget.  The invariant from the spec:
#
#   Every run must either produce research progress, downgrade scope, or emit
#   a typed blocker with a bounded next action.  It should never silently
#   relaunch the same kind of repair forever.
#
# Implementation:
# - We hash each blocked task's (task_id, blocker_category) pair so identical
#   blocked states are recognised across iterations.
# - After STUCK_RUN_BUDGET consecutive blocked/needs_changes runs we write a
#   stuck report and mark the task blocked with blocker_category="stuck_loop"
#   so the planner can decide what to do (cancel, downgrade, or ask user).
# - The stuck report is written to research_plan/stuck_reports/<task_id>.json.

STUCK_RUN_BUDGET: int = 3  # max consecutive identical blocked runs before flagging

# In-memory counter: task_id → (action_hash, consecutive_count)
_task_stuck_counters: dict[str, tuple[str, int]] = {}


def _compute_task_action_hash(task: dict[str, Any]) -> str:
    """Stable hash of the task's stuck state for repeated-run detection.

    Uses task_id + status + blockerCategory so that changing either resets
    the counter.  We deliberately do NOT hash the full latestRunSummary
    because that changes on every run even when the underlying problem is
    the same.
    """
    import hashlib
    key = "|".join([
        str(task.get("_id") or ""),
        str(task.get("status") or ""),
        str(task.get("blockerCategory") or ""),
    ])
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:12]


def _write_stuck_report(project_root: Path, task: dict[str, Any], consecutive_count: int) -> None:
    """Write a stuck-loop report to research_plan/stuck_reports/<task_id>.json."""
    import datetime
    try:
        stuck_dir = project_root / "research_plan" / "stuck_reports"
        stuck_dir.mkdir(parents=True, exist_ok=True)
        task_id = str(task.get("_id") or "unknown")
        report = {
            "task_id": task_id,
            "title": task.get("title") or "",
            "role": task.get("agentRole") or task.get("agent_role") or "",
            "status": task.get("status") or "",
            "blocker_category": task.get("blockerCategory") or "",
            "latest_run_summary": task.get("latestRunSummary") or "",
            "consecutive_blocked_runs": consecutive_count,
            "recorded_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "") + "Z",
            "recommended_actions": [
                "Downgrade task scope (e.g. mark as candidate instead of draft)",
                "Cancel this repair task and create a more targeted replacement",
                "Ask the operator whether to continue or abandon",
            ],
        }
        report_path = stuck_dir / f"{task_id}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.info(
            "Autopilot: wrote stuck report for task %s after %d consecutive blocked runs",
            task_id, consecutive_count,
        )
    except Exception as exc:
        logger.warning("Autopilot: failed to write stuck report for task %s: %s", task.get("_id"), exc)


async def _detect_and_handle_stuck_tasks(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> bool:
    """Scan tasks for stuck loops and flag them before launching anything.

    A task is stuck when it has been in a blocked/needs_changes state with
    the same blocker_category for STUCK_RUN_BUDGET or more consecutive
    autopilot iterations.

    Returns True if any task was flagged (so the caller can reload tasks).
    """
    project_root_str = project.get("localRepoPath") or ""
    project_root = Path(project_root_str).resolve() if project_root_str else None

    flagged = False

    # Track B: Project-level stuck detection
    from app.services import stuck_detector
    if project_root:
        diagnosis = stuck_detector.detect_stuck_state(project_root)
        if diagnosis:
            stuck_detector.write_stuck_report(project_root, diagnosis)
            logger.warning("Autopilot: Project-level stuck state detected for %s", project.get("slug"))
            
            # Track B: Automated escape
            for issue in diagnosis["issues"]:
                if issue["type"] in {"maintenance_loop", "no_domain_progress", "no_progress_edges"}:
                    # Try to break the cycle by creating an MVR task
                    if not _has_ready_task_title(tasks, "MVR:"):
                        await planner_runtime._execute_planner_tool(
                            project,
                            "create_mvr_task",
                            {
                                "focus_source": "primary project source", # Fallback
                                "reason": f"Automated escape from {issue['type']} loop."
                            }
                        )
                        flagged = True
                        break

    for task in tasks:

        task_id = str(task.get("_id") or "")
        if not task_id:
            continue
        status = str(task.get("status") or "")
        if status not in {"blocked", "needs_changes"}:
            # Task advanced — reset the counter
            if task_id in _task_stuck_counters:
                del _task_stuck_counters[task_id]
            continue

        action_hash = _compute_task_action_hash(task)
        prev_hash, count = _task_stuck_counters.get(task_id, ("", 0))
        if prev_hash == action_hash:
            count += 1
        else:
            count = 1
        _task_stuck_counters[task_id] = (action_hash, count)

        if count < STUCK_RUN_BUDGET:
            continue

        # Task is stuck — write a report and flag it so the planner must decide.
        logger.warning(
            "Autopilot: task %s (%s) is stuck after %d consecutive blocked runs; flagging.",
            task_id,
            task.get("title") or "",
            count,
        )
        if project_root and project_root.exists():
            _write_stuck_report(project_root, task, count)
        try:
            await planner_service.update_task(
                task_id,
                project=project,
                status="blocked",
                blockerCategory="stuck_loop",
                latestRunSummary=(
                    f"Stuck loop detected: task has been in a blocked/needs_changes state "
                    f"for {count} consecutive autopilot iterations with the same blocker "
                    f"({task.get('blockerCategory') or 'unknown'}). "
                    "A stuck report has been written to research_plan/stuck_reports/. "
                    "The planner must decide whether to cancel, downgrade scope, or retry with a narrower task."
                ),
            )
        except Exception as exc:
            logger.warning("Autopilot: failed to flag stuck task %s: %s", task_id, exc)
        # Reset counter so we don't re-flag on the very next iteration
        _task_stuck_counters[task_id] = (action_hash, 0)
        flagged = True

    return flagged


async def _launch_ready_tasks_if_available(
    project: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any] | None,
    project_slug: str,
) -> bool:
    lane_state = await ensure_execution_lane_available(project)
    if not lane_state.get("available"):
        logger.info(
            "Autopilot: execution lane blocked for %s: %s",
            project_slug,
            lane_state.get("reason"),
        )
        return False

    ready_tasks = [t for t in tasks if t["status"] == "ready" and t.get("approvalState") != "pending"]
    ready_tasks = _filter_ready_tasks_for_auditors(project, ready_tasks, auditors)
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
        if _goal_mode_enabled(project):
            goal_service.record_human_decision(
                project,
                decision_kind="scope_decision",
                blocked=f"Worker session {session_id} is awaiting input.",
                autonomy_limit="Autonomy cannot continue because the worker needs a concrete answer or reroute decision.",
                decision_needed="Choose whether to answer, reroute, cancel, or ask the user.",
                next_step_after_decision="Autopilot will resume the worker or replan once the decision is recorded.",
            )
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
    from app.services import kill_switch_service

    if kill_switch_service.is_killed(project_slug):
        logger.warning(
            "Autopilot refused to start for %s: kill switch engaged. "
            "Release via POST /api/v1/autopilot/release-all or /projects/%s/autopilot/release.",
            project_slug, project_slug,
        )
        return

    _update_config(project_slug, auto_approve=auto_approve, desired_enabled=True)
    await _persist_autopilot_state(project_slug, enabled=True, auto_approve=auto_approve)

    if _active_autopilots.get(project_slug):
        logger.info(f"Autopilot already running for {project_slug}")
        return

    _wake_event(project_slug)
    _active_autopilots[project_slug] = True
    try:
        while _desired_autopilot_enabled(project_slug):
            try:
                await run_autopilot_loop(project_slug, max_iterations=None)
            except Exception as exc:
                logger.exception("Autopilot loop crashed for %s: %s", project_slug, exc)
                _update_config(
                    project_slug,
                    last_action="Recovering from autopilot crash",
                    last_turn_result=str(exc),
                )
            if not _desired_autopilot_enabled(project_slug):
                break
            try:
                project = await planner_service.get_project_by_slug(project_slug)
            except Exception as exc:
                logger.warning("Failed to reload project %s after autopilot loop exit: %s", project_slug, exc)
                await asyncio.sleep(5)
                continue
            if str(project.get("status") or "").strip().lower() in {"completed", "closed"}:
                await _disable_autopilot_desired_state(project_slug, auto_approve=auto_approve)
                break
            _update_config(
                project_slug,
                last_action="Restarting autopilot loop",
                last_turn_result="Loop exited before project completion; restarting because autopilot is still desired.",
            )
            await asyncio.sleep(1)
    finally:
        _active_autopilots[project_slug] = False
        if not _desired_autopilot_enabled(project_slug):
            _wake_events.pop(project_slug, None)

async def stop_autopilot(project_slug: str):
    """
    Stops the autopilot loop for a project.
    """
    auto_approve = bool(_autopilot_configs.get(project_slug, {}).get("auto_approve", False))
    await _disable_autopilot_desired_state(project_slug, auto_approve=auto_approve)
    _active_autopilots[project_slug] = False
    trigger_wake(project_slug)

async def run_autopilot_loop(project_slug: str, *, max_iterations: int | None = 40):
    """
    God Mode: Continuously run the planner and agents until the project is done.
    """
    logger.info(f"Starting Autopilot God Mode for project: {project_slug}")
    # Ensure the wake event exists when callers (CLI scripts, autopilot tick)
    # enter via run_autopilot_loop directly without going through start_autopilot.
    if project_slug not in _wake_events:
        _wake_events[project_slug] = asyncio.Event()

    project = await planner_service.get_project_by_slug(project_slug)
    goal_mode = _goal_mode_enabled(project)
    consecutive_idle_turns = 0
    
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        if not _active_autopilots.get(project_slug):
            logger.info(f"Autopilot stopped for {project_slug}")
            break
        # Kill switch check — file-backed, checked every iteration so a kill
        # engaged from another API process or via direct file write still wins.
        from app.services import kill_switch_service
        if kill_switch_service.is_killed(project_slug):
            logger.warning("Autopilot loop exiting for %s: kill switch engaged.", project_slug)
            _active_autopilots[project_slug] = False
            break
            
        limit_display = "infinite" if max_iterations is None else str(max_iterations)
        logger.info("Autopilot iteration %s/%s for %s", iteration, limit_display, project_slug)
        project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
        if project_root and project_root.exists() and (project_root / "rail.yaml").is_file():
            try:
                planner_service.load_validated_manifest(project)
            except Exception as exc:
                logger.warning("Autopilot: manifest validation failed for %s: %s", project_slug, exc)
                if goal_mode:
                    goal_service.record_failure(
                        project,
                        failure_class="setup_failure",
                        summary=f"Manifest validation failed: {exc}",
                        root_cause_hypothesis="Project manifest or repo bootstrap is invalid, so goal mode cannot safely start.",
                        reusable_lesson="Do not begin goal execution until repo bootstrap and manifest validation are green.",
                        next_repair_action="Repair rail.yaml or bootstrap metadata, then rerun goal preflight.",
                        retry_eligible=False,
                        phase_override="blocked",
                    )
                    await _disable_autopilot_desired_state(
                        project_slug,
                        auto_approve=bool(_autopilot_configs.get(project_slug, {}).get("auto_approve", False)),
                    )
                    break
                _update_config(
                    project_slug,
                    last_action="Blocked: invalid project manifest",
                    last_turn_result=str(exc),
                )
                await asyncio.sleep(60)
                continue
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
            _record_goal_gate_failure(
                project,
                failure_class="audit_drift",
                summary=str(audit_gate.get("reason") or "Audit gate blocked autopilot."),
                root_cause_hypothesis="Post-run audit truth is stale or missing, so the control plane cannot safely advance.",
                reusable_lesson="Do not continue research execution while audit truth is stale; repair the control plane first.",
                next_repair_action="Finalize or rebuild post-run audits and reconcile session truth before continuing.",
            )
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
            _wake_event(project_slug).clear()
            try:
                await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
            continue
        
        config = _autopilot_configs.get(project_slug, {})

        board = await planner_service.ensure_main_board(project)
        tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
        
        # Track B: Ensure research artifacts exist
        if project_root:
            from app.services import artifact_service
            artifact_service.ensure_draft_artifacts(project_root)

        if goal_mode:
            goal_service.sync_goal_runtime(
                project,
                tasks=tasks,
                auditors=auditors,
                reality=reconciliation,
                active_sessions=[active_worker] if active_worker else [],
                autopilot_enabled=bool(config.get("desired_enabled", True)),
            )
        # Track B: Audit-only commit throttling — only meaningful when we have
        # a local project root to track commit cadence against.
        ledger: dict[str, Any] = {}
        if project_root:
            from app.services import liveness_service
            ledger = liveness_service.read_ledger(project_root)
        if ledger.get("consecutive_audit_only_commits", 0) >= 1:
            # Check if there are any non-audit ready tasks. 
            # If everything is just audit repair, and we already tried one, we pause.
            ready_tasks = [t for t in tasks if t.get("status") == "ready"]
            non_audit_ready = [t for t in ready_tasks if not _is_audit_repair_task(t)]
            
            if not non_audit_ready and not active_worker:
                logger.info("Autopilot: Throttling consecutive audit-only wakeup for %s", project_slug)
                _wake_event(project_slug).clear()
                continue

        if await cancel_stale_repair_tasks(project, tasks, auditors):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
        # Anti-stall: detect tasks that have been stuck in the same blocked/
        # needs_changes state for too many consecutive iterations and flag them
        # so the planner must decide (cancel, downgrade scope, or reroute).
        if await _detect_and_handle_stuck_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
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
                _record_goal_gate_failure(
                    project,
                    failure_class="planner_drift",
                    summary=str(blockers[0] if blockers else "Control-plane auditors blocked autopilot."),
                    root_cause_hypothesis="Session or planner truth has drifted away from canonical control-plane state.",
                    reusable_lesson="Research track must pause whenever control-plane truth is broken.",
                    next_repair_action="Launch or complete control-plane reconciliation before additional domain work.",
                )
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
                _wake_event(project_slug).clear()
                try:
                    await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
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
                _record_goal_gate_failure(
                    project,
                    failure_class="integrity_invalid",
                    summary=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                    root_cause_hypothesis="Completion requirements are not yet satisfied even though planner tasks are terminal.",
                    reusable_lesson="Completion must be certified by closeout evidence, not inferred from task activity.",
                    next_repair_action="Resolve closeout blockers, refresh integrity or ontology state, and rerun closeout.",
                )
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
                _wake_event(project_slug).clear()
                try:
                    await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
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
                if goal_mode:
                    goal_service.mark_completed(
                        project,
                        summary="Success criteria are satisfied, closeout is green, and no blocking repairs remain.",
                    )
                await _mark_project_completed(project)
                await _disable_autopilot_desired_state(
                    project_slug,
                    auto_approve=bool(_autopilot_configs.get(project_slug, {}).get("auto_approve", False)),
                )
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
        if _should_skip_planner_for_ready_repair(project, tasks, auditors):
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
                if goal_mode:
                    goal_service.sync_goal_runtime(
                        project,
                        tasks=tasks,
                        auditors=auditors,
                        reality=reconciliation,
                        active_sessions=[active_worker] if active_worker else [],
                        autopilot_enabled=bool(config.get("desired_enabled", True)),
                    )
                _update_config(project_slug, last_turn_result="Planner turn completed.")
                logger.info("Planner turn complete.")
            except Exception as e:
                logger.error(f"Planner turn failed in autopilot: {e}")
                if goal_mode:
                    goal_service.record_failure(
                        project,
                        failure_class="platform_bug",
                        summary=f"Planner turn failed: {e}",
                        root_cause_hypothesis="Planner execution failed inside the control plane rather than from a domain blocker.",
                        reusable_lesson="When planner execution fails, stop domain progress and repair the control plane first.",
                        next_repair_action="Inspect planner runtime, recent tasks, and session state; then rerun the planner turn.",
                        retry_eligible=True,
                    )
                _update_config(project_slug, last_action="Idle (Recovering from error)", last_turn_result=f"Error: {e}")
                await asyncio.sleep(60)
                continue

        poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
        if poll_result:
            if poll_result == "polled":
                consecutive_idle_turns = 0
            continue

        control_plane_gate = _control_plane_auditor_gate(auditors)
        if control_plane_gate.get("blocked"):
            if await _ensure_control_plane_repair_tasks(project, tasks, auditors):
                tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
                consecutive_idle_turns = 0
                poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
                if poll_result:
                    if poll_result == "polled":
                        consecutive_idle_turns = 0
                    continue
                control_plane_gate = _control_plane_auditor_gate(auditors)
            if not _has_ready_task_title(tasks, "Reconcile control-plane drift and stale sessions"):
                blockers = control_plane_gate.get("blockers") or []
                _record_goal_gate_failure(
                    project,
                    failure_class="planner_drift",
                    summary=str(blockers[0] if blockers else "Control-plane auditors blocked autopilot."),
                    root_cause_hypothesis="Session or planner truth has drifted away from canonical control-plane state.",
                    reusable_lesson="Research track must pause whenever control-plane truth is broken.",
                    next_repair_action="Launch or complete control-plane reconciliation before additional domain work.",
                )
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
                _wake_event(project_slug).clear()
                try:
                    await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue

        if await _ensure_integrity_repair_tasks(project, tasks):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
            poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
            if poll_result:
                if poll_result == "polled":
                    consecutive_idle_turns = 0
                continue
        if await _ensure_ontology_repair_task(project, tasks, auditors):
            tasks, active_worker, auditors = await _reload_tasks_and_auditors(project, board["_id"])
            consecutive_idle_turns = 0
            poll_result = await _poll_active_worker_if_present(project, active_worker, project_slug)
            if poll_result:
                if poll_result == "polled":
                    consecutive_idle_turns = 0
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
                _record_goal_gate_failure(
                    project,
                    failure_class="integrity_invalid",
                    summary=str(blockers[0] if blockers else "Closeout gate blocked autopilot completion."),
                    root_cause_hypothesis="Completion requirements are not yet satisfied even though planner tasks are terminal.",
                    reusable_lesson="Completion must be certified by closeout evidence, not inferred from task activity.",
                    next_repair_action="Resolve closeout blockers, refresh integrity or ontology state, and rerun closeout.",
                )
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
                _wake_event(project_slug).clear()
                try:
                    await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
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
                if goal_mode:
                    goal_service.mark_completed(
                        project,
                        summary="Success criteria are satisfied, closeout is green, and no blocking repairs remain.",
                    )
                await _mark_project_completed(project)
                await _disable_autopilot_desired_state(
                    project_slug,
                    auto_approve=bool(_autopilot_configs.get(project_slug, {}).get("auto_approve", False)),
                )
                break

        task_by_id = {str(t["_id"]): t for t in tasks}
        control_plane_gate = _control_plane_auditor_gate(auditors)

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
                if not _task_allowed_for_auditors(project, promotion_view, auditors):
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
                    if not _task_allowed_for_auditors(project, requeue_view, auditors):
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
        ready_tasks = _filter_ready_tasks_for_auditors(project, ready_tasks, auditors)
        ontology_auditor = auditors.get("ontology") or {}
        if not ready_tasks and ontology_auditor.get("status") == "blocked":
            blockers = ontology_auditor.get("blockers") or []
            _record_goal_gate_failure(
                project,
                failure_class="ontology_invalid",
                summary=str(blockers[0] if blockers else "Ontology auditor blocked autopilot."),
                root_cause_hypothesis="Hydration state, ontology artifacts, or ontology health remain invalid for trusted work.",
                reusable_lesson="Do not continue downstream research while ontology readiness is blocked.",
                next_repair_action="Repair hydration, source coverage, pipeline steps, or ontology health verification.",
            )
            _update_config(
                project_slug,
                last_action="Waiting for ontology repair",
                last_turn_result=str(blockers[0] if blockers else "Ontology auditor blocked autopilot."),
            )
            await raise_decision_event(
                project,
                source="autopilot",
                event_type="ontology_auditor_blocked",
                severity="needs_planner",
                summary=str(blockers[0] if blockers else "Ontology auditor blocked autopilot."),
                evidence_refs=[f"project:{project.get('slug')}"],
                recommended_actions=[
                    "Repair ontology readiness blockers",
                    "Hydrate or repair source/pipeline coverage",
                    "Advance only after ontology blockers are cleared",
                ],
            )
            _wake_event(project_slug).clear()
            try:
                await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
            continue
        integrity_auditor = auditors.get("integrity") or {}
        if not ready_tasks and integrity_auditor.get("status") == "blocked":
            blockers = integrity_auditor.get("blockers") or []
            _record_goal_gate_failure(
                project,
                failure_class="integrity_invalid",
                summary=str(blockers[0] if blockers else "Integrity auditor blocked autopilot."),
                root_cause_hypothesis="Claims, provenance, verification, or source admissibility are not yet valid for trusted promotion.",
                reusable_lesson="Do not promote final outputs until integrity blockers are repaired or downgraded.",
                next_repair_action="Repair evidence, provenance, freshness, admissibility, or verification state before continuing.",
            )
            _update_config(
                project_slug,
                last_action="Waiting for integrity repair",
                last_turn_result=str(blockers[0] if blockers else "Integrity auditor blocked autopilot."),
            )
            await raise_decision_event(
                project,
                source="autopilot",
                event_type="integrity_auditor_blocked",
                severity="needs_planner",
                summary=str(blockers[0] if blockers else "Integrity auditor blocked autopilot."),
                evidence_refs=[f"project:{project.get('slug')}"],
                recommended_actions=[
                    "Repair unsupported claims or missing evidence",
                    "Refresh stale sources or verification state",
                    "Advance only after integrity blockers are cleared",
                ],
            )
            _wake_event(project_slug).clear()
            try:
                await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
            continue
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
            if not unfinished and consecutive_idle_turns >= 3:
                logger.info("Autopilot: Stalled or finished (3 consecutive idle turns). Stopping.")
                break
            if unfinished:
                _update_config(
                    project_slug,
                    last_action="Waiting for repair wake event",
                    last_turn_result=(
                        f"No ready tasks yet; {len(unfinished)} unfinished task(s) remain. "
                        "Autopilot will keep watching for reconciliation or newly ready work."
                    ),
                )
            # Give the planner a chance to think/refine, or wait for a wake-up event
            _wake_event(project_slug).clear()
            try:
                await asyncio.wait_for(_wake_event(project_slug).wait(), timeout=60.0)
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
