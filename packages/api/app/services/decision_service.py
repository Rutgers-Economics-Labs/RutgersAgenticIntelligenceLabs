from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.services import planner_service, session_files


DECISION_STATUSES = {"open", "handled", "dismissed"}


@dataclass
class DecisionEvent:
    _id: str
    projectSlug: str
    source: str
    type: str
    severity: str
    summary: str
    evidenceRefs: list[str] = field(default_factory=list)
    recommendedActions: list[str] = field(default_factory=list)
    status: str = "open"
    createdAt: str | None = None
    updatedAt: str | None = None
    plannerRunAt: str | None = None
    plannerResponse: str | None = None


def _decision_root(project: dict) -> Path | None:
    root = planner_service.project_root_from_record(project)
    if root is None:
        return None
    return root / "research_plan" / "decisions"


def _decision_id(event_type: str, source: str, summary: str) -> str:
    digest = hashlib.sha1(f"{event_type}:{source}:{summary}".encode("utf-8")).hexdigest()[:10]
    safe_type = event_type.lower().replace("_", "-")
    safe_source = source.lower().replace("_", "-")
    return f"{safe_type}-{safe_source}-{digest}"


def _read_frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if not content.startswith("---\n"):
        return {}
    parts = content.split("\n---\n", 1)
    if len(parts) != 2:
        return {}
    data = yaml.safe_load(parts[0][4:]) or {}
    return data if isinstance(data, dict) else {}


def _render_decision(event: DecisionEvent) -> str:
    meta = {
        "decision_id": event._id,
        "project_slug": event.projectSlug,
        "source": event.source,
        "type": event.type,
        "severity": event.severity,
        "status": event.status,
        "evidence_refs": event.evidenceRefs,
        "recommended_actions": event.recommendedActions,
        "created_at": event.createdAt,
        "updated_at": event.updatedAt,
        "planner_run_at": event.plannerRunAt,
    }
    body = ["# Decision Event", "", event.summary.strip() or "No summary provided.", ""]
    if event.plannerResponse:
        body.extend(["## Planner Response", "", event.plannerResponse.strip(), ""])
    return f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n\n" + "\n".join(body)


def _decision_from_path(path: Path) -> DecisionEvent:
    meta = _read_frontmatter(path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    body = content.split("\n---\n", 1)[1].strip() if "\n---\n" in content else ""
    summary = body
    planner_response = None
    if "## Planner Response" in body:
        summary, planner_response = body.split("## Planner Response", 1)
        summary = summary.replace("# Decision Event", "", 1).strip()
        planner_response = planner_response.strip()
    else:
        summary = summary.replace("# Decision Event", "", 1).strip()
    return DecisionEvent(
        _id=meta.get("decision_id") or path.stem,
        projectSlug=meta.get("project_slug") or "",
        source=meta.get("source") or "system",
        type=meta.get("type") or "unknown",
        severity=meta.get("severity") or "needs_planner",
        summary=summary or "No summary provided.",
        evidenceRefs=meta.get("evidence_refs") or [],
        recommendedActions=meta.get("recommended_actions") or [],
        status=meta.get("status") or "open",
        createdAt=meta.get("created_at"),
        updatedAt=meta.get("updated_at"),
        plannerRunAt=meta.get("planner_run_at"),
        plannerResponse=planner_response,
    )


async def list_decision_events(project: dict, *, status: str | None = None) -> list[DecisionEvent]:
    root = _decision_root(project)
    if root is None or not root.is_dir():
        return []
    events = [_decision_from_path(path) for path in root.glob("*.md")]
    if status:
        events = [event for event in events if event.status == status]
    return sorted(events, key=lambda event: event.updatedAt or event.createdAt or "", reverse=True)


async def mark_decision_event(project: dict, decision_id: str, status: str) -> DecisionEvent | None:
    if status not in DECISION_STATUSES:
        raise ValueError(f"Unsupported decision status: {status}")
    root = _decision_root(project)
    if root is None:
        return None
    path = root / f"{decision_id}.md"
    if not path.exists():
        return None
    event = _decision_from_path(path)
    event.status = status
    event.updatedAt = session_files.utc_now_iso()
    path.write_text(_render_decision(event), encoding="utf-8")
    return event


async def raise_decision_event(
    project: dict,
    *,
    source: str,
    event_type: str,
    severity: str,
    summary: str,
    evidence_refs: list[str] | None = None,
    recommended_actions: list[str] | None = None,
    wake_planner: bool = True,
) -> DecisionEvent | None:
    root = _decision_root(project)
    if root is None:
        return None
    root.mkdir(parents=True, exist_ok=True)
    now = session_files.utc_now_iso()
    decision_id = _decision_id(event_type, source, summary)
    path = root / f"{decision_id}.md"

    if path.exists():
        event = _decision_from_path(path)
        if event.status == "open":
            return event
        event.status = "open"
        event.updatedAt = now
    else:
        event = DecisionEvent(
            _id=decision_id,
            projectSlug=project.get("slug") or "",
            source=source,
            type=event_type,
            severity=severity,
            summary=summary,
            evidenceRefs=evidence_refs or [],
            recommendedActions=recommended_actions or [],
            createdAt=now,
            updatedAt=now,
        )

    path.write_text(_render_decision(event), encoding="utf-8")

    if wake_planner and severity == "needs_planner" and not event.plannerRunAt:
        from app.services import planner_runtime

        prompt = await build_planner_decision_prompt(project, event)
        result = await planner_runtime.run_planner_turn(
            project=project,
            user_message=prompt,
            persist=True,
        )
        event.plannerRunAt = session_files.utc_now_iso()
        event.plannerResponse = str(result.get("assistantMessage") or "Planner turn completed.")
        event.updatedAt = event.plannerRunAt
        path.write_text(_render_decision(event), encoding="utf-8")

    return event


async def build_planner_decision_prompt(project: dict, event: DecisionEvent) -> str:
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    task_lines = [
        f"- {task['_id']}: status={task.get('status')} role={task.get('agentRole')} "
        f"runner={task.get('runner') or 'default'} deps={','.join(task.get('dependsOnTaskIds') or []) or 'none'}"
        for task in tasks
    ]
    evidence_lines = [f"- {item}" for item in event.evidenceRefs] or ["- none"]
    action_lines = [f"- {item}" for item in event.recommendedActions] or ["- decide the safest next action"]
    return (
        "You are the planning agent for this RAIL project.\n\n"
        "A decision event occurred.\n\n"
        f"Type: {event.type}\n"
        f"Source: {event.source}\n"
        f"Severity: {event.severity}\n"
        f"Summary: {event.summary}\n\n"
        "Evidence:\n"
        + "\n".join(evidence_lines)
        + "\n\nRecommended actions:\n"
        + "\n".join(action_lines)
        + "\n\nCurrent task state:\n"
        + "\n".join(task_lines)
        + "\n\nYour job:\n"
        "1. Decide whether this can be resolved automatically or needs the user.\n"
        "2. If automatic, update tasks, approvals, or rerun plan using tools.\n"
        "3. If user input is required, write one concise question with 2-3 concrete options.\n"
        "4. Do not claim work was completed unless there is artifact or run evidence.\n"
        "5. Record assumptions and affected outputs when relevant.\n"
    )
