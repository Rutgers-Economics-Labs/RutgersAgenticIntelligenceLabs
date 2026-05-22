"""
Liveness Service — Track B anti-stuck mechanisms.

Maintains the progress_ledger.json, tracking actual domain progress
instead of just file churn. Prevents infinite repair loops.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runners.contracts import SessionResult

logger = logging.getLogger(__name__)

LEDGER_REL_PATH = Path("research_plan") / "state" / "progress_ledger.json"

def get_ledger_path(project_root: Path) -> Path:
    return project_root / LEDGER_REL_PATH

def read_ledger(project_root: Path) -> dict[str, Any]:
    path = get_ledger_path(project_root)
    if not path.exists():
        return {
            "last_domain_progress_at": None,
            "domain_progress_events": [],
            "consecutive_maintenance_sessions": 0,
            "consecutive_audit_only_commits": 0,
            "repeated_blockers": {}
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to parse progress_ledger.json")
        return {
            "last_domain_progress_at": None,
            "domain_progress_events": [],
            "consecutive_maintenance_sessions": 0,
            "consecutive_audit_only_commits": 0,
            "repeated_blockers": {}
        }

def write_ledger(project_root: Path, ledger: dict[str, Any]) -> None:
    path = get_ledger_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

def check_liveness(project_root: Path, task_type: str, idempotency_key: str | None = None, input_hash: str | None = None) -> dict[str, Any]:
    """Evaluate anti-stuck rules before dispatching a new task.
    Returns {"allowed": bool, "reason": str}
    """
    ledger = read_ledger(project_root)
    
    # Rule 1: Maintenance limit
    if task_type in {"health_repair", "verification"}:
        if ledger.get("consecutive_maintenance_sessions", 0) >= 1:
            return {
                "allowed": False, 
                "reason": "Liveness guard: Max consecutive maintenance sessions reached. Domain progress required."
            }
            
    # Rule 2: No-repeat hash
    # We need to track executed hashes. Let's add them to the ledger.
    executed = ledger.get("executed_hashes", {})
    if idempotency_key and input_hash:
        if executed.get(idempotency_key) == input_hash:
            return {
                "allowed": False, 
                "reason": f"Liveness guard: Task {idempotency_key} already executed with input hash {input_hash}."
            }
            
    return {"allowed": True, "reason": "ok"}
    
def record_session_result(project_root: Path, session_id: str, raw_result: dict[str, Any]) -> None:

    """Update the progress ledger based on a session's structured result."""
    try:
        result = SessionResult.model_validate(raw_result)
    except Exception as e:
        logger.warning(f"Failed to validate session_result for liveness tracking: {e}")
        return

    ledger = read_ledger(project_root)
    
    # Calculate domain progress
    dp = result.domain_progress
    has_progress = (
        dp.new_sources > 0 or 
        dp.new_datasets > 0 or 
        dp.new_claim_candidates > 0 or 
        dp.new_analysis_artifacts > 0 or 
        dp.new_verified_claims > 0
    )

    now_iso = datetime.now(timezone.utc).isoformat() + "Z"

    if has_progress:
        ledger["last_domain_progress_at"] = now_iso
        ledger["consecutive_maintenance_sessions"] = 0
        ledger["domain_progress_events"].append({
            "session_id": session_id,
            "timestamp": now_iso,
            "progress": dp.model_dump()
        })
        # Reset repeated blockers if we made progress
        ledger["repeated_blockers"] = {}
    else:
        # If it was a health/maintenance task that made no domain progress
        if result.task_type.value == "health_repair" or result.task_type.value == "verification":
            ledger["consecutive_maintenance_sessions"] = ledger.get("consecutive_maintenance_sessions", 0) + 1

    # Record blockers
    for blocker in result.blockers:
        b_id = blocker.blocker_id or blocker.category
        ledger["repeated_blockers"][b_id] = ledger.get("repeated_blockers", {}).get(b_id, 0) + 1

    # Record executed hash
    if result.work_order_id:
        # We need to load the work order to get the idempotency key and input hash
        wo_path = project_root / "research_plan" / "work_orders" / f"{result.work_order_id}.json"
        try:
            wo_data = json.loads(wo_path.read_text(encoding="utf-8"))
            ik = wo_data.get("idempotency_key")
            ih = wo_data.get("input_hash")
            if ik and ih:
                if "executed_hashes" not in ledger:
                    ledger["executed_hashes"] = {}
                ledger["executed_hashes"][ik] = ih
        except Exception:
            pass

    write_ledger(project_root, ledger)
    logger.info(f"Liveness: Updated progress ledger for session {session_id}. Has progress: {has_progress}")

