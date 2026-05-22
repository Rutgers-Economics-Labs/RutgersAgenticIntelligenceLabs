"""
Lifecycle Service — Track B data-driven research phases.

Replaces hardcoded lifecycle logic in autopilot_service with a 
declarative transition table. Each phase defines exit criteria 
and escape paths (if blocked).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services import planner_service

logger = logging.getLogger(__name__)

# Default Lifecycle Definition
DEFAULT_LIFECYCLE = {
    "phases": {
        "brief": {
            "exit_when": ["project_slug_defined"],
            "if_blocked": ["ask_user_for_brief"]
        },
        "source_discovery": {
            "exit_when": ["at_least_one_source_registered"],
            "if_blocked": [
                "create_source_search_task",
                "ask_user_for_source",
                "continue_with_known_sources"
            ]
        },
        "hydration_ready": {
            "exit_when": ["at_least_one_analysis_ready_dataset"],
            "if_blocked": [
                "run_targeted_hydration_repair",
                "mark_partial_hydration",
                "allow_candidate_research"
            ]
        },
        "research_active": {
            "exit_when": [
                "at_least_one_claim_candidate",
                "at_least_one_draft_artifact"
            ],
            "if_blocked": [
                "create_mvr_task",
                "reduce_scope",
                "produce_stuck_report"
            ]
        },
        "synthesis_ready": {
            "exit_when": ["final_memo_produced"],
            "if_blocked": ["ask_user_for_review"]
        }
    }
}

async def evaluate_lifecycle(project: dict[str, Any], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Determine the current lifecycle phase and the next best action.
    Returns {"phase": str, "research_allowed": bool, "promotion_allowed": bool, "next_best_action": dict | None}
    """
    from app.services import liveness_service
    from pathlib import Path
    
    project_root = Path(project.get("localRepoPath")) if project.get("localRepoPath") else None
    ledger = liveness_service.read_ledger(project_root) if project_root else {}
    
    current_phase = project.get("lifecyclePhase") or "brief"
    
    # 1. Check exit criteria for current phase
    can_exit = True
    phase_config = DEFAULT_LIFECYCLE["phases"].get(current_phase, {})
    
    for criterion in phase_config.get("exit_when", []):
        if not _check_criterion(criterion, project, ledger, tasks):
            can_exit = False
            break
            
    # 2. Suggest next phase if current is done
    if can_exit:
        # Simplistic linear transition for now
        phase_order = list(DEFAULT_LIFECYCLE["phases"].keys())
        try:
            curr_idx = phase_order.index(current_phase)
            if curr_idx < len(phase_order) - 1:
                next_phase = phase_order[curr_idx + 1]
                logger.info(f"Lifecycle: Phase {current_phase} exit criteria met. Transitioning to {next_phase}.")
                # (Actual phase update would happen via planner_service)
            else:
                next_phase = current_phase
        except ValueError:
            next_phase = current_phase
    else:
        next_phase = current_phase

    return {
        "phase": next_phase,
        "research_allowed": True,
        "promotion_allowed": False, # Gated by auditors usually
        "next_best_action": _get_next_action(next_phase, tasks, ledger)
    }

def _check_criterion(name: str, project: dict[str, Any], ledger: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    """Evaluate a specific exit criterion."""
    if name == "project_slug_defined":
        return bool(project.get("slug"))
    if name == "at_least_one_source_registered":
        return ledger.get("domain_progress", {}).get("new_sources", 0) > 0 or len(project.get("sources", [])) > 0
    if name == "at_least_one_analysis_ready_dataset":
        return ledger.get("domain_progress", {}).get("new_datasets", 0) > 0
    if name == "at_least_one_claim_candidate":
        return ledger.get("domain_progress", {}).get("new_claim_candidates", 0) > 0
    return False

def _get_next_action(phase: str, tasks: list[dict[str, Any]], ledger: dict[str, Any]) -> dict[str, Any] | None:
    """Suggest the next best action if blocked or in a phase."""
    # Matches Item 15's schema
    if phase == "source_discovery":
        return {
            "task_type": "source_discovery",
            "runner_capabilities_required": ["browse_web", "edit_files"],
            "expected_progress": ["new_remote_source_fetched"],
            "fallback_if_failed": "generate_stuck_report"
        }
    if phase == "research_active":
        return {
            "task_type": "analysis",
            "runner_capabilities_required": ["query_duckdb", "execute_python", "write_claims"],
            "expected_progress": ["claim_candidate_created", "hypothesis_rejected"],
            "fallback_if_failed": "generate_stuck_report"
        }
    return None
