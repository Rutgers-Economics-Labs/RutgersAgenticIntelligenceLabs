from __future__ import annotations

from pathlib import Path
from typing import Any

from app.runners import session_lifecycle
from app.services import planner_service, running_agent_service
from app.services.audit_service import audit_gate_status, repair_stale_session_audits


async def repair_stale_active_sessions(project: dict[str, Any]) -> dict[str, Any]:
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


async def project_reality_status(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None = None,
    active_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = planner_service.project_root_from_record(project)
    if root is None or not root.exists():
        return {
            "hasDrift": False,
            "duplicateTaskFileCount": 0,
            "taskSessionMismatchCount": 0,
            "staleRuntimeSessionCount": 0,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 0,
            "activeRuntimeSessionCount": len(active_sessions or []),
        }

    runtime_tasks = tasks if tasks is not None else await planner_service.list_tasks("main", project=project)
    runtime_active_sessions = (
        active_sessions
        if active_sessions is not None
        else await running_agent_service.list_project_running_agents(project["_id"], active_only=True, limit=50)
    )

    task_by_id = {str(task.get("_id") or ""): task for task in runtime_tasks}
    mismatch_count = 0
    for session_root in planner_service._session_task_roots(root):
        state = session_lifecycle.session_files.read_state(session_root)
        task_id = str(state.get("task_id") or "").strip()
        if not task_id or task_id not in task_by_id:
            continue
        patch = planner_service._terminal_task_patch_from_session_state(
            state,
            str(state.get("session_id") or session_root.name),
        )
        if patch is None:
            continue
        task = task_by_id[task_id]
        if (
            str(task.get("status") or "") != patch["status"]
            or task.get("blockerCategory") != patch["blockerCategory"]
            or str(task.get("latestRunSummary") or "") != patch["latestRunSummary"]
            or (task.get("approvalState") is not None and patch["status"] in {"done", "cancelled", "blocked"})
        ):
            mismatch_count += 1

    stale_runtime_count = 0
    for session in runtime_active_sessions:
        session_root = session_lifecycle._resolve_session_root_path(session, project_root=root)
        if session_root is None or not session_root.exists():
            continue
        state = session_lifecycle.session_files.read_state(session_root)
        status = str(state.get("status") or "")
        if status in session_lifecycle.TERMINAL_STATUSES:
            stale_runtime_count += 1

    task_dir = root / "research_plan" / "tasks"
    duplicate_count = 0
    if task_dir.is_dir():
        seen: dict[tuple[str, str], int] = {}
        for path in sorted(task_dir.glob("*.md")):
            task = planner_service._task_to_runtime(path)
            key = planner_service._task_dedupe_key(task)
            if key == ("", ""):
                continue
            seen[key] = seen.get(key, 0) + 1
        duplicate_count = sum(count - 1 for count in seen.values() if count > 1)

    gate = audit_gate_status(root)
    stale_audit_count = len(gate.get("staleSessionIds") or [])
    terminal_count = len(gate.get("terminalSessionIds") or [])

    return {
        "hasDrift": bool(duplicate_count or mismatch_count or stale_runtime_count or stale_audit_count),
        "duplicateTaskFileCount": duplicate_count,
        "taskSessionMismatchCount": mismatch_count,
        "staleRuntimeSessionCount": stale_runtime_count,
        "staleAuditSessionCount": stale_audit_count,
        "terminalSessionCount": terminal_count,
        "activeRuntimeSessionCount": len(runtime_active_sessions),
    }


async def reconcile_project_reality(project: dict[str, Any]) -> dict[str, Any]:
    root = planner_service.project_root_from_record(project)
    removed_task_files: list[str] = []
    updated_task_ids: list[str] = []
    repaired_session_ids: list[str] = []
    repaired_audit_session_ids: list[str] = []

    removed_task_files = list((await planner_service.reconcile_task_files(project)).get("removed") or [])
    updated_task_ids = list((await planner_service.reconcile_task_session_states(project)).get("updated") or [])
    repaired_session_ids = list((await repair_stale_active_sessions(project)).get("repairedSessionIds") or [])
    if root is not None and root.exists():
        repaired_audit_session_ids = list((await repair_stale_session_audits(project, root)).get("repairedSessionIds") or [])

    return {
        "removedTaskFiles": removed_task_files,
        "updatedTaskIds": updated_task_ids,
        "repairedSessionIds": repaired_session_ids,
        "repairedAuditSessionIds": repaired_audit_session_ids,
        "hasChanges": bool(
            removed_task_files
            or updated_task_ids
            or repaired_session_ids
            or repaired_audit_session_ids
        ),
    }
