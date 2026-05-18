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


async def _repair_stale_active_sessions(project: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    if not project_root or not project_root.exists():
        return {"repairedSessionIds": []}
    active_sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    repaired: list[str] = []
    for session in active_sessions:
        root = session_lifecycle._resolve_session_root_path(session, project_root=project_root)
        if root is None or not root.exists():
            continue
        state = session_lifecycle.session_files.read_state(root)
        status = str(state.get("status") or "")
        if status not in session_lifecycle.TERMINAL_STATUSES:
            continue
        await running_agent_service.finalize_running_agent(
            str(session["_id"]),
            status=status,
        )
        repaired.append(str(session["_id"]))
    return {"repairedSessionIds": repaired}


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
    weight = {"high": 0, "medium": 1, "low": 2, None: 3}.get(task.get("priority"), 3)
    return (weight, str(task.get("_id") or ""))


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
        repaired = await planner_service.reconcile_task_files(project)
        if repaired.get("removed"):
            _update_config(
                project_slug,
                last_action="Reconciled duplicate task files",
                last_turn_result=", ".join(repaired["removed"][:5]),
            )
        repaired_sessions = await _repair_stale_active_sessions(project)
        if repaired_sessions.get("repairedSessionIds"):
            _update_config(
                project_slug,
                last_action="Reconciled stale active sessions",
                last_turn_result=", ".join(repaired_sessions["repairedSessionIds"][:5]),
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
        
        # 1. Check for pending approvals if auto-approve is enabled
        config = _autopilot_configs.get(project_slug, {})
        if config.get("auto_approve"):
            try:
                approvals = await planner_service.list_approvals(project)
                pending = [a for a in approvals if a["status"] == "pending"]
                if pending:
                    for app in pending:
                        logger.info(f"Autopilot: Auto-approving {app['_id']}")
                        await planner_service.resolve_approval(
                            project=project,
                            approval_id=app["_id"],
                            status="granted",
                            resolution_note="Auto-approved by Autopilot Mode."
                        )
                        if app.get("taskId"):
                            await planner_service.update_task(app["taskId"], project=project, approval_state="granted")
            except Exception as e:
                logger.error(f"Failed to auto-approve in autopilot: {e}")

        board = await planner_service.ensure_main_board(project)
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        if await _ensure_ontology_lifecycle_tasks(project, tasks):
            tasks = await planner_service.list_tasks(board["_id"], project=project)
            consecutive_idle_turns = 0
        if await _reconcile_ontology_lifecycle_state(project, tasks):
            tasks = await planner_service.list_tasks(board["_id"], project=project)
            consecutive_idle_turns = 0

        all_done = all(t["status"] in ["done", "cancelled"] for t in tasks)
        if all_done and tasks:
            logger.info("Autopilot: All tasks are completed. Project goal reached.")
            _update_config(
                project_slug,
                last_action="Completed",
                last_turn_result="All planner tasks reached terminal status.",
            )
            await _mark_project_completed(project)
            break

        # 2. Run the planner to see what it wants to do
        _update_config(project_slug, last_action="Running Planner: Determining next task...")
        try:
            await planner_runtime.run_planner_turn(
                project=project,
                user_message="[AUTOPILOT MODE] Analyze the project state. If any tasks are 'ready', use launch_task_runner to start them. If tasks recently finished, analyze findings. If everything is done, synthesize the final report. Always move the project forward.",
                persist=False # Do not spam the chat thread
            )
            _update_config(project_slug, last_turn_result="Planner turn completed.")
            logger.info("Planner turn complete.")
        except Exception as e:
            logger.error(f"Planner turn failed in autopilot: {e}")
            _update_config(project_slug, last_action="Idle (Recovering from error)", last_turn_result=f"Error: {e}")
            await asyncio.sleep(60)
            continue

        # 3. Check if a worker is already running or was just launched
        _update_config(project_slug, last_action="Checking for active worker sessions...")
        active_worker = await running_agent_service.find_active_worker(project["_id"])
        if active_worker:
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
            logger.info(f"Autopilot: Waiting for worker {session_id} ({active_worker.get('role')}) to complete...")
            try:
                await session_lifecycle.poll_session_until_done(
                    session_id,
                    project_id=project["_id"],
                    max_polls=100,
                    poll_interval_seconds=5 # Snappier response
                )
                logger.info(f"Worker {active_worker['_id']} finished.")
                consecutive_idle_turns = 0
                continue # Re-run planner immediately after task completion
            except Exception as e:
                logger.error(f"Error polling worker in autopilot: {e}")
                await asyncio.sleep(10)
                continue
            
        # 4. Check tasks on the board to see if we are actually making progress
        # If everything is 'done' or 'cancelled', we are finished
        all_done = all(t["status"] in ["done", "cancelled"] for t in tasks)
        if all_done and tasks:
            logger.info("Autopilot: All tasks are completed. Project goal reached.")
            _update_config(
                project_slug,
                last_action="Completed",
                last_turn_result="All planner tasks reached terminal status.",
            )
            await _mark_project_completed(project)
            break

        task_by_id = {str(t["_id"]): t for t in tasks}

        if config.get("auto_approve"):
            promoted: list[str] = []
            approvals = await planner_service.list_approvals(project)
            for task in tasks:
                status = task.get("status")
                if status not in {"awaiting_approval", "backlog", "blocked"}:
                    continue
                if status == "blocked" and task.get("blockerCategory") == "publish_failure":
                    continue
                if not _dependencies_satisfied(task, task_by_id):
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
                consecutive_idle_turns = 0
                continue

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
                for task in cancelled_with_dependents:
                    await planner_service.update_task(
                        str(task["_id"]),
                        project=project,
                        status="ready",
                        runner=task.get("runner") or "cursor_cli",
                        approval_state="granted",
                        latestRunSummary="Requeued by Autopilot because downstream tasks still depend on it.",
                    )
                await mark_decision_event(project, event._id, "handled")
                await planner_service.sync_planner_files(project, board)
                consecutive_idle_turns = 0
                continue
            
        # Check if we have ready tasks that weren't launched
        ready_tasks = [t for t in tasks if t["status"] == "ready" and t.get("approvalState") != "pending"]
        if ready_tasks:
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
                consecutive_idle_turns = 0
                continue
            if launch_result and launch_result.get("error"):
                logger.info("Autopilot: Ready task launch deferred for %s: %s", project_slug, launch_result.get("error"))

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
