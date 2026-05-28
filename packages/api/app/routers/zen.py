import logging
import time
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.models.zen import (
    ZenResponse, ZenProject, ZenActiveRun, ZenTruth, 
    ZenDecision, ZenPlan, ZenAttention, ZenArtifact
)
from app.services.convex_client import convex
from app.services import running_agent_service, planner_service, session_files, command_center_service
from app.services.integrity_service import load_integrity_indexes
from app.services.command_center_service import list_project_artifacts
from app.services.decision_service import list_decision_events

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["zen"])

async def _known_project(slug: str) -> dict | None:
    return await planner_service.get_project_by_slug(slug)

@router.get("/{slug}/zen", response_model=ZenResponse)
async def get_project_zen(slug: str):
    project = await _known_project(slug)
    if not project:
        raise HTTPException(404, f"Project '{slug}' not found")
    
    local_path = project.get("localRepoPath")
    if not local_path:
         raise HTTPException(400, f"Project '{slug}' has no localRepoPath")
         
    project_root = Path(local_path)
    projection = command_center_service.load_control_plane_summary(project)
    summary = projection["summary"]
    
    # 1. Objective
    current_plan = summary.get("currentPlan") or {}
    goal = summary.get("goal") or {}
    mission_brief = summary.get("missionBrief") or {}
    objective = (
        str(current_plan.get("summary") or "").strip()
        or str(goal.get("objective") or "").strip()
        or str(mission_brief.get("current") or "").strip()
        or "Define and execute the next approved step for this project."
    )
    plan_path = project_root / "research_plan" / "current_plan.md"
    if objective == "Define and execute the next approved step for this project." and plan_path.exists():
        try:
            content = plan_path.read_text(encoding="utf-8")
            match = re.search(r"## Objective\n\n(.*?)(?:\n\n##|$)", content, re.DOTALL)
            if match:
                objective = match.group(1).strip()
        except Exception as exc:
            logger.warning(f"Failed to read objective from {plan_path}: {exc}")
            
    # 2. Active Run
    active_worker = await running_agent_service.find_active_worker(project["_id"])
    active_run = None
    if active_worker:
        active_session_id = active_worker.get("sessionId") or active_worker.get("_id", "unknown")
        # Try to get elapsed time if creation time is available
        creation_time = active_worker.get("_creationTime", time.time() * 1000)
        elapsed = int(time.time() - creation_time / 1000)
        
        # Try to find last event and outputs created if session path exists
        last_event = "Starting agent..."
        outputs = []
        session_path_str = active_worker.get("sessionPath")
        if not session_path_str and active_worker.get("role") and active_session_id != "unknown":
            fallback_path = session_files.session_root(project_root, active_worker["role"], active_session_id)
            if fallback_path.exists():
                session_path_str = str(fallback_path)
        if session_path_str:
            session_path = Path(session_path_str)
            if session_path.exists():
                events = session_files.list_events(session_path)
                if events:
                    last = events[-1]
                    event_type = last.get("type") or last.get("event") or "event"
                    content = last.get("content")
                    if isinstance(content, list):
                        content = " ".join(str(item) for item in content[:2])
                    last_event = str(content or event_type or "Processing...")[:240]
                
                # Check for output files in workspace if possible, or use event hints
                # For now, we'll keep it simple
        
        active_run = ZenActiveRun(
            id=active_session_id,
            label=active_worker.get("title", "Active Agent"),
            role=active_worker.get("role", "agent"),
            runner=active_worker.get("runner") or active_worker.get("runtimeKind") or "unknown",
            status=active_worker.get("status", "running"),
            elapsedSeconds=max(0, elapsed),
            lastEvent=last_event,
            outputsCreated=outputs,
            needsInput=(active_worker.get("status") == "awaiting_input")
        )
        
    # 3. Latest Truth
    latest_truth = []
    try:
        indexes = load_integrity_indexes(project_root)
        for claim in indexes.claims[:5]:
            latest_truth.append(ZenTruth(
                claim=claim.statement,
                confidence=0.95 if claim.status == "verified" else 0.7,
                evidenceRefs=claim.evidence_paths,
                verified=(claim.status == "verified")
            ))
    except Exception as exc:
        logger.warning(f"Failed to load integrity indexes for truth section: {exc}")
        
    # 4. Plan
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    
    plan = ZenPlan(
        now=[t["title"] for t in tasks if t.get("status") in {"running", "ready"}],
        next=[t["title"] for t in tasks if t.get("status") == "awaiting_approval"][:3],
        later=[t["title"] for t in tasks if t.get("status") == "backlog"][:3],
        done=[t["title"] for t in tasks if t.get("status") == "done"][:3]
    )
    
    # 5. Decisions / Attention
    next_decision = None
    decision_cards = []
    running_or_ready = any(t.get("status") in {"running", "ready"} for t in tasks)
    cancelled_task_ids = {str(t["_id"]) for t in tasks if t.get("status") == "cancelled"}
    open_decisions = await list_decision_events(project, status="open")
    for event in open_decisions:
        if event.type == "no_ready_tasks" and (active_run or running_or_ready):
            continue
        if event.type == "task_cancelled_with_dependents":
            referenced_tasks = [
                ref.removeprefix("task:")
                for ref in event.evidenceRefs
                if ref.startswith("task:")
            ]
            if referenced_tasks and not any(task_id in cancelled_task_ids for task_id in referenced_tasks):
                continue
        decision_cards.append(ZenDecision(
            id=event._id,
            type=event.type,
            severity=event.severity,
            source=event.source,
            prompt=event.summary,
            recommendedAction=event.recommendedActions[0] if event.recommendedActions else None,
            actions=[
                {"label": action, "value": action.lower().replace(" ", "_"), "id": event._id}
                for action in event.recommendedActions[:3]
            ],
        ))
        if len(decision_cards) >= 5:
            break
    if decision_cards:
        next_decision = decision_cards[0]

    approvals = await planner_service.list_approvals(project)
    pending_approvals = [a for a in approvals if a.get("status") == "pending"]
    
    if not next_decision and pending_approvals:
        appr = pending_approvals[0]
        next_decision = ZenDecision(
            id=appr["_id"],
            type="approval",
            severity="needs_user",
            source="approval",
            prompt=f"Approval needed for {appr.get('approvalType', 'task execution')}",
            recommendedAction="Approve",
            actions=[
                {"label": "Approve", "value": "approve", "id": appr["_id"]},
                {"label": "Reject", "value": "reject", "id": appr["_id"]}
            ]
        )
    elif not next_decision and active_run and active_run.needsInput:
        next_decision = ZenDecision(
            id=active_run.id,
            type="input",
            severity="needs_user",
            source="runner",
            prompt=f"Agent '{active_run.label}' is waiting for your input.",
            recommendedAction="Provide Feedback",
            actions=[{"label": "Go to Session", "value": "navigate", "sessionId": active_run.id}]
        )
    
    attention = []
    blocked_tasks = [t for t in tasks if t.get("status") == "blocked"]
    for b in blocked_tasks:
        attention.append(ZenAttention(
            severity="error",
            title=f"Task Blocked: {b['title']}",
            detail=b.get("description", "No details provided."),
            action={"label": "View Task", "taskId": b["_id"]}
        ))
        
    # 6. Artifacts
    artifact_summary = None
    recent_artifacts = summary.get("recentArtifacts") or []
    artifacts = []
    artifact_rows = recent_artifacts
    if not artifact_rows:
        artifact_summary = list_project_artifacts(project)
        artifact_rows = artifact_summary.get("artifacts", [])
    for a in artifact_rows[:8]:
        artifacts.append(ZenArtifact(
            name=a["name"],
            path=a["path"],
            freshness="stale" if a.get("promotionState") == "stale" else "verified" if a.get("verificationStatus") == "passed" else "new",
            verified=(a.get("verificationStatus") == "passed")
        ))
        
    # 7. Project Metadata (Phase & Health)
    blocker_summary = summary.get("blockerSummary") or {}
    health = "On track"
    if summary.get("currentBlocker") or blocker_summary.get("blocked") or blocked_tasks:
        health = "Blocked"
    elif pending_approvals or decision_cards or (active_run and active_run.needsInput):
        health = "Needs input"
    elif not tasks:
        health = "Stale"
        
    # Rudimentary phase detection
    phase = str(summary.get("lifecyclePhase") or "").strip() or "Planning"
        
    return ZenResponse(
        project=ZenProject(
            name=project.get("name", "Unnamed Project"),
            slug=slug,
            phase=phase,
            health=health
        ),
        objective=objective,
        activeRun=active_run,
        latestTruth=latest_truth,
        nextDecision=next_decision,
        plan=plan,
        attention=attention,
        artifacts=artifacts,
        decisions=decision_cards,
    )
