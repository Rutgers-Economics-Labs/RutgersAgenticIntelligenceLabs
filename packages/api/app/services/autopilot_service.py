from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from app.services import planner_runtime, planner_service, running_agent_service
from app.runners import session_lifecycle
from app.services.convex_client import convex
from app.services.decision_service import list_decision_events, mark_decision_event, raise_decision_event

logger = logging.getLogger(__name__)

# State for tracking active autopilot loops per project
_active_autopilots: dict[str, bool] = {}
_autopilot_configs: dict[str, dict[str, Any]] = {}
_wake_events: dict[str, asyncio.Event] = {}

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
                if status not in {"awaiting_approval", "backlog", "blocked", "ready"}:
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
