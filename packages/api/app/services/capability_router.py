"""
Capability Router — intelligent selection of agents based on task requirements.

Matches WorkOrder capability requirements against certified runner profiles,
applying project-level preferences and historical affinity scores.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.runners.contracts import Capability, TaskType
from app.runners.profile_loader import load_all_profiles, load_profile
from app.services import planner_service

logger = logging.getLogger(__name__)

DISPATCH_LOG_REL_PATH = Path("research_plan") / "dispatch_log"


async def route_task(
    project_slug: str,
    work_order_id: str,
    required_capabilities: list[Capability],
    task_type: TaskType,
    *,
    explicit_runner: str | None = None,
    project: dict[str, Any] | None = None,
) -> str:
    """
    Select the best runner for a task.
    Returns the runner name.
    Writes a routing decision log to the project repo.

    The caller may pass an already-resolved ``project`` record to avoid an
    extra DB lookup; otherwise we fetch by slug.
    """
    if project is None:
        project = await planner_service.resolve_project_reference(project_slug)
    root = planner_service.project_root_from_record(project)
    
    # 1. Load project-level runner policy from rail.yaml. Missing or invalid
    # manifests should not crash routing — fall back to "no allow-list".
    allowed_runners = None
    try:
        manifest = planner_service.load_validated_manifest(project)
        allowed_runners = getattr(manifest.agents, "runner_policy", None)
    except Exception as exc:
        logger.debug("Capability Router: no manifest policy for %s (%s)", project_slug, exc)
    
    # 2. Filter available runners by capabilities
    profiles = load_all_profiles()
    eligible: list[Any] = []
    
    reasons = {}

    for name, profile in profiles.items():
        # Check explicit allow-list if defined
        if allowed_runners and allowed_runners.allowed and name not in allowed_runners.allowed:
            reasons[name] = "Not in project allow-list"
            continue
            
        # Check capabilities
        missing = []
        for cap in required_capabilities:
            # profile.capabilities is a dict[Capability, CapabilityState]
            cap_val = profile.capabilities.get(cap, "no")
            if cap_val == "no":
                missing.append(cap.value)
        
        if missing:
            reasons[name] = f"Missing required capabilities: {', '.join(missing)}"
            continue
            
        eligible.append(profile)

    if explicit_runner:
        # If the operator forced a runner, we still check eligibility but 
        # proceed anyway (warning if not eligible)
        is_eligible = any(p.name == explicit_runner for p in eligible)
        _log_decision(root, work_order_id, explicit_runner, reasons, override=True)
        if not is_eligible:
            logger.warning("Capability Router: Manual override runner %s is not technically eligible for task %s", explicit_runner, work_order_id)
        return explicit_runner

    if not eligible:
        # Fallback or error
        error_msg = f"No eligible runners found for task {work_order_id}. Requirements: {[c.value for c in required_capabilities]}"
        _log_decision(root, work_order_id, None, reasons, error=error_msg)
        raise RuntimeError(error_msg)

    # 3. Rank eligible runners
    # Ranking formula: Affinity + (Preferred Bonus) + (Success Score)
    best_runner = None
    best_score = -1.0
    eligible_scores = {}
    
    for p in eligible:
        name = p.name
        # p.task_affinity is a dict[TaskType, float]
        affinity = p.task_affinity.get(task_type, 0.5)
        
        # Preferred bonus
        pref_bonus = 0.0
        if allowed_runners and allowed_runners.preferred and name in allowed_runners.preferred:
            pref_bonus = 0.2
            
        # Total score
        score = affinity + pref_bonus
        eligible_scores[name] = score
        
        if score > best_score:
            best_score = score
            best_runner = name

    _log_decision(root, work_order_id, best_runner, reasons, eligible_scores=eligible_scores)
    return best_runner


def _log_decision(
    project_root: Path | None,
    work_order_id: str,
    selected_runner: str | None,
    reasons: dict[str, str],
    eligible_scores: dict[str, float] | None = None,
    override: bool = False,
    error: str | None = None,
):
    if not project_root:
        return

    log_dir = project_root / DISPATCH_LOG_REL_PATH
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_path = log_dir / f"{work_order_id}.json"
    
    import datetime
    payload = {
        "work_order_id": work_order_id,
        "selected_runner": selected_runner,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
        "override": override,
        "error": error,
        "eligible_scores": eligible_scores or {},
        "rejection_reasons": reasons,
    }
    
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
