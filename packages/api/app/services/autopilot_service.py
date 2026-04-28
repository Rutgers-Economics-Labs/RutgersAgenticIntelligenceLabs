from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.services import planner_runtime, planner_service, running_agent_service
from app.runners import session_lifecycle

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
        board = await planner_service.ensure_main_board(project)
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        
        # If everything is 'done' or 'cancelled', we are finished
        all_done = all(t["status"] in ["done", "cancelled"] for t in tasks)
        if all_done and tasks:
            logger.info("Autopilot: All tasks are completed. Project goal reached.")
            break
            
        # Check if we have ready tasks that weren't launched
        ready_tasks = [t for t in tasks if t["status"] == "ready" and t.get("approvalState") != "pending"]
        
        if not ready_tasks:
            consecutive_idle_turns += 1
            logger.info(f"Autopilot: No ready tasks. Idle turns: {consecutive_idle_turns}")
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
