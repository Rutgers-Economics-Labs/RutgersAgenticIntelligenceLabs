"""
Stuck Detector — Track B anti-stuck diagnostics.

Analyzes the project progress ledger and generates diagnostic reports 
when a research loop enters a repetitive or non-productive cycle.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services import liveness_service

logger = logging.getLogger(__name__)

STUCK_REPORTS_DIR = Path("research_plan") / "stuck_reports"

# Track B: Blocker attempt budgets
BLOCKER_BUDGETS = {
    "source_fetch_failed": 2,
    "verification_failed": 2,
    "ontology_stale": 1,
    "integrity_blocked": 2
}

def detect_stuck_state(project_root: Path) -> dict[str, Any] | None:
    """
    Check if the project is stuck based on the progress ledger.
    Returns a diagnostic dict if stuck, else None.
    """
    ledger = liveness_service.read_ledger(project_root)
    
    issues = []
    
    # 1. Repeated Blockers (with budgets)
    for b_id, count in ledger.get("repeated_blockers", {}).items():
        budget = BLOCKER_BUDGETS.get(b_id, 3) # default budget of 3
        if count >= budget:
            issues.append({
                "type": "repeated_blocker",
                "id": b_id,
                "count": count,
                "budget": budget,
                "description": f"Blocker '{b_id}' has exhausted its retry budget ({count}/{budget})."
            })
            
    # 2. No Domain Progress
    no_progress_count = ledger.get("consecutive_no_progress_sessions", 0)
    if no_progress_count >= 5:
        issues.append({
            "type": "no_domain_progress",
            "count": no_progress_count,
            "description": f"Ran {no_progress_count} consecutive sessions without making domain progress (new sources, datasets, or claims)."
        })
            
    # 3. Maintenance Loop
    maint_count = ledger.get("consecutive_maintenance_sessions", 0)
    if maint_count >= 3:
        issues.append({
            "type": "maintenance_loop",
            "count": maint_count,
            "description": f"Ran {maint_count} consecutive maintenance sessions without any domain progress."
        })

    # 4. No new progress edges
    edges = ledger.get("progress_edges", [])
    if no_progress_count >= 10 and len(edges) == 0:
        issues.append({
            "type": "no_progress_edges",
            "count": no_progress_count,
            "description": f"No research progress edges (sources, datasets, claims) have ever been added, after {no_progress_count} sessions."
        })
    
    if not issues:
        return None
        
    return {
        "stuck": True,
        "issues": issues,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "last_domain_progress_at": ledger.get("last_domain_progress_at"),
        "consecutive_maintenance_sessions": maint_count,
        "recommended_escape": _derive_escape_path(issues)
    }

def _derive_escape_path(issues: list[dict]) -> str:
    """Suggest a recovery path based on the detected issues."""
    for issue in issues:
        if issue["type"] == "repeated_blocker":
            return (
                "Mark the blocker as a promotion-blocker only, allow candidate research to continue, "
                "or reduce the project scope to exclude the blocked component."
            )
        if issue["type"] in {"maintenance_loop", "no_domain_progress", "no_progress_edges"}:
            return (
                "Force a synthesis/draft task or a Minimum Viable Research (MVR) analysis task "
                "to break the cycle and produce the first research result."
            )
    return "Create a human decision request to resolve the impasse."

def write_stuck_report(project_root: Path, diagnosis: dict[str, Any]) -> Path:
    """Generate a Markdown stuck report in the project repository."""
    reports_dir = project_root / STUCK_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    now = datetime.now(timezone.utc)
    filename = f"stuck_{now.strftime('%Y%m%d_%H%M%S')}.md"
    report_path = reports_dir / filename
    
    issues_md = ""
    for issue in diagnosis["issues"]:
        issues_md += f"- **{issue['type']}**: {issue['description']}\n"
        
    content = f"""# RAIL Stuck Report

## Diagnosis
Detected a non-productive cycle in the research loop.

**Timestamp**: {diagnosis['timestamp']}

### Issues Detected
{issues_md}

### Recommended Escape Path
{diagnosis['recommended_escape']}

### Project Context
- **Last Progress**: {diagnosis.get('last_domain_progress_at', 'Unknown')}
- **Consecutive Maintenance**: {diagnosis.get('consecutive_maintenance_sessions', 'Unknown')}

---
*Generated automatically by RAIL Stuck Detector.*
"""
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Stuck Detector: Wrote diagnostic report to {report_path}")
    return report_path
