from __future__ import annotations

from pathlib import Path
from typing import Any

from app.runners import session_lifecycle
from app.services import planner_service, running_agent_service
from app.services.audit_service import repair_stale_session_audits


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
