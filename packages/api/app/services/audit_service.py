from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services import planner_service, session_files
from app.services.integrity_service import evaluate_integrity_gate
from rail.manifest import load_manifest


def _audit_root(project_root: Path) -> Path:
    return project_root / "research_plan" / "audits"


def _session_roots(project_root: Path) -> list[Path]:
    sessions_root = project_root / "research_plan" / "sessions"
    if not sessions_root.is_dir():
        return []
    return sorted(path for path in sessions_root.glob("*/*") if path.is_dir())


def read_latest_audit(project_root: Path) -> dict[str, Any] | None:
    audit_root = _audit_root(project_root)
    if not audit_root.is_dir():
        return None
    candidates = sorted(audit_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload["path"] = str(path.relative_to(project_root))
        return payload
    return None


def _normalize_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("_id") or "Untitled task")


def _planner_snapshot(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    ready_titles = [_normalize_title(task) for task in tasks if task.get("status") == "ready"][:5]
    blocked_titles = [_normalize_title(task) for task in tasks if task.get("status") == "blocked"][:5]
    active_titles = [
        _normalize_title(task)
        for task in tasks
        if task.get("status") not in {"done", "cancelled", "blocked", "ready"}
    ][:5]
    return {
        "taskCounts": counts,
        "readyTasks": ready_titles,
        "blockedTasks": blocked_titles,
        "activeTasks": active_titles,
    }


def _derive_current_blocker(
    *,
    state: dict[str, Any],
    integrity_gate: dict[str, Any],
    planner_snapshot: dict[str, Any],
) -> str | None:
    blockers = state.get("completion_summary", {}).get("blockers") or []
    if blockers:
        return str(blockers[0])
    if state.get("publish_status") == "failed":
        return str(state.get("publish_error") or "Publish failed.")
    if state.get("verification_status") == "failed":
        reasons = integrity_gate.get("reasons") or []
        if reasons:
            return str(reasons[0])
        return "Verification failed."
    blocked_tasks = planner_snapshot.get("blockedTasks") or []
    if blocked_tasks:
        return f"Blocked planner task: {blocked_tasks[0]}"
    ready_tasks = planner_snapshot.get("readyTasks") or []
    if ready_tasks and state.get("review_status") != "review":
        return f"Ready planner task waiting on review: {ready_tasks[0]}"
    return None


def _render_audit_markdown(payload: dict[str, Any]) -> str:
    session = payload["session"]
    planner = payload["planner"]
    integrity = payload["integrity"]
    lines = [
        "# Post-Run Audit",
        "",
        f"- Session: `{session['id']}`",
        f"- Role: `{session['role']}`",
        f"- Status: `{session['status']}`",
        f"- Review: `{session['reviewStatus']}`",
        f"- Verification: `{session['verificationStatus']}`",
        f"- Publish: `{session['publishStatus']}`",
    ]
    if payload.get("currentBlocker"):
        lines.extend(["", "## Current Blocker", "", f"- {payload['currentBlocker']}"])
    lines.extend(
        [
            "",
            "## Planner Snapshot",
            "",
            f"- Task counts: `{json.dumps(planner['taskCounts'], sort_keys=True)}`",
            f"- Ready tasks: {', '.join(planner['readyTasks']) if planner['readyTasks'] else 'None'}",
            f"- Blocked tasks: {', '.join(planner['blockedTasks']) if planner['blockedTasks'] else 'None'}",
            f"- Active tasks: {', '.join(planner['activeTasks']) if planner['activeTasks'] else 'None'}",
            "",
            "## Integrity Snapshot",
            "",
            f"- Action: `{integrity['action']}`",
            f"- Blocked: `{integrity['blocked']}`",
            f"- Reasons: {', '.join(integrity['reasons']) if integrity['reasons'] else 'None'}",
        ]
    )
    changed_files = session.get("changedFiles") or []
    if changed_files:
        lines.extend(["", "## Changed Files", ""])
        lines.extend(f"- `{path}`" for path in changed_files)
    return "\n".join(lines) + "\n"


def audit_gate_status(project_root: Path) -> dict[str, Any]:
    latest = read_latest_audit(project_root)
    latest_generated_at = str((latest or {}).get("generatedAt") or "")
    stale_sessions: list[str] = []
    terminal_sessions: list[str] = []

    for session_root in _session_roots(project_root):
        state = session_files.read_state(session_root)
        status = str(state.get("status") or "")
        if status not in {"completed", "failed", "cancelled"}:
            continue
        session_id = str(state.get("session_id") or session_root.name)
        terminal_sessions.append(session_id)
        updated_at = str(state.get("updated_at") or "")
        if not latest:
            stale_sessions.append(session_id)
            continue
        audited_session_id = str((latest.get("session") or {}).get("id") or "")
        if session_id != audited_session_id and updated_at >= latest_generated_at:
            stale_sessions.append(session_id)
            continue
        if session_id == audited_session_id and updated_at > latest_generated_at:
            stale_sessions.append(session_id)

    return {
        "blocked": bool(stale_sessions),
        "reason": (
            "Autopilot is waiting for audited truth to catch up with terminal session state."
            if stale_sessions
            else None
        ),
        "staleSessionIds": stale_sessions,
        "latestAudit": latest,
        "latestAuditPath": (latest or {}).get("path") if latest else None,
        "terminalSessionIds": terminal_sessions,
    }


async def write_post_run_audit(
    *,
    project: dict[str, Any],
    project_root: Path,
    session_root: Path,
    session_id: str,
    session: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    state = session_files.read_state(session_root)
    manifest = load_manifest(project_root)
    integrity_gate = evaluate_integrity_gate(project_root, manifest, action="artifact_generation")
    tasks: list[dict[str, Any]] = []
    if project.get("_id") or project.get("projectId"):
        try:
            board = await planner_service.ensure_main_board(project)
            tasks = await planner_service.list_tasks(board["_id"], project=project)
        except Exception:
            tasks = []
    planner = _planner_snapshot(tasks)
    payload = {
        "generatedAt": session_files.utc_now_iso(),
        "session": {
            "id": session_id,
            "role": session.get("role") or state.get("role") or "agent",
            "status": state.get("status") or "unknown",
            "reviewStatus": state.get("review_status") or "pending",
            "verificationStatus": state.get("verification_status") or "pending",
            "publishStatus": state.get("publish_status") or "not_started",
            "taskId": state.get("task_id") or session.get("taskId"),
            "changedFiles": list(changed_files),
        },
        "planner": planner,
        "integrity": {
            "action": integrity_gate.get("action") or "artifact_generation",
            "blocked": bool(integrity_gate.get("blocked")),
            "reasons": [str(item) for item in (integrity_gate.get("reasons") or [])],
        },
        "completionSummary": state.get("completion_summary") or {},
    }
    payload["currentBlocker"] = _derive_current_blocker(
        state=state,
        integrity_gate=payload["integrity"],
        planner_snapshot=planner,
    )
    audit_root = _audit_root(project_root)
    audit_root.mkdir(parents=True, exist_ok=True)
    json_path = audit_root / f"{session_id}.json"
    md_path = audit_root / f"{session_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_audit_markdown(payload), encoding="utf-8")
    return {"jsonPath": str(json_path), "markdownPath": str(md_path), "payload": payload}
