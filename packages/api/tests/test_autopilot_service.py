from __future__ import annotations

import asyncio
from pathlib import Path

from app.services import autopilot_service
from app.services import reconciliation_service
from rail.bootstrap import bootstrap_future_project
from app.services.github_service import GitHubService


def test_autopilot_auto_approves_ready_pending_task(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    promoted = {"value": False}
    task = {
        "_id": "design-ontology-backed-ingestion-plan-for-soccer-ecosystem-data",
        "status": "ready",
        "approvalState": "pending",
        "runner": "codex_cli",
        "dependsOnTaskIds": [],
    }
    updates: list[dict] = []
    created: list[dict] = []
    resolved: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        task["approvalState"] = "granted" if promoted["value"] else "pending"
        return [task]

    async def _list_approvals(project_arg):
        return []

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-1"

    async def _resolve_approval(**kwargs):
        resolved.append(kwargs)
        return {"_id": "approval-1", "taskId": task["_id"], "status": "granted"}

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        promoted["value"] = True
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "resolve_approval", _resolve_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert created and created[0]["task_id"] == task["_id"]
    assert resolved and resolved[0]["approval_id"] == "approval-1"
    assert updates and updates[0]["approval_state"] == "granted"
    assert updates[0]["status"] == "ready"


def test_autopilot_launches_promoted_task_in_same_iteration(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    task_id = "design-ontology-backed-ingestion-plan-for-soccer-ecosystem-data"
    promoted = {"value": False}
    launches: list[list[str]] = []
    reconcile_calls = {"count": 0}

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": task_id,
                "title": "Design ontology-backed ingestion plan for soccer ecosystem data",
                "status": "ready",
                "approvalState": "granted" if promoted["value"] else "pending",
                "runner": "codex_cli",
                "priority": "high",
                "dependsOnTaskIds": [],
            }
        ]

    async def _list_approvals(project_arg):
        return []

    async def _create_approval(**kwargs):
        return "approval-1"

    async def _resolve_approval(**kwargs):
        return {"_id": "approval-1", "taskId": task_id, "status": "granted"}

    async def _update_task(task_id_arg: str, *, project=None, **fields):
        promoted["value"] = True
        return {"_id": task_id_arg, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(item["_id"]) for item in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _reconcile_project_reality(project_arg):
        reconcile_calls["count"] += 1
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "resolve_approval", _resolve_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == [[task_id]]
    assert reconcile_calls["count"] == 1


def test_autopilot_does_not_auto_promote_after_planner_refresh_blocks_control_plane(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    task_id = "research-task"
    planner_turns: list[str] = []
    updates: list[dict] = []
    raised_events: list[str] = []
    auditor_call_count = {"value": 0}

    class _ImmediateWakeEvent:
        def clear(self):
            return None

        async def wait(self):
            return True

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": task_id,
                "title": "Continue downstream research synthesis",
                "status": "awaiting_approval",
                "approvalState": "pending",
                "runner": "codex_cli",
                "priority": "high",
                "dependsOnTaskIds": [],
            }
        ]

    async def _list_approvals(project_arg):
        return []

    async def _create_approval(**kwargs):
        raise AssertionError("approval should not be created when control-plane auditors become blocked")

    async def _resolve_approval(**kwargs):
        raise AssertionError("approval should not be resolved when control-plane auditors become blocked")

    async def _update_task(task_id_arg: str, *, project=None, **fields):
        updates.append({"task_id": task_id_arg, **fields})
        return {"_id": task_id_arg, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _raise_decision_event(project_arg, **kwargs):
        raised_events.append(kwargs["event_type"])
        autopilot_service._active_autopilots["soccer-project"] = False
        return type("Event", (), {"_id": "event-1"})()

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "blocked", "blockers": ["1 terminal session audit(s) are stale or missing."]},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "resolve_approval", _resolve_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = _ImmediateWakeEvent()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert updates == []
    assert raised_events == ["control_plane_auditor_blocked"]


def test_autopilot_reenters_control_plane_gate_after_planner_refresh(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    planner_turns: list[str] = []
    events: list[str] = []
    auditor_call_count = {"value": 0}

    class _ImmediateWakeEvent:
        def clear(self):
            return None

        async def wait(self):
            return True

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Continue downstream research synthesis",
                "status": "backlog",
                "dependsOnTaskIds": [],
            }
        ]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs["event_type"])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "blocked", "blockers": ["1 terminal session audit(s) are stale or missing."]},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = _ImmediateWakeEvent()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert events == ["control_plane_auditor_blocked"]


def test_autopilot_creates_integrity_repair_after_planner_refresh(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    planner_turns: list[str] = []
    launches: list[list[str]] = []
    integrity_repair_created = {"value": False}
    auditor_call_count = {"value": 0}

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if integrity_repair_created["value"]:
            return [
                {
                    "_id": "repair-integrity",
                    "title": "Repair unsupported claims and verification evidence",
                    "status": "ready",
                    "approvalState": "granted",
                    "agentRole": "health",
                    "priority": "high",
                    "runner": "codex_cli",
                    "dependsOnTaskIds": [],
                }
            ]
        return [
            {
                "_id": "task-1",
                "title": "Continue downstream research synthesis",
                "status": "backlog",
                "dependsOnTaskIds": [],
            }
        ]

    async def _ensure_integrity_repair_tasks(project_arg, tasks):
        if auditor_call_count["value"] >= 2 and not integrity_repair_created["value"]:
            integrity_repair_created["value"] = True
            return True
        return False

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(item["_id"]) for item in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "blocked", "blockers": ["2 unsupported claim(s) lack evidence."]},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", _ensure_integrity_repair_tasks)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert launches == [["repair-integrity"]]


def test_autopilot_creates_ontology_repair_after_planner_refresh(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    planner_turns: list[str] = []
    launches: list[list[str]] = []
    ontology_repair_created = {"value": False}
    auditor_call_count = {"value": 0}

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if ontology_repair_created["value"]:
            return [
                {
                    "_id": "repair-ontology",
                    "title": "Repair ontology readiness blockers",
                    "status": "ready",
                    "approvalState": "granted",
                    "agentRole": "health",
                    "priority": "high",
                    "runner": "codex_cli",
                    "dependsOnTaskIds": [],
                }
            ]
        return [
            {
                "_id": "task-1",
                "title": "Continue downstream research synthesis",
                "status": "backlog",
                "dependsOnTaskIds": [],
            }
        ]

    async def _ensure_ontology_repair_task(project_arg, tasks, auditors):
        if auditor_call_count["value"] >= 2 and not ontology_repair_created["value"]:
            ontology_repair_created["value"] = True
            return True
        return False

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(item["_id"]) for item in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", _ensure_ontology_repair_task)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert launches == [["repair-ontology"]]


def test_autopilot_reenters_integrity_gate_after_planner_refresh(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    planner_turns: list[str] = []
    events: list[str] = []
    auditor_call_count = {"value": 0}

    class _ImmediateWakeEvent:
        def clear(self):
            return None

        async def wait(self):
            return True

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Continue downstream research synthesis",
                "status": "backlog",
                "dependsOnTaskIds": [],
            }
        ]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs["event_type"])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = _ImmediateWakeEvent()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert events == ["integrity_auditor_blocked"]


def test_autopilot_reenters_ontology_gate_after_planner_refresh(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    planner_turns: list[str] = []
    events: list[str] = []
    auditor_call_count = {"value": 0}

    class _ImmediateWakeEvent:
        def clear(self):
            return None

        async def wait(self):
            return True

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Continue downstream research synthesis",
                "status": "backlog",
                "dependsOnTaskIds": [],
            }
        ]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs["event_type"])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        auditor_call_count["value"] += 1
        if auditor_call_count["value"] == 1:
            return {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            }
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = _ImmediateWakeEvent()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert events == ["ontology_auditor_blocked"]


def test_autopilot_control_plane_gate_only_launches_repair_task(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
    tasks = [
        {
            "_id": "task-1",
            "title": "Continue downstream research synthesis",
            "status": "awaiting_approval",
            "approvalState": "pending",
            "runner": "codex_cli",
            "dependsOnTaskIds": [],
        },
        {
            "_id": "task-repair",
            "title": "Reconcile control-plane drift and stale sessions",
            "status": "ready",
            "approvalState": "granted",
            "agentRole": "health",
            "runner": "codex_cli",
            "dependsOnTaskIds": [],
        },
    ]
    launches: list[list[str]] = []
    created: list[dict] = []
    resolved: list[dict] = []
    updates: list[dict] = []
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return tasks

    async def _list_approvals(project_arg):
        return []

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-1"

    async def _resolve_approval(**kwargs):
        resolved.append(kwargs)
        return {"_id": "approval-1"}

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(task["_id"]) for task in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) detected."]},
            "planner": {"status": "blocked", "blockers": ["1 duplicate task file(s) detected."]},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "resolve_approval", _resolve_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launches == [["task-repair"]]
    assert created == []
    assert resolved == []
    assert updates == []


def test_start_autopilot_marks_project_completed_when_all_tasks_terminal(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "pipelineConfigSlug": "soccer-pipeline"}
    completions: list[dict] = []
    planner_turns: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append(kwargs)
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "status": "done", "dependsOnTaskIds": []}]

    async def _mark_project_completed(project_arg):
        completions.append(project_arg)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _mark_project_completed)
    monkeypatch.setattr(autopilot_service, "_closeout_gate", lambda project_arg, tasks: asyncio.sleep(0, result={"blocked": False, "reason": None}))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "ready", "blockers": []},
            },
        ),
    )

    asyncio.run(autopilot_service.start_autopilot("soccer-project"))

    assert completions == [project]
    assert planner_turns == []
    assert autopilot_service._active_autopilots.get("soccer-project") is False


def test_start_autopilot_restarts_loop_while_desired_enabled(monkeypatch, tmp_path):
    import json

    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "localRepoPath": str(tmp_path)}
    runs: list[dict] = []
    sleeps: list[float] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_autopilot_loop(slug: str, *, max_iterations=None):
        runs.append({"slug": slug, "max_iterations": max_iterations})
        if len(runs) == 1:
            return None
        await autopilot_service._disable_autopilot_desired_state(slug, auto_approve=True)
        return None

    async def _sleep(seconds: float):
        sleeps.append(seconds)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service, "run_autopilot_loop", _run_autopilot_loop)
    monkeypatch.setattr(autopilot_service.asyncio, "sleep", _sleep)

    asyncio.run(autopilot_service.start_autopilot("soccer-project", auto_approve=True))

    state_path = tmp_path / ".rail" / "autopilot_state.json"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert runs == [
        {"slug": "soccer-project", "max_iterations": None},
        {"slug": "soccer-project", "max_iterations": None},
    ]
    assert persisted["enabled"] is False
    assert persisted["autoApprove"] is True
    assert sleeps == [1]


def test_autopilot_does_not_complete_when_closeout_gate_is_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "pipelineConfigSlug": "soccer-pipeline"}
    completions: list[dict] = []
    events: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "status": "done", "dependsOnTaskIds": []}]

    async def _mark_project_completed(project_arg):
        completions.append(project_arg)
        return None

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _mark_project_completed)
    monkeypatch.setattr(autopilot_service.planner_service, "load_validated_manifest", lambda project: None)
    monkeypatch.setattr(autopilot_service, "cancel_stale_repair_tasks", lambda *args, **kwargs: asyncio.sleep(0, result=0))

    async def _ensure_closeout_repair_task(*args, **kwargs):
        return False

    monkeypatch.setattr(autopilot_service, "_ensure_closeout_repair_task", _ensure_closeout_repair_task)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["Integrity closeout gate is blocked."]},
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()
    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project", max_iterations=2))

    assert completions == []
    assert events and events[0]["event_type"] == "closeout_gate_blocked"


def test_autopilot_launches_created_closeout_repair_task_before_waiting(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "localRepoPath": str(tmp_path)}
    launches: list[dict] = []
    events: list[dict] = []
    created_titles: list[str] = []
    created = {"value": False}

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        tasks = [
            {"_id": "task-1", "title": "Existing completed task", "status": "done", "dependsOnTaskIds": []},
        ]
        if created["value"]:
            tasks.append(
                {
                    "_id": "repair-closeout",
                    "title": "Resolve closeout blockers",
                    "status": "ready",
                    "agentRole": "health",
                    "approvalState": "granted",
                    "priority": "medium",
                    "dependsOnTaskIds": [],
                }
            )
        return tasks

    async def _create_task(**kwargs):
        created["value"] = True
        created_titles.append(str(kwargs["title"]))
        return {"_id": "repair-closeout", "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        return None

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_service, "load_validated_manifest", lambda project: None)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "cancel_stale_repair_tasks", lambda *args, **kwargs: asyncio.sleep(0, result=0))
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["Integrity closeout gate is blocked."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project", max_iterations=3))

    assert created_titles == ["Resolve closeout blockers"]
    assert launches == [{"task_ids": ["repair-closeout"]}]
    assert events == []


def test_autopilot_refreshes_active_worker_after_closeout_repair_task_creation(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "localRepoPath": str(tmp_path)}
    launches: list[dict] = []
    polled: list[dict] = []
    created = {"value": False}
    active_worker_snapshots = [None, {"_id": "sess-closeout", "role": "health", "status": "running"}]

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        if len(active_worker_snapshots) > 1:
            return active_worker_snapshots.pop(0)
        return active_worker_snapshots[0]

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if created["value"]:
            return [
                {"_id": "task-1", "title": "Existing completed task", "status": "done", "dependsOnTaskIds": []},
                {
                    "_id": "repair-closeout",
                    "title": "Resolve closeout blockers",
                    "status": "ready",
                    "agentRole": "health",
                    "approvalState": "granted",
                    "priority": "medium",
                    "dependsOnTaskIds": [],
                },
            ]
        return [{"_id": "task-1", "title": "Existing completed task", "status": "backlog", "dependsOnTaskIds": []}]

    async def _create_task(**kwargs):
        created["value"] = True
        return {"_id": "repair-closeout", "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        return {"convex_session_id": "session-closeout"}

    async def _poll_session_until_done(session_id: str, *, project_id=None, max_polls=None, poll_interval_seconds=None):
        polled.append({"session_id": session_id, "project_id": project_id})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service.session_lifecycle, "poll_session_until_done", _poll_session_until_done)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["Integrity closeout gate is blocked."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == []
    assert polled == [{"session_id": "sess-closeout", "project_id": "project-1"}]


def test_autopilot_creates_closeout_repair_after_planner_refresh(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "localRepoPath": str(tmp_path)}
    planner_turns: list[str] = []
    launches: list[dict] = []
    created = {"value": False}
    task_snapshots = [
        [{"_id": "task-1", "title": "Existing completed task", "status": "backlog", "dependsOnTaskIds": []}],
        [{"_id": "task-1", "title": "Existing completed task", "status": "done", "dependsOnTaskIds": []}],
    ]

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if created["value"]:
            return [
                {"_id": "task-1", "title": "Existing completed task", "status": "done", "dependsOnTaskIds": []},
                {
                    "_id": "repair-closeout",
                    "title": "Resolve closeout blockers",
                    "status": "ready",
                    "agentRole": "health",
                    "approvalState": "granted",
                    "priority": "medium",
                    "dependsOnTaskIds": [],
                },
            ]
        if len(task_snapshots) > 1:
            return task_snapshots.pop(0)
        return task_snapshots[0]

    async def _create_task(**kwargs):
        created["value"] = True
        return {"_id": "repair-closeout", "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-closeout"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _raise_decision_event(*args, **kwargs):
        return {"_id": "event-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["Integrity closeout gate is blocked."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert created["value"] is True
    assert launches == [{"task_ids": ["repair-closeout"]}]


def test_mark_project_completed_uses_repo_pipeline_when_project_record_is_stale(tmp_path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "status": "draft",
        "localRepoPath": str(tmp_path),
    }
    (tmp_path / ".ontology" / "pipelines").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "pipelines" / "soccer.yaml").write_text("name: soccer\n", encoding="utf-8")
    mutations: list[dict] = []

    async def _mutation(path: str, payload: dict):
        mutations.append({"path": path, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(autopilot_service.convex, "mutation", _mutation)

    asyncio.run(autopilot_service._mark_project_completed(project))

    assert mutations == [
        {
            "path": "projects:updateById",
            "payload": {"projectId": "project-1", "status": "ready"},
        }
    ]


def test_autopilot_creates_ontology_lifecycle_tasks_for_not_hydrated_project(monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "status": "ready",
        "localRepoPath": "/tmp/soccer-project",
        "approach": "ontology-first",
    }
    created: list[dict] = []
    sync_calls: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    tasks_state = [{"_id": "task-1", "status": "done", "dependsOnTaskIds": []}]

    async def _list_tasks(board_id: str, *, project=None):
        return list(tasks_state)

    async def _create_task(**kwargs):
        task_id = kwargs["title"].lower().replace(" ", "-")
        task = {
            "_id": task_id,
            "status": kwargs["status"],
            "title": kwargs["title"],
            "dependsOnTaskIds": kwargs.get("depends_on_task_ids") or [],
        }
        tasks_state.append(task)
        created.append(kwargs)
        return task

    async def _sync_planner_files(*args, **kwargs):
        sync_calls.append({"args": args, "kwargs": kwargs})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "not_hydrated"}

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    created_titles = [item["title"] for item in created]
    # During bootstrap (state=not_hydrated) only the populate + hydrate tasks
    # are created. Verify / research / follow-up come once hydration is live —
    # this is by design (see _is_ontology_data_bootstrap_phase) to keep health
    # agents from running before the ontology has real rows to validate.
    assert "Populate ontology pipeline steps for project sources" in created_titles
    assert "Hydrate project ontology and register active artifacts" in created_titles
    assert "Verify hydrated ontology health before research" not in created_titles
    assert "Launch ontology-backed research after hydration" not in created_titles
    assert "Propose ontology-answerable follow-up questions" not in created_titles
    assert sync_calls


def test_autopilot_creates_ontology_expansion_tasks_from_follow_up_questions(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "approach": "ontology-first",
    }
    created: list[dict] = []
    sync_calls: list[dict] = []

    (tmp_path / ".ontology").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md").write_text(
        """# Ontology-Answerable Follow-Up Questions

### 1. How different would the findings look if non-top-five domestic leagues were hydrated too?

- Classification: `requires_expansion`

### 2. Which data source would unblock a broader wage-bill analysis?

- Classification: `blocked_by_data`
""",
        encoding="utf-8",
    )

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    tasks_state = [{"_id": "task-1", "title": "Existing Task", "status": "done", "dependsOnTaskIds": []}]

    async def _list_tasks(board_id: str, *, project=None):
        return list(tasks_state)

    async def _create_task(**kwargs):
        task_id = kwargs["title"].lower().replace(" ", "-")
        task = {
            "_id": task_id,
            "status": kwargs["status"],
            "title": kwargs["title"],
            "dependsOnTaskIds": kwargs.get("depends_on_task_ids") or [],
        }
        tasks_state.append(task)
        created.append(kwargs)
        return task

    async def _sync_planner_files(*args, **kwargs):
        sync_calls.append({"args": args, "kwargs": kwargs})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    created_titles = [item["title"] for item in created]
    assert "Expand ontology coverage for: 1. How different would the findings look if non-top-five domestic leagues were hydrated too?" in created_titles
    assert "Resolve data blocker for: 2. Which data source would unblock a broader wage-bill analysis?" in created_titles
    assert sync_calls


def test_autopilot_normalizes_legacy_expansion_classification_alias(tmp_path: Path, monkeypatch):
    """Legacy `answerable_after_expansion` alias must route to the expansion task path.

    Regression test for the autopilot parser silently dropping aliases that
    `question_expansion_service.normalize_classification` already understood.
    Before consolidation, this question would produce no task even though the
    auditor flagged it as a closeout blocker — splitting the platform's truth.
    """
    project = {
        "_id": "project-1",
        "slug": "alias-project",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "approach": "ontology-first",
    }
    created: list[dict] = []

    (tmp_path / ".ontology").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md").write_text(
        """# Follow-Ups

### Does the manager-tenure effect generalize to lower-division clubs?

- Classification: `answerable_after_expansion`
""",
        encoding="utf-8",
    )

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    tasks_state: list[dict] = []

    async def _list_tasks(board_id: str, *, project=None):
        return list(tasks_state)

    async def _create_task(**kwargs):
        task = {"_id": kwargs["title"], "status": kwargs["status"], "title": kwargs["title"], "dependsOnTaskIds": []}
        tasks_state.append(task)
        created.append(kwargs)
        return task

    async def _sync_planner_files(*args, **kwargs):
        autopilot_service._active_autopilots["alias-project"] = False
        return None

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["alias-project"] = True
    autopilot_service._autopilot_configs["alias-project"] = {"auto_approve": True}

    asyncio.run(autopilot_service.run_autopilot_loop("alias-project"))

    created_titles = [item["title"] for item in created]
    assert any(t.startswith("Expand ontology coverage for:") for t in created_titles), created_titles


def test_autopilot_launches_ready_task_when_planner_does_not(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "hydrate-task",
                "status": "ready",
                "title": "Hydrate project ontology and register active artifacts",
                "approvalState": "granted",
                "priority": "high",
                "dependsOnTaskIds": [],
            }
        ]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launched.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "hydrated_on_this_device"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launched == [{"task_ids": ["hydrate-task"]}]


def test_autopilot_refreshes_task_state_after_planner_turn(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []
    planner_turns: list[str] = []
    task_snapshots = [
        [{"_id": "task-1", "status": "backlog", "title": "Prepare research plan", "dependsOnTaskIds": []}],
        [{"_id": "task-2", "status": "ready", "title": "Hydrate project ontology and register active artifacts", "approvalState": "granted", "dependsOnTaskIds": []}],
    ]

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if len(task_snapshots) > 1:
            return task_snapshots.pop(0)
        return task_snapshots[0]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launched.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert launched == [{"task_ids": ["task-2"]}]


def test_autopilot_polls_worker_revealed_by_planner_before_auto_promoting(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    planner_turns: list[str] = []
    polled: list[dict] = []
    updates: list[dict] = []
    task_snapshots = [
        [{"_id": "task-1", "status": "backlog", "title": "Prepare research plan", "dependsOnTaskIds": []}],
        [
            {
                "_id": "task-2",
                "status": "awaiting_approval",
                "title": "Continue downstream research synthesis",
                "approvalState": "pending",
                "priority": "high",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            }
        ],
    ]
    active_worker_snapshots = [None, {"_id": "sess-planner", "role": "research", "status": "running"}]

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if len(task_snapshots) > 1:
            return task_snapshots.pop(0)
        return task_snapshots[0]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        if len(active_worker_snapshots) > 1:
            return active_worker_snapshots.pop(0)
        return active_worker_snapshots[0]

    async def _poll_session_until_done(session_id: str, *, project_id=None, max_polls=None, poll_interval_seconds=None):
        polled.append({"session_id": session_id, "project_id": project_id})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.session_lifecycle, "poll_session_until_done", _poll_session_until_done)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == ["ran"]
    assert polled == [{"session_id": "sess-planner", "project_id": "project-1"}]
    assert updates == []


def test_autopilot_polls_active_worker_before_launching_new_ready_task(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launches: list[dict] = []
    polled: list[dict] = []
    planner_turns: list[str] = []
    active_worker = {"_id": "sess-1", "role": "data", "status": "running"}

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-2",
                "status": "ready",
                "title": "Hydrate project ontology and register active artifacts",
                "approvalState": "granted",
                "dependsOnTaskIds": [],
            }
        ]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return active_worker

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        return {"convex_session_id": "session-2"}

    async def _poll_session_until_done(session_id: str, *, project_id=None, max_polls=None, poll_interval_seconds=None):
        polled.append({"session_id": session_id, "project_id": project_id})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )
    monkeypatch.setattr(autopilot_service.session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launches == []
    assert polled == [{"session_id": "sess-1", "project_id": "project-1"}]


def test_autopilot_refreshes_active_worker_after_helper_changes(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launches: list[dict] = []
    polled: list[dict] = []
    active_worker_snapshots = [None, {"_id": "sess-2", "role": "health", "status": "running"}]
    task_snapshots = [
        [{"_id": "task-1", "status": "backlog", "title": "Prepare repair plan", "dependsOnTaskIds": []}],
        [{"_id": "task-2", "status": "ready", "title": "Reconcile control-plane drift and stale sessions", "approvalState": "granted", "dependsOnTaskIds": []}],
    ]

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        if len(task_snapshots) > 1:
            return task_snapshots.pop(0)
        return task_snapshots[0]

    async def _find_active_worker(project_id: str):
        if len(active_worker_snapshots) > 1:
            return active_worker_snapshots.pop(0)
        return active_worker_snapshots[0]

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        return {"convex_session_id": "session-2"}

    async def _poll_session_until_done(session_id: str, *, project_id=None, max_polls=None, poll_interval_seconds=None):
        polled.append({"session_id": session_id, "project_id": project_id})
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _ensure_control_plane_repair_tasks(project_arg, tasks, auditors):
        return True

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", lambda **kwargs: asyncio.sleep(0))
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", _ensure_control_plane_repair_tasks)
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )
    monkeypatch.setattr(autopilot_service.session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == []
    assert polled == [{"session_id": "sess-2", "project_id": "project-1"}]


def test_autopilot_filters_ready_tasks_when_ontology_auditor_is_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "research-task",
                "status": "ready",
                "title": "Launch ontology-backed research after hydration",
                "agentRole": "planner",
                "approvalState": "granted",
                "priority": "high",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "hydrate-task",
                "status": "ready",
                "title": "Hydrate project ontology and register active artifacts",
                "agentRole": "data",
                "approvalState": "granted",
                "priority": "medium",
                "dependsOnTaskIds": [],
            },
        ]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launched.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    # Background-health-governance: ontology blocked no longer excludes the
    # research task from dispatch. Both tasks reach the launcher together;
    # ordering between them is determined by priority + repair-boost and is
    # not asserted here.
    assert len(launched) == 1
    launched_ids = set(launched[0]["task_ids"])
    assert launched_ids == {"hydrate-task", "research-task"}


def test_autopilot_filters_ready_tasks_when_integrity_auditor_is_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "final-report",
                "status": "ready",
                "title": "Synthesize final report",
                "agentRole": "artifact",
                "approvalState": "granted",
                "priority": "high",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "integrity-repair",
                "status": "ready",
                "title": "Repair unsupported claims and verification evidence",
                "agentRole": "health",
                "approvalState": "granted",
                "priority": "medium",
                "dependsOnTaskIds": [],
            },
        ]

    async def _run_planner_turn(**kwargs):
        planner_turns.append("ran")
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launched.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
                "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launched == [{"task_ids": ["integrity-repair"]}]


def test_filter_ready_tasks_prioritizes_matching_repair_tasks_for_blocked_auditors():
    ready_tasks = [
        {
            "_id": "task-1",
            "title": "Verify ontology health after hydration",
            "status": "ready",
            "agentRole": "health",
            "priority": "high",
        },
        {
            "_id": "task-2",
            "title": "Repair ontology readiness blockers",
            "status": "ready",
            "agentRole": "data",
            "priority": "medium",
        },
        {
            "_id": "task-3",
            "title": "Resolve closeout blockers",
            "status": "ready",
            "agentRole": "health",
            "priority": "high",
        },
    ]

    filtered = autopilot_service._filter_ready_tasks_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        ready_tasks,
        {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        },
    )

    ranked_ids = [task["_id"] for task in sorted(filtered, key=autopilot_service._task_priority)]
    assert ranked_ids[0] == "task-2"


def test_filter_ready_tasks_keeps_research_alongside_repair_when_both_blocked():
    """Background-health-governance: ontology+integrity blocked must not starve research.

    Under the previous restrictive behavior the filter dropped the research
    task and surfaced only the two repair tasks. That trapped projects in
    repair loops while the actual research backlog grew. Now the filter
    preserves research/data/coding tasks; the priority boost still sorts
    repair tasks ahead of them.
    """
    ready_tasks = [
        {
            "_id": "ontology-repair",
            "title": "Repair ontology readiness blockers",
            "status": "ready",
            "agentRole": "data",
            "priority": "high",
        },
        {
            "_id": "integrity-repair",
            "title": "Resolve failed verification runs before trusted promotion",
            "status": "ready",
            "agentRole": "health",
            "priority": "high",
        },
        {
            "_id": "research-task",
            "title": "Continue downstream research synthesis",
            "status": "ready",
            "agentRole": "research",
            "priority": "high",
        },
    ]

    filtered = autopilot_service._filter_ready_tasks_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        ready_tasks,
        {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "blocked", "blockers": ["Failed verification runs must be resolved."]},
            "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
        },
    )

    filtered_ids = {task["_id"] for task in filtered}
    assert filtered_ids == {"ontology-repair", "integrity-repair", "research-task"}


def test_filter_ready_tasks_keeps_coding_repair_when_ontology_blocked():
    """Coding-role repair work is no longer excluded just because the ontology
    auditor is flagging. The repair still runs (priority-boosted) and the
    coding task is no longer arbitrarily dropped."""
    ready_tasks = [
        {
            "_id": "coding-repair",
            "title": "Repair analysis lineage and verification metadata",
            "status": "ready",
            "agentRole": "coding",
            "priority": "high",
        },
        {
            "_id": "health-repair",
            "title": "Resolve failed verification runs before trusted promotion",
            "status": "ready",
            "agentRole": "health",
            "priority": "high",
        },
    ]

    filtered = autopilot_service._filter_ready_tasks_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        ready_tasks,
        {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "blocked", "blockers": ["Failed verification runs must be resolved."]},
            "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
        },
    )

    filtered_ids = {task["_id"] for task in filtered}
    assert filtered_ids == {"coding-repair", "health-repair"}


def test_filter_ready_tasks_excludes_artifact_role_when_promotion_blocked():
    """The one role that *is* still gated by ontology/integrity is `artifact` —
    the promotion-class meta-synthesis/closeout work. Everything else flows."""
    ready_tasks = [
        {
            "_id": "final-memo",
            "title": "Synthesize final report",
            "status": "ready",
            "agentRole": "artifact",
            "priority": "high",
        },
        {
            "_id": "research-task",
            "title": "Continue downstream research synthesis",
            "status": "ready",
            "agentRole": "research",
            "priority": "high",
        },
        {
            "_id": "data-repair",
            "title": "Repair ontology readiness blockers",
            "status": "ready",
            "agentRole": "data",
            "priority": "high",
        },
    ]

    filtered = autopilot_service._filter_ready_tasks_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        ready_tasks,
        {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "ready", "blockers": []},
        },
    )

    filtered_ids = {task["_id"] for task in filtered}
    assert filtered_ids == {"research-task", "data-repair"}
    assert "final-memo" not in filtered_ids


def test_task_allowed_for_auditors_keeps_research_when_ontology_blocked():
    """Background-health-governance: ontology blocked must NOT block research.

    Only promotion-class (`artifact`-role) tasks are gated on ontology/integrity.
    Research/data/coding tasks continue to produce candidate work that the
    promotion gates will later evaluate.
    """
    auditors_ontology_blocked = {
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "ready", "blockers": []},
        "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
        "integrity": {"status": "ready", "blockers": []},
        "closeout": {"status": "ready", "blockers": []},
    }

    hydrate_allowed = autopilot_service._task_allowed_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        {"_id": "hydrate-task", "title": "Hydrate ontology and refresh source registry", "agentRole": "data", "priority": "medium"},
        auditors_ontology_blocked,
    )
    research_allowed = autopilot_service._task_allowed_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        {"_id": "research-task", "title": "Continue downstream research synthesis", "agentRole": "research", "priority": "high"},
        auditors_ontology_blocked,
    )
    final_memo_allowed = autopilot_service._task_allowed_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        {"_id": "final-memo", "title": "Synthesize final report", "agentRole": "artifact", "priority": "high"},
        auditors_ontology_blocked,
    )

    assert hydrate_allowed is True
    assert research_allowed is True, "research must be allowed even when ontology auditor is blocked"
    assert final_memo_allowed is False, "promotion-class artifact tasks must wait for ontology to clear"


def test_task_allowed_for_auditors_keeps_coding_when_integrity_blocked():
    """Coding tasks (refactors, helpers, repairs) keep running while integrity
    blocks. The integrity gate only stops promotion of trusted outputs."""
    auditors_integrity_blocked = {
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "ready", "blockers": []},
        "ontology": {"status": "ready", "blockers": []},
        "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
        "closeout": {"status": "ready", "blockers": []},
    }

    repair_allowed = autopilot_service._task_allowed_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        {"_id": "integrity-repair", "title": "Repair analysis lineage and verification metadata", "agentRole": "coding", "priority": "medium"},
        auditors_integrity_blocked,
    )
    coding_allowed = autopilot_service._task_allowed_for_auditors(
        {"localRepoPath": "/tmp/soccer-project"},
        {
            "_id": "coding-task",
            "title": "Refactor chart rendering helpers",
            "agentRole": "coding",
            "priority": "high",
        },
        {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
            "closeout": {"status": "ready", "blockers": []},
        },
    )

    assert repair_allowed is True
    assert coding_allowed is True, "coding tasks must continue while integrity blocks promotion"


def test_autopilot_does_not_auto_promote_unrelated_pending_task_when_ontology_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launches: list[list[str]] = []
    created: list[dict] = []
    resolved: list[dict] = []
    updates: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "research-task",
                "title": "Continue downstream research synthesis",
                "status": "awaiting_approval",
                "agentRole": "research",
                "approvalState": "pending",
                "priority": "high",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "hydrate-task",
                "title": "Hydrate ontology and refresh source registry",
                "status": "ready",
                "agentRole": "data",
                "approvalState": "granted",
                "priority": "medium",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            },
        ]

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _list_approvals(project_arg):
        return []

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-1"

    async def _resolve_approval(**kwargs):
        resolved.append(kwargs)
        return {"_id": "approval-1"}

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(task["_id"]) for task in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "resolve_approval", _resolve_approval)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == [["hydrate-task"]]
    assert created == []
    assert resolved == []
    assert updates == []


def test_autopilot_does_not_requeue_unrelated_cancelled_task_when_ontology_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launches: list[list[str]] = []
    updates: list[dict] = []
    raised_events: list[dict] = []
    handled_events: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "research-task",
                "title": "Continue downstream research synthesis",
                "status": "cancelled",
                "agentRole": "research",
                "priority": "high",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "hydrate-task",
                "title": "Hydrate ontology and refresh source registry",
                "status": "ready",
                "agentRole": "data",
                "approvalState": "granted",
                "priority": "medium",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "downstream-task",
                "title": "Launch ontology-backed research after hydration",
                "status": "backlog",
                "agentRole": "planner",
                "approvalState": "pending",
                "priority": "high",
                "runner": "default",
                "dependsOnTaskIds": ["research-task"],
            },
        ]

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _raise_decision_event(project_arg, **kwargs):
        raised_events.append(kwargs)
        return type("Event", (), {"_id": "event-1"})()

    async def _mark_decision_event(project_arg, event_id: str, status: str):
        handled_events.append(f"{event_id}:{status}")
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(task["_id"]) for task in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "mark_decision_event", _mark_decision_event)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == [["hydrate-task"]]
    assert updates == []
    assert raised_events == []
    assert handled_events == []


def test_autopilot_launches_requeued_task_in_same_iteration(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    task_id = "research-task"
    requeued = {"value": False}
    launches: list[list[str]] = []
    reconcile_calls = {"count": 0}

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": task_id,
                "title": "Continue downstream research synthesis",
                "status": "ready" if requeued["value"] else "cancelled",
                "approvalState": "granted" if requeued["value"] else None,
                "agentRole": "research",
                "priority": "high",
                "runner": "codex_cli",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "downstream-task",
                "title": "Launch downstream synthesis",
                "status": "backlog",
                "agentRole": "planner",
                "approvalState": "pending",
                "priority": "medium",
                "runner": "default",
                "dependsOnTaskIds": [task_id],
            },
        ]

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _update_task(task_id_arg: str, *, project=None, **fields):
        requeued["value"] = True
        return {"_id": task_id_arg, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

    async def _raise_decision_event(project_arg, **kwargs):
        return type("Event", (), {"_id": "event-1"})()

    async def _mark_decision_event(project_arg, event_id: str, status: str):
        return None

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append([str(item["_id"]) for item in ready_tasks])
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    async def _reconcile_project_reality(project_arg):
        reconcile_calls["count"] += 1
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["2 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "mark_decision_event", _mark_decision_event)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == [[task_id]]
    assert reconcile_calls["count"] == 1


def test_should_skip_planner_for_ready_repair_when_blocked_auditor_has_match():
    tasks = [
        {"title": "Repair ontology readiness blockers", "status": "ready"},
        {"title": "Launch ontology-backed research after hydration", "status": "ready"},
    ]
    auditors = {
        "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
        "integrity": {"status": "ready", "blockers": []},
        "closeout": {"status": "ready", "blockers": []},
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "ready", "blockers": []},
    }

    project = {"slug": "soccer-project", "localRepoPath": "/tmp/soccer-project"}
    assert autopilot_service._should_skip_planner_for_ready_repair(project, tasks, auditors) is True


def test_should_not_skip_planner_without_matching_ready_repair():
    tasks = [
        {"title": "Launch ontology-backed research after hydration", "status": "ready"},
    ]
    auditors = {
        "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
        "integrity": {"status": "ready", "blockers": []},
        "closeout": {"status": "ready", "blockers": []},
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "ready", "blockers": []},
    }

    project = {"slug": "soccer-project", "localRepoPath": "/tmp/soccer-project"}
    assert autopilot_service._should_skip_planner_for_ready_repair(project, tasks, auditors) is False


def test_autopilot_routes_planner_turn_toward_ontology_unblocking(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "title": "Repair ontology state", "status": "backlog", "dependsOnTaskIds": []}]

    async def _run_planner_turn(*, project=None, user_message=None, persist=False):
        planner_turns.append(str(user_message or ""))
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _sync_planner_files(*args, **kwargs):
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "list_decision_events", lambda *args, **kwargs: asyncio.sleep(0, result=[]))

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns
    assert "Focus only on hydration" in planner_turns[0]


def test_autopilot_routes_planner_turn_toward_integrity_repair(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    planner_turns: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "title": "Repair integrity state", "status": "backlog", "dependsOnTaskIds": []}]

    async def _run_planner_turn(*, project=None, user_message=None, persist=False):
        planner_turns.append(str(user_message or ""))
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _sync_planner_files(*args, **kwargs):
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
                "ontology": {"status": "ready", "blockers": [], "state": "hydrated_on_this_device"},
                "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
                "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "list_decision_events", lambda *args, **kwargs: asyncio.sleep(0, result=[]))

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns
    assert "Integrity is blocked" in planner_turns[0]


def test_autopilot_blocks_advance_until_audit_is_current(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": str(tmp_path)}
    planner_turns: list[dict] = []
    launches: list[dict] = []
    events: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append(kwargs)
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "status": "ready", "approvalState": "granted", "dependsOnTaskIds": []}]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(
        autopilot_service,
        "audit_gate_status",
        lambda project_root: {
            "blocked": True,
            "reason": "Autopilot is waiting for audited truth to catch up with terminal session state.",
            "staleSessionIds": ["sess-1"],
        },
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launches == []
    assert events and events[0]["event_type"] == "audit_required_before_advance"


def test_autopilot_blocks_advance_when_control_plane_auditors_are_blocked(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": str(tmp_path)}
    planner_turns: list[dict] = []
    launches: list[dict] = []
    events: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        planner_turns.append(kwargs)
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "status": "ready", "approvalState": "granted", "dependsOnTaskIds": []}]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) still marked active."]},
                "planner": {"status": "blocked", "blockers": ["1 duplicate task file(s) detected."]},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "ready", "blockers": []},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert planner_turns == []
    assert launches == []
    assert events and events[0]["event_type"] == "control_plane_auditor_blocked"


def test_autopilot_launches_ready_control_plane_repair_task_when_auditors_blocked(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": str(tmp_path)}
    launches: list[dict] = []
    events: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _run_planner_turn(**kwargs):
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "repair-task",
                "title": "Reconcile control-plane drift and stale sessions",
                "status": "ready",
                "agentRole": "health",
                "approvalState": "granted",
                "priority": "medium",
                "dependsOnTaskIds": [],
            }
        ]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"convex_session_id": "session-1"}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(
        autopilot_service,
        "reconcile_project_reality",
        lambda project_arg: asyncio.sleep(
            0,
            result={
                "removedTaskFiles": [],
                "updatedTaskIds": [],
                "repairedSessionIds": [],
                "repairedAuditSessionIds": [],
                "hasChanges": False,
            },
        ),
    )
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(
        autopilot_service,
        "build_auditor_statuses",
        lambda project_arg, *, tasks=None, active_sessions=None: asyncio.sleep(
            0,
            result={
                "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) still marked active."]},
                "planner": {"status": "blocked", "blockers": ["1 duplicate task file(s) detected."]},
                "ontology": {"status": "ready", "blockers": []},
                "integrity": {"status": "ready", "blockers": []},
                "closeout": {"status": "ready", "blockers": []},
            },
        ),
    )

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launches == [{"task_ids": ["repair-task"]}]
    assert events == []


def test_repair_stale_active_sessions_finalizes_runtime_rows(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        status="completed",
    )
    finalized: list[dict] = []

    async def _list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50):
        return [
            {
                "_id": "sess-1",
                "projectId": "project-1",
                "projectSlug": "soccer-project",
                "role": "data",
                "status": "running",
                "sessionPath": str(session_root),
            }
        ]

    async def _finalize_running_agent(session_id: str, *, status: str, ended_at: int | None = None):
        finalized.append({"session_id": session_id, "status": status})
        return None

    monkeypatch.setattr(autopilot_service.running_agent_service, "list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr(autopilot_service.running_agent_service, "finalize_running_agent", _finalize_running_agent)

    result = asyncio.run(autopilot_service._repair_stale_active_sessions(project))

    assert result == {"repairedSessionIds": ["sess-1"]}
    assert finalized == [{"session_id": "sess-1", "status": "completed"}]


def test_reconcile_project_reality_returns_consolidated_summary(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}

    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_task_files", lambda project_arg: asyncio.sleep(0, result={"removed": ["research_plan/tasks/old.md"]}))
    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_task_session_states", lambda project_arg: asyncio.sleep(0, result={"updated": ["task-1"]}))
    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_planner_metadata", lambda project_arg: asyncio.sleep(0, result={"updatedTaskIds": ["task-2"], "updatedApprovalIds": ["approval-1"]}))
    monkeypatch.setattr(reconciliation_service, "repair_agent_secret_policy_roles", lambda project_arg: asyncio.sleep(0, result={"repairedRoles": ["coding"]}))
    monkeypatch.setattr(reconciliation_service.role_runtime_service, "reconcile_role_config_aliases", lambda project_arg: {"updatedConfigPaths": ["agents/coding.yaml"]})
    monkeypatch.setattr(reconciliation_service, "repair_running_agent_status_drift", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-legacy"]}))
    monkeypatch.setattr(reconciliation_service, "repair_running_agent_role_drift", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-role"]}))
    monkeypatch.setattr(reconciliation_service, "repair_running_agent_runner_drift", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-runner"]}))
    monkeypatch.setattr(reconciliation_service, "repair_stale_active_sessions", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-1"]}))
    monkeypatch.setattr(reconciliation_service, "repair_zombie_sessions", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-zombie"]}))
    monkeypatch.setattr(reconciliation_service, "repair_stale_session_audits", lambda project_arg, project_root: asyncio.sleep(0, result={"repairedSessionIds": ["sess-2"]}))
    monkeypatch.setattr(
        reconciliation_service,
        "repair_active_ontology_registry_drift",
        lambda project_arg: asyncio.sleep(
            0,
            result={"repaired": True, "previousDuckdbPath": "/tmp/old.duckdb", "nextDuckdbPath": "/tmp/new.duckdb"},
        ),
    )
    monkeypatch.setattr(
        command_center_service,
        "persist_control_plane_snapshot",
        lambda project_arg: asyncio.sleep(0, result={"path": "research_plan/state/control_plane_snapshot.json", "generatedAt": 123}),
    )

    result = asyncio.run(reconciliation_service.reconcile_project_reality(project))

    assert result == {
        "removedTaskFiles": ["research_plan/tasks/old.md"],
        "updatedTaskIds": ["task-1", "task-2"],
        "updatedApprovalIds": ["approval-1"],
        "repairedSecretPolicyRoles": ["coding"],
        "repairedRoleConfigPaths": ["agents/coding.yaml"],
        "repairedRunningAgentStatusSessionIds": ["sess-legacy"],
        "repairedRunningAgentRoleSessionIds": ["sess-role"],
        "repairedRunningAgentRunnerSessionIds": ["sess-runner"],
        "repairedSessionIds": ["sess-1", "sess-zombie"],
        "repairedAuditSessionIds": ["sess-2"],
        "repairedOntologyArtifact": {
            "repaired": True,
            "previousDuckdbPath": "/tmp/old.duckdb",
            "nextDuckdbPath": "/tmp/new.duckdb",
        },
        "persistedControlPlaneSnapshot": {
            "path": "research_plan/state/control_plane_snapshot.json",
            "generatedAt": 123,
        },
        "hasChanges": True,
    }


def test_build_project_control_plane_status_prefers_repo_snapshot(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    snapshot_payload = {
        "snapshotVersion": command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION,
        "generatedAt": 1234567890,
        "commandCenter": {
            "projectReality": {"hasDrift": True, "taskSessionMismatchCount": 2},
            "auditors": {"session": {"status": "blocked"}, "planner": {"status": "ready"}},
        },
    }
    snapshot_path = tmp_path / "research_plan" / "state" / "control_plane_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(__import__("json").dumps(snapshot_payload, indent=2), encoding="utf-8")

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, active_only=True, limit=50: asyncio.sleep(0, result=[{"_id": "sess-1", "status": "running"}]),
    )

    async def _unexpected_project_reality_status(*args, **kwargs):
        raise AssertionError("project_reality_status should not run when repo snapshot is loaded")

    monkeypatch.setattr(reconciliation_service, "project_reality_status", _unexpected_project_reality_status)

    result = asyncio.run(reconciliation_service.build_project_control_plane_status(project))

    assert result["reality"]["hasDrift"] is True
    assert result["reality"]["taskSessionMismatchCount"] == 2
    assert result["auditors"]["session"]["status"] == "blocked"
    assert result["lane"]["available"] is False
    assert result["snapshot"]["loaded"] is True


def test_project_reality_status_reports_drift_counts(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Same Task
status: running
assigned_role: data
---

## Description

Task A.
""",
        encoding="utf-8",
    )
    (task_dir / "task-b.md").write_text(
        """---
title: Same Task
status: done
assigned_role: data
---

## Description

Duplicate task file.
""",
        encoding="utf-8",
    )

    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        status="completed",
        review_status="review",
        publish_commit_sha="abc123",
        completion_summary={
            "status": "completed",
            "assumptions_added": [],
            "assumptions_changed": [],
            "sources_used": [],
            "datasets_created": [],
            "artifacts_created": [],
            "claims_created": [],
            "verification_results": [],
            "open_questions": [],
            "blockers": [],
            "recommended_next_tasks": [],
        },
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(
            0,
            result=[
                {
                    "_id": "sess-1",
                    "projectId": "project-1",
                    "projectSlug": "soccer-project",
                    "role": "data",
                    "status": "running",
                    "sessionPath": str(session_root),
                }
            ],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-legacy", "status": "done", "canonicalStatus": "completed"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-role", "role": "developer", "canonicalRole": "coding"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-runner", "runner": "CODEX_CLI", "canonicalRunner": "codex_cli"}],
        ),
    )

    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert status["hasDrift"] is True
    assert status["duplicateTaskFileCount"] == 1
    assert status["taskSessionMismatchCount"] == 1
    assert status["staleRuntimeSessionCount"] == 1
    assert status["terminalSessionCount"] == 1
    assert status["runningAgentStatusDriftCount"] == 1
    assert status["runningAgentRoleDriftCount"] == 1
    assert status["runningAgentRunnerDriftCount"] == 1
    assert status["details"]["duplicateTaskFiles"] == ["research_plan/tasks/task-b.md"]
    assert status["details"]["taskSessionMismatchTaskIds"] == ["task-a"]
    assert status["details"]["staleRuntimeSessionIds"] == ["sess-1"]


def test_project_reality_status_does_not_report_mismatch_for_review_held_worker_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Review Held Task
status: review
assigned_role: data
latest_run_summary: Session completed and is awaiting a reviewed post-run audit before task closeout.
---

## Description

Task A.
""",
        encoding="utf-8",
    )

    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        status="completed",
        review_status="review",
        completion_summary={
            "status": "completed",
            "assumptions_added": [],
            "assumptions_changed": [],
            "sources_used": [],
            "datasets_created": [],
            "artifacts_created": [],
            "claims_created": [],
            "verification_results": [],
            "open_questions": [],
            "blockers": [],
            "recommended_next_tasks": [],
        },
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )

    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert status["taskSessionMismatchCount"] == 0
    assert status["details"]["taskSessionMismatchTaskIds"] == []


def test_project_reality_status_does_not_report_mismatch_for_planner_task_completed_by_worker_session(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Review Held Task
status: review
assigned_role: planner
latest_run_summary: Session completed and is awaiting a reviewed post-run audit before task closeout.
---

## Description

Task A.
""",
        encoding="utf-8",
    )

    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        role="data",
        status="completed",
        review_status="review",
        completion_summary={
            "status": "completed",
            "assumptions_added": [],
            "assumptions_changed": [],
            "sources_used": [],
            "datasets_created": [],
            "artifacts_created": [],
            "claims_created": [],
            "verification_results": [],
            "open_questions": [],
            "blockers": [],
            "recommended_next_tasks": [],
        },
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )

    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert status["taskSessionMismatchCount"] == 0
    assert status["details"]["taskSessionMismatchTaskIds"] == []


def test_project_reality_status_does_not_report_mismatch_for_explicitly_cancelled_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Review Held Task
status: cancelled
assigned_role: planner
latest_run_summary: Cancelled after manual closeout cleanup.
---

## Description

Task A.
""",
        encoding="utf-8",
    )

    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "planner", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        role="planner",
        status="completed",
        review_status="needs_changes",
        updated_at="2026-01-01T00:00:00Z",
        completion_summary={
            "status": "completed",
            "assumptions_added": [],
            "assumptions_changed": [],
            "sources_used": [],
            "datasets_created": [],
            "artifacts_created": [],
            "claims_created": [],
            "verification_results": [],
            "open_questions": [],
            "blockers": ["Deterministic verification failed."],
            "recommended_next_tasks": ["Fix verification failures and rerun the worker task."],
        },
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )

    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert status["taskSessionMismatchCount"] == 0
    assert status["details"]["taskSessionMismatchTaskIds"] == []


def test_launch_ready_task_falls_through_after_blocked_candidate(monkeypatch):
    project = {"slug": "demo-project"}
    ready_tasks = [
        {"_id": "task-blocked", "priority": "high"},
        {"_id": "task-launchable", "priority": "medium"},
    ]

    calls: list[str] = []

    async def _fake_execute(project_arg, tool_name, payload):
        assert project_arg is project
        assert tool_name == "launch_task_runner"
        calls.append(str(payload["task_id"]))
        if payload["task_id"] == "task-blocked":
            return {"error": "Ontology hydration state is `not_hydrated`."}
        return {"ok": True, "session_id": "sess-123"}

    monkeypatch.setattr(
        autopilot_service.planner_runtime,
        "_execute_planner_tool",
        _fake_execute,
    )

    result = asyncio.run(autopilot_service._launch_ready_task(project, ready_tasks))

    assert calls == ["task-blocked", "task-launchable"]
    assert result == {"ok": True, "session_id": "sess-123"}


def test_launch_ready_task_falls_through_after_blocked_candidate_exception(monkeypatch):
    project = {"slug": "demo-project"}
    ready_tasks = [
        {"_id": "task-blocked", "priority": "high"},
        {"_id": "task-launchable", "priority": "medium"},
    ]

    calls: list[str] = []

    async def _fake_execute(project_arg, tool_name, payload):
        assert project_arg is project
        assert tool_name == "launch_task_runner"
        calls.append(str(payload["task_id"]))
        if payload["task_id"] == "task-blocked":
            raise RuntimeError("Ontology hydration state is `not_hydrated`.")
        return {"ok": True, "session_id": "sess-456"}

    monkeypatch.setattr(
        autopilot_service.planner_runtime,
        "_execute_planner_tool",
        _fake_execute,
    )

    result = asyncio.run(autopilot_service._launch_ready_task(project, ready_tasks))

    assert calls == ["task-blocked", "task-launchable"]
    assert result == {"ok": True, "session_id": "sess-456"}


def test_ensure_control_plane_repair_task_reopens_existing_blocked_task(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
    }
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_path = task_dir / "reconcile-control-plane-drift-and-stale-sessions.md"
    task_path.write_text(
        """---
task_id: reconcile-control-plane-drift-and-stale-sessions
title: Reconcile control-plane drift and stale sessions
status: blocked
assigned_role: health
latest_run_summary: Recovered from session sess-1.
blocker_category: verification_failure
---

## Description

Repair control-plane drift.
""",
        encoding="utf-8",
    )

    async def _fake_ensure_main_board(project_arg):
        assert project_arg is project
        return {"_id": "main"}

    synced: list[str] = []

    async def _fake_sync_planner_files(project_arg, board_arg):
        assert project_arg is project
        assert board_arg == {"_id": "main"}
        synced.append("synced")

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)

    tasks = [autopilot_service.planner_service._task_to_runtime(task_path)]
    auditors = {
        "planner": {"status": "blocked", "blockers": ["task/session mismatch"]},
        "session": {"status": "ready", "blockers": []},
    }

    changed = asyncio.run(
        autopilot_service._ensure_control_plane_repair_tasks(project, tasks, auditors)
    )

    updated = autopilot_service.planner_service._task_to_runtime(task_path)
    assert changed is True
    assert updated["status"] == "ready"
    assert updated["approvalState"] == "granted"
    assert updated["blockerCategory"] is None
    assert updated["latestRunSummary"] == "Reopened by Autopilot because control-plane auditors remain blocked."
    assert synced == ["synced"]


def test_ensure_ontology_repair_task_reopens_existing_review_task(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
    }
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_path = task_dir / "repair-ontology-readiness-blockers.md"
    task_path.write_text(
        """---
task_id: repair-ontology-readiness-blockers
title: Repair ontology readiness blockers
status: review
assigned_role: data
latest_run_summary: Recovered from session sess-2.
---

## Description

Repair ontology blockers.
""",
        encoding="utf-8",
    )

    async def _fake_ensure_main_board(project_arg):
        assert project_arg is project
        return {"_id": "main"}

    synced: list[str] = []

    async def _fake_sync_planner_files(project_arg, board_arg):
        assert project_arg is project
        assert board_arg == {"_id": "main"}
        synced.append("synced")

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)

    tasks = [autopilot_service.planner_service._task_to_runtime(task_path)]
    auditors = {
        "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
    }

    changed = asyncio.run(
        autopilot_service._ensure_ontology_repair_task(project, tasks, auditors)
    )

    updated = autopilot_service.planner_service._task_to_runtime(task_path)
    assert changed is True
    assert updated["status"] == "ready"
    assert updated["approvalState"] == "granted"
    assert updated["blockerCategory"] is None
    assert updated["latestRunSummary"] == "Reopened by Autopilot because ontology readiness is still blocked."
    assert synced == ["synced"]


def test_ontology_task_specs_do_not_encourage_cross_project_harnesses():
    populate_spec = next(
        spec
        for spec in autopilot_service.ONTOLOGY_TASK_SPECS
        if spec["title"] == "Populate ontology pipeline steps for project sources"
    )
    joined = " ".join(str(item) for item in populate_spec["acceptance_criteria"]).lower()
    assert "soccer source" not in joined
    assert "smoke-test fixtures" in joined  # explicit guard against smoke-test pollution
    assert "cross-project harnesses" in joined
    assert "project-relevant source" in joined
    # Real-data gate: at least one source must fetch data, not register a stub.
    assert "actually fetches data" in joined


def test_project_reality_snapshot_returns_drift_details(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
        "activeOntologyDuckdbPath": str(tmp_path / ".ontology" / "missing.duckdb"),
    }
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Same Task
status: running
assigned_role: data
---

## Description

Task A.
""",
        encoding="utf-8",
    )
    (task_dir / "task-b.md").write_text(
        """---
title: Same Task
status: done
assigned_role: data
---

## Description

Duplicate task file.
""",
        encoding="utf-8",
    )

    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        status="completed",
        review_status="review",
        publish_commit_sha="abc123",
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(
            0,
            result=[
                {
                    "_id": "sess-1",
                    "projectId": "project-1",
                    "projectSlug": "soccer-project",
                    "role": "data",
                    "status": "running",
                    "sessionPath": str(session_root),
                }
            ],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-legacy", "status": "done", "canonicalStatus": "completed"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-role", "role": "developer", "canonicalRole": "coding"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-runner", "runner": "CODEX_CLI", "canonicalRunner": "codex_cli"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(
            0,
            result={
                "reusableArtifact": {"duckdbArtifactPath": str(tmp_path / ".ontology" / "onto.duckdb")},
                "currentDeviceArtifacts": [],
            },
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.convex,
        "query",
        lambda path, args: asyncio.sleep(
            0,
            result=[
                {
                    "_id": "policy-1",
                    "projectId": "project-1",
                    "agentRole": "developer",
                    "allowedSecretNames": ["FRED_API_KEY"],
                }
            ] if path == "agentSecretPolicies:listByProject" else None,
        ),
    )
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents" / "coding.yaml").write_text(
        """role: developer
label: Coding Agent
purpose: Build features.
runner:
  default: codex_cli
""",
        encoding="utf-8",
    )
    (tmp_path / "rail.yaml").write_text(
        """version: 1
project:
  name: Grid Study
  slug: grid-study
  default_branch: main
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
  transforms_dir: .ontology/transforms
  hydration_mode: full
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
  approval_required_for_write_runs: true
  planner_thread_mode: project
  default_planner_role: planner
frontend:
  topic_index_mode: filesystem
  artifact_index_mode: filesystem
  show_repo_tree: true
  show_task_board_snapshot: true
  default_home_view: project_home
""",
        encoding="utf-8",
    )

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))

    assert snapshot["duplicateTaskFiles"] == ["research_plan/tasks/task-b.md"]
    assert snapshot["taskSessionMismatchTaskIds"] == ["task-a"]
    assert snapshot["staleRuntimeSessionIds"] == ["sess-1"]
    assert snapshot["terminalSessionIds"] == ["sess-1"]
    assert snapshot["activeRuntimeSessionIds"] == ["sess-1"]
    assert snapshot["runningAgentStatusDrift"]["hasDrift"] is True
    assert snapshot["runningAgentStatusDrift"]["sessions"][0]["sessionId"] == "sess-legacy"
    assert snapshot["runningAgentStatusDrift"]["sessions"][0]["canonicalStatus"] == "completed"
    assert snapshot["runningAgentRoleDrift"]["hasDrift"] is True
    assert snapshot["runningAgentRoleDrift"]["sessions"][0]["sessionId"] == "sess-role"
    assert snapshot["runningAgentRoleDrift"]["sessions"][0]["canonicalRole"] == "coding"
    assert snapshot["runningAgentRunnerDrift"]["hasDrift"] is True
    assert snapshot["runningAgentRunnerDrift"]["sessions"][0]["sessionId"] == "sess-runner"
    assert snapshot["runningAgentRunnerDrift"]["sessions"][0]["canonicalRunner"] == "codex_cli"
    assert snapshot["ontologyArtifactDrift"]["hasDrift"] is True
    assert snapshot["ontologyArtifactDrift"]["reason"] == "active_ontology_path_missing_on_disk"
    assert snapshot["ontologyArtifactDrift"]["expectedDuckdbPath"] == str(tmp_path / ".ontology" / "onto.duckdb")
    assert snapshot["artifactRegistryDrift"]["hasDrift"] is False
    assert snapshot["secretPolicyRoleDrift"]["hasDrift"] is True
    assert snapshot["secretPolicyRoleDrift"]["policies"][0]["agentRole"] == "developer"
    assert snapshot["secretPolicyRoleDrift"]["policies"][0]["canonicalRole"] == "coding"
    assert snapshot["roleConfigAliasDrift"]["hasDrift"] is True
    assert snapshot["roleConfigAliasDrift"]["configs"][0]["configPath"] == "agents/coding.yaml"
    assert snapshot["roleConfigAliasDrift"]["configs"][0]["canonicalRole"] == "coding"


def test_project_reality_snapshot_ignores_explicitly_reopened_task(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
    }
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Populate ontology pipeline steps for attachable sources
status: ready
assigned_role: data
approval_state: granted
latest_run_summary: Reopened by Autopilot because the default ontology pipeline still has no executable steps.
---

## Description

Task A.
""",
        encoding="utf-8",
    )
    session_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    autopilot_service.session_lifecycle.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="task-a",
        status="completed",
        review_status="needs_changes",
        completion_summary={
            "status": "completed",
            "blockers": ["Deterministic verification failed."],
            "recommended_next_tasks": ["Fix verification failures and rerun the worker task."],
        },
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(0, result={"reusableArtifact": {}, "currentDeviceArtifacts": [], "state": "not_hydrated"}),
    )
    monkeypatch.setattr(
        reconciliation_service.convex,
        "query",
        lambda path, args: asyncio.sleep(0, result=[] if path == "agentSecretPolicies:listByProject" else None),
    )

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))

    assert snapshot["duplicateTaskFiles"] == []
    assert snapshot["taskSessionMismatchTaskIds"] == []


def test_project_reality_snapshot_uses_latest_terminal_session_per_task(tmp_path: Path, monkeypatch):
    import json

    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
    }
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task-a.md").write_text(
        """---
task_id: task-a
title: Same Task
status: done
assigned_role: data
latest_run_summary: Published commit abc123
---

## Description

Task A.
""",
        encoding="utf-8",
    )

    old_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-old")
    autopilot_service.session_lifecycle.session_files.update_state(
        old_root,
        session_id="sess-old",
        task_id="task-a",
        status="completed",
        review_status="needs_changes",
        updated_at="2026-01-01T00:00:00Z",
        completion_summary={
            "status": "completed",
            "blockers": ["Deterministic verification failed."],
            "recommended_next_tasks": ["Fix verification failures and rerun the worker task."],
        },
    )
    new_root = autopilot_service.session_lifecycle.session_files.ensure_session_root(tmp_path, "data", "sess-new")
    autopilot_service.session_lifecycle.session_files.update_state(
        new_root,
        session_id="sess-new",
        task_id="task-a",
        status="completed",
        review_status="review",
        updated_at="2026-01-02T00:00:00Z",
        publish_commit_sha="abc123",
    )
    audit_dir = tmp_path / "research_plan" / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "task-a.json").write_text(
        json.dumps(
            {
                "session": {
                    "taskId": "task-a",
                    "reviewStatus": "review",
                    "status": "completed",
                },
                "integrity": {"blocked": False},
                "currentBlocker": None,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(0, result={"reusableArtifact": {}, "currentDeviceArtifacts": [], "state": "not_hydrated"}),
    )
    monkeypatch.setattr(
        reconciliation_service.convex,
        "query",
        lambda path, args: asyncio.sleep(0, result=[] if path == "agentSecretPolicies:listByProject" else None),
    )

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))

    assert snapshot["taskSessionMismatchTaskIds"] == []


def test_project_reality_snapshot_reports_artifact_registry_drift(tmp_path: Path, monkeypatch):
    bootstrap_future_project(tmp_path, name="Artifact Drift Project", slug="artifact-drift-project")
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": str(tmp_path),
    }
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "untracked.md").write_text("# Untracked\n", encoding="utf-8")
    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan" / "state" / "artifact_lineage.json").write_text(
        """[
  {
    "artifact_path": "artifacts/missing.md",
    "artifact_type": "report",
    "title": "Missing",
    "promotion_state": "draft",
    "inputs": [],
    "scripts": [],
    "sources": [],
    "assumptions": [],
    "claims": [],
    "verification_runs": [],
    "stale_reasons": []
  }
]
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(0, result=[]),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-legacy", "status": "done", "canonicalStatus": "completed"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-role", "role": "developer", "canonicalRole": "coding"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-runner", "runner": "CODEX_CLI", "canonicalRunner": "codex_cli"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(0, result={"reusableArtifact": {}, "currentDeviceArtifacts": []}),
    )
    monkeypatch.setattr(
        reconciliation_service.convex,
        "query",
        lambda path, args: asyncio.sleep(0, result=[] if path == "agentSecretPolicies:listByProject" else None),
    )
    (tmp_path / "rail.yaml").write_text(
        """version: 1
project:
  name: Artifact Drift Project
  slug: artifact-drift-project
  default_branch: main
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
  transforms_dir: .ontology/transforms
  hydration_mode: full
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
  approval_required_for_write_runs: true
  planner_thread_mode: project
  default_planner_role: planner
frontend:
  topic_index_mode: filesystem
  artifact_index_mode: filesystem
  show_repo_tree: true
  show_task_board_snapshot: true
  default_home_view: project_home
""",
        encoding="utf-8",
    )
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents" / "coding.yaml").write_text("role: developer\n", encoding="utf-8")

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))
    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert snapshot["artifactRegistryDrift"]["hasDrift"] is True
    assert snapshot["artifactRegistryDrift"]["untrackedArtifactPaths"] == ["artifacts/untracked.md"]
    assert snapshot["artifactRegistryDrift"]["missingArtifactPaths"] == ["artifacts/missing.md"]
    assert status["artifactRegistryDriftCount"] == 2
    assert status["secretPolicyRoleDriftCount"] == 0
    assert status["roleConfigAliasDriftCount"] == 1
    assert status["runningAgentStatusDriftCount"] == 1
    assert status["runningAgentRoleDriftCount"] == 1
    assert status["runningAgentRunnerDriftCount"] == 1


def test_project_reality_snapshot_without_repo_root_preserves_control_plane_drift_shape(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": None}

    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_project_running_agents",
        lambda project_id, *, active_only=True, limit=50: asyncio.sleep(
            0,
            result=[{"_id": "sess-1", "role": "coding", "status": "running"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_status_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-legacy", "status": "done", "canonicalStatus": "completed"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_role_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-role", "role": "developer", "canonicalRole": "coding"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.running_agent_service,
        "list_running_agent_runner_drift",
        lambda project_id, *, limit=50: asyncio.sleep(
            0,
            result=[{"sessionId": "sess-runner", "runner": "CODEX_CLI", "canonicalRunner": "codex_cli"}],
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.convex,
        "query",
        lambda name, args: asyncio.sleep(
            0,
            result=[
                {
                    "_id": "policy-1",
                    "agentRole": "developer",
                    "allowedSecretNames": ["OPENAI_API_KEY"],
                }
            ]
            if name == "agentSecretPolicies:listByProject"
            else [],
        ),
    )

    snapshot = asyncio.run(
        reconciliation_service.project_reality_snapshot(project)
    )
    status = asyncio.run(
        reconciliation_service.project_reality_status(project)
    )

    assert snapshot["activeRuntimeSessionIds"] == ["sess-1"]
    assert snapshot["runningAgentStatusDrift"]["hasDrift"] is True
    assert snapshot["runningAgentStatusDrift"]["sessions"][0]["sessionId"] == "sess-legacy"
    assert snapshot["runningAgentRoleDrift"]["hasDrift"] is True
    assert snapshot["runningAgentRoleDrift"]["sessions"][0]["sessionId"] == "sess-role"
    assert snapshot["runningAgentRoleDrift"]["sessions"][0]["canonicalRole"] == "coding"
    assert snapshot["runningAgentRunnerDrift"]["hasDrift"] is True
    assert snapshot["runningAgentRunnerDrift"]["sessions"][0]["sessionId"] == "sess-runner"
    assert snapshot["runningAgentRunnerDrift"]["sessions"][0]["canonicalRunner"] == "codex_cli"
    assert snapshot["secretPolicyRoleDrift"]["hasDrift"] is True
    assert snapshot["secretPolicyRoleDrift"]["policies"][0]["agentRole"] == "developer"
    assert snapshot["secretPolicyRoleDrift"]["policies"][0]["canonicalRole"] == "coding"
    assert snapshot["ontologyArtifactDrift"] == {
        "hasDrift": False,
        "activeDuckdbPath": None,
        "expectedDuckdbPath": None,
        "reason": None,
    }
    assert snapshot["artifactRegistryDrift"] == {
        "hasDrift": False,
        "untrackedArtifactPaths": [],
        "missingArtifactPaths": [],
    }
    assert snapshot["roleConfigAliasDrift"] == {
        "hasDrift": False,
        "configs": [],
    }
    assert status["hasDrift"] is True
    assert status["runningAgentStatusDriftCount"] == 1
    assert status["runningAgentRoleDriftCount"] == 1
    assert status["runningAgentRunnerDriftCount"] == 1
    assert status["secretPolicyRoleDriftCount"] == 1
    assert status["ontologyArtifactDriftCount"] == 0
    assert status["artifactRegistryDriftCount"] == 0
    assert status["roleConfigAliasDriftCount"] == 0


def test_repair_active_ontology_registry_drift_promotes_reusable_artifact(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "status": "hydrated",
        "localRepoPath": str(tmp_path),
        "activeOntologyDuckdbPath": str(tmp_path / ".ontology" / "missing.duckdb"),
    }
    (tmp_path / ".ontology").mkdir(parents=True, exist_ok=True)
    target_duckdb = tmp_path / ".ontology" / "onto.duckdb"
    target_duckdb.write_text("", encoding="utf-8")
    promoted: list[dict[str, object]] = []

    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(
            0,
            result={
                "reusableArtifact": {
                    "ontologyArtifactPath": str(tmp_path / ".ontology" / "onto.db"),
                    "duckdbArtifactPath": str(target_duckdb),
                    "owlArtifactPath": str(tmp_path / ".ontology" / "populated_ontology.owl"),
                },
                "currentDeviceArtifacts": [],
            },
        ),
    )
    monkeypatch.setattr(
        reconciliation_service.hydration_registry_service,
        "promote_project_hydration_artifact",
        lambda **kwargs: asyncio.sleep(0, result=promoted.append(kwargs)),
    )

    result = asyncio.run(reconciliation_service.repair_active_ontology_registry_drift(project))

    assert result["repaired"] is True
    assert result["nextDuckdbPath"] == str(target_duckdb)
    assert promoted[0]["duckdb_artifact_path"] == str(target_duckdb)


def test_ensure_project_reality_repair_tasks_creates_drift_tasks(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": True,
            "details": {
                "ontologyArtifactDrift": {"hasDrift": True, "reason": "active_ontology_pointer_out_of_date"},
                "artifactRegistryDrift": {
                    "hasDrift": True,
                    "untrackedArtifactPaths": ["artifacts/untracked.md"],
                    "missingArtifactPaths": ["artifacts/missing.md"],
                },
            },
        }

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_project_reality_repair_tasks(project, []))

    titles = {str(item["title"]) for item in created}
    assert changed is True
    assert "Repair active ontology artifact pointer drift" in titles
    assert "Reconcile artifact registry drift" in titles
    assert synced == [True]


def test_ensure_project_reality_repair_tasks_is_noop_without_drift(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": False,
            "details": {
                "ontologyArtifactDrift": {"hasDrift": False},
                "artifactRegistryDrift": {"hasDrift": False},
            },
        }

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_project_reality_repair_tasks(project, []))

    assert changed is False
    assert created == []
    assert synced == []


def test_ensure_integrity_repair_tasks_creates_inadmissible_source_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": ["estimated-series", "synthetic-series"],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Resolve inadmissible sources for trusted outputs"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_unsupported_claim_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": ["claim-001", "claim-002"],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Repair unsupported claims and verification evidence"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_stale_source_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": [],
                "staleSources": ["stale-source-a", "stale-source-b"],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Refresh stale sources or rerun dependent analyses"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_failed_verification_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": ["run-001", "run-002"],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Resolve failed verification runs before trusted promotion"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_reproducibility_gap_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": ["artifacts/report.md"],
                "inadmissibleSources": [],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Repair reproducibility metadata for trusted artifacts"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_dataset_metadata_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "blocked",
                "datasetsMissingProvenance": ["artifacts/panel.csv"],
                "datasetsMissingFreshness": ["artifacts/panel.csv"],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "ready",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            },
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Repair dataset provenance and freshness metadata"
    assert created[0]["agent_role"] == "data"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_creates_analysis_metadata_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "blocked",
                "artifactsMissingLineage": ["artifacts/report.md"],
                "artifactsMissingVerificationCommands": ["artifacts/report.md"],
                "artifactsMissingVerification": ["artifacts/report.md"],
            },
            "health": {
                "status": "ready",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            },
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is True
    assert created[0]["title"] == "Repair analysis lineage and verification metadata"
    assert created[0]["agent_role"] == "coding"
    assert synced == [True]


def test_ensure_integrity_repair_tasks_defers_health_repairs_during_ontology_bootstrap(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(autopilot_service, "_is_ontology_project", lambda project_arg: True)
    monkeypatch.setattr(autopilot_service, "get_hydration_status", lambda project=None: asyncio.sleep(0, result={"state": "not_hydrated"}))
    monkeypatch.setattr(autopilot_service, "_is_ontology_data_bootstrap_phase", lambda project_arg, hydration=None: True)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "blocked",
                "missingEvidenceClaims": ["claim-001"],
                "staleSources": ["stale-source-a"],
                "failedVerificationRuns": ["run-001"],
                "reproducibilityGaps": ["artifacts/report.md"],
                "inadmissibleSources": ["estimated-series"],
            },
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is False
    assert created == []
    assert synced == []


def test_ensure_integrity_repair_tasks_is_noop_without_inadmissible_sources(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "project_root_from_record", lambda project_arg: tmp_path)
    monkeypatch.setattr(
        autopilot_service,
        "summarize_agent_workflow_health",
        lambda root: {
            "data": {
                "status": "ready",
                "datasetsMissingProvenance": [],
                "datasetsMissingFreshness": [],
            },
            "coding": {
                "status": "ready",
                "artifactsMissingLineage": [],
                "artifactsMissingVerificationCommands": [],
                "artifactsMissingVerification": [],
            },
            "health": {
                "status": "ready",
                "missingEvidenceClaims": [],
                "staleSources": [],
                "failedVerificationRuns": [],
                "reproducibilityGaps": [],
                "inadmissibleSources": [],
            }
        },
    )
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._ensure_integrity_repair_tasks(project, []))

    assert changed is False
    assert created == []
    assert synced == []


def test_github_create_blob_accepts_bytes(monkeypatch):
    service = GitHubService()
    captured: dict[str, object] = {}

    async def _request(method: str, repo: str, path: str, *, token=None, **kwargs):
        captured["method"] = method
        captured["repo"] = repo
        captured["path"] = path
        captured["json"] = kwargs.get("json")

        class _Resp:
            def json(self):
                return {"sha": "blob-sha"}

        return _Resp()

    monkeypatch.setattr(service, "_request", _request)

    sha = asyncio.run(service.create_blob("owner/repo", b"\x00\x01binary"))

    assert sha == "blob-sha"
    assert captured["path"] == "/git/blobs"
    assert captured["json"]["encoding"] == "base64"


def test_ensure_control_plane_repair_tasks_creates_reconcile_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_control_plane_repair_tasks(
            project,
            [],
            {
                "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) still marked active."]},
                "planner": {"status": "blocked", "blockers": ["1 duplicate task file(s) detected."]},
            },
        )
    )

    assert changed is True
    assert created[0]["title"] == "Reconcile control-plane drift and stale sessions"
    assert created[0]["agent_role"] == "health"
    assert "stale or missing post-run audits" in str(created[0]["description"])
    assert "non-canonical secret policy role mappings" in str(created[0]["description"])
    assert "non-canonical role config aliases" in str(created[0]["description"])
    assert "non-canonical running-agent session statuses" in str(created[0]["description"])
    assert "non-canonical running-agent session roles" in str(created[0]["description"])
    assert "duplicate task files, task/session mismatches, stale session audits, running-agent status drift, running-agent role drift, running-agent runner drift, secret policy role drift, and role config alias drift are reconciled" in created[0]["acceptance_criteria"]
    assert synced == [True]


def test_ensure_control_plane_repair_tasks_is_noop_without_blockers(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_control_plane_repair_tasks(
            project,
            [],
            {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "ready", "blockers": []},
            },
        )
    )

    assert changed is False


def test_ensure_control_plane_repair_tasks_recreates_cancelled_repair_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_control_plane_repair_tasks(
            project,
            [
                {
                    "_id": "repair-task",
                    "title": "Reconcile control-plane drift and stale sessions",
                    "status": "cancelled",
                }
            ],
            {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "blocked", "blockers": ["1 task/session state mismatch(es) detected."]},
            },
        )
    )

    assert changed is True
    assert created and created[0]["title"] == "Reconcile control-plane drift and stale sessions"
    assert synced == [True]


def test_cancel_stale_repair_tasks_keeps_control_plane_task_until_session_and_planner_are_both_ready(tmp_path: Path, monkeypatch):
    project_root = tmp_path
    (project_root / "artifacts").mkdir(parents=True, exist_ok=True)
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(project_root)}
    updates: list[dict[str, object]] = []
    synced: list[bool] = []
    task = {
        "_id": "repair-task",
        "title": "Reconcile control-plane drift and stale sessions",
        "status": "ready",
    }

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    cancelled = asyncio.run(
        autopilot_service.cancel_stale_repair_tasks(
            project,
            [task],
            {
                "session": {"status": "ready", "blockers": []},
                "planner": {"status": "blocked", "blockers": ["1 task/session state mismatch(es) detected."]},
                "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            },
        )
    )

    assert cancelled == 0
    assert updates == []
    assert synced == []
    assert synced == []


def test_ensure_closeout_repair_task_creates_closeout_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_closeout_repair_task(
            project,
            [],
            {"closeout": {"status": "blocked", "blockers": ["Integrity closeout gate is blocked."]}},
        )
    )

    assert changed is True
    assert created[0]["title"] == "Resolve closeout blockers"
    assert created[0]["agent_role"] == "health"
    assert synced == [True]


def test_ensure_closeout_repair_task_is_noop_without_blockers(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_closeout_repair_task(
            project,
            [],
            {"closeout": {"status": "ready", "blockers": []}},
        )
    )

    assert changed is False
    assert created == []
    assert synced == []


def test_ensure_ontology_repair_task_creates_ontology_task(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_ontology_repair_task(
            project,
            [],
            {"ontology": {"status": "blocked", "blockers": ["Ontology artifact exists but does not contain populated rows."]}},
        )
    )

    assert changed is True
    assert created[0]["title"] == "Repair ontology readiness blockers"
    assert created[0]["agent_role"] == "data"
    assert synced == [True]


def test_ensure_ontology_repair_task_is_noop_without_blockers(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}
    created: list[dict[str, object]] = []
    synced: list[bool] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": kwargs["title"], "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(
        autopilot_service._ensure_ontology_repair_task(
            project,
            [],
            {"ontology": {"status": "ready", "blockers": []}},
        )
    )

    assert changed is False
    assert created == []
    assert synced == []


def test_autopilot_repairs_stale_session_audits_before_blocking(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "ready", "localRepoPath": str(tmp_path)}
    planner_turns: list[str] = []
    launches: list[dict] = []
    events: list[dict] = []

    async def _get_project_by_slug(_slug: str):
        return project

    async def _run_planner_turn(*, project=None, user_message=None, persist=False):
        planner_turns.append(str(user_message or ""))
        autopilot_service._active_autopilots["soccer-project"] = False
        return None

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Continue research synthesis",
                "status": "awaiting_approval",
                "approvalState": "pending",
                "dependsOnTaskIds": [],
            }
        ]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        return {"convex_session_id": "session-1"}

    def _audit_gate_status(project_root: Path):
        return {"blocked": False, "reason": None, "staleSessionIds": []}

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    reconciled: list[str] = []
    async def _reconcile_project_reality(project_arg):
        reconciled.append(project_arg["slug"])
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": ["sess-1"],
            "hasChanges": True,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _raise_decision_event)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", _audit_gate_status)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "_closeout_gate", lambda project_arg, tasks: asyncio.sleep(0, result={"blocked": False, "reason": None}))
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", lambda project_arg: asyncio.sleep(0))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda project_arg, tasks: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda project_arg, tasks, auditors: asyncio.sleep(0, result=False))

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert reconciled and all(item == "soccer-project" for item in reconciled)
    assert planner_turns
    assert not any(
        e.get("event_type") in {"audit_required_before_advance", "control_plane_auditor_blocked"}
        for e in events
    )


def test_autopilot_reconciles_task_states_from_session_truth(tmp_path: Path, monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "ready", "localRepoPath": str(tmp_path)}
    completed: list[str] = []

    async def _get_project_by_slug(_slug: str):
        return project

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "status": "done", "approvalState": None, "dependsOnTaskIds": []}]

    async def _find_active_worker(project_id: str):
        return None

    repaired_calls: list[dict] = []

    async def _reconcile_project_reality(project_arg):
        repaired_calls.append({"project": project_arg["slug"]})
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": ["task-1"],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": True,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": False})
    monkeypatch.setattr(autopilot_service, "_closeout_gate", lambda project_arg, tasks: asyncio.sleep(0, result={"blocked": False, "reason": None}))
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", lambda project_arg: completed.append(str(project_arg["slug"])) or asyncio.sleep(0))

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": False}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert repaired_calls and all(item["project"] == "soccer-project" for item in repaired_calls)
    assert completed == ["soccer-project"]


def test_autopilot_creates_pipeline_population_task_when_pipeline_has_no_steps(tmp_path: Path, monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "approach": "ontology-first",
        "activeOntologyDuckdbPath": str(tmp_path / ".ontology" / "onto.duckdb"),
    }
    (tmp_path / ".ontology" / "pipelines").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "pipelines" / "soccer.yaml").write_text("name: soccer\nsteps: []\n", encoding="utf-8")
    (tmp_path / ".ontology").mkdir(exist_ok=True)
    (tmp_path / ".ontology" / "onto.duckdb").write_bytes(b"DUCK")
    (tmp_path / "rail.yaml").write_text(
        """version: 1
project:
  name: Soccer
  slug: soccer-project
  default_branch: main
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
  default_pipeline: soccer
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
  planner_thread_mode: project
  default_planner_role: planner
frontend:
  topic_index_mode: filesystem
  artifact_index_mode: filesystem
""",
        encoding="utf-8",
    )

    created: list[dict] = []

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    tasks_state = [{"_id": "task-1", "status": "done", "dependsOnTaskIds": []}]

    async def _list_tasks(board_id: str, *, project=None):
        return list(tasks_state)

    async def _create_task(**kwargs):
        task_id = kwargs["title"].lower().replace(" ", "-")
        task = {
            "_id": task_id,
            "status": kwargs["status"],
            "title": kwargs["title"],
            "dependsOnTaskIds": kwargs.get("depends_on_task_ids") or [],
        }
        tasks_state.append(task)
        created.append(kwargs)
        return task

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "hydrated_on_this_device"}

    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "create_task", _create_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(autopilot_service, "_ontology_has_populated_rows", lambda project: False)

    changed = asyncio.run(autopilot_service._ensure_ontology_lifecycle_tasks(project, tasks_state))

    assert changed is True
    assert any(item["title"] == "Populate ontology pipeline steps for project sources" for item in created)


def test_reconcile_ontology_lifecycle_state_advances_tasks_after_successful_hydration(monkeypatch):
    project = {
        "_id": "project-1",
        "slug": "soccer-project",
        "localRepoPath": "/tmp/soccer-project",
        "approach": "ontology-first",
    }
    tasks = [
        {
            "_id": "hydrate-task",
            "title": "Hydrate project ontology and register active artifacts",
            "status": "ready",
        },
        {
            "_id": "rerun-task",
            "title": "Rerun hydration after populating soccer pipeline",
            "status": "ready",
        },
        {
            "_id": "health-task",
            "title": "Verify hydrated ontology health before research",
            "status": "blocked",
            "description": "Blocked until hydration artifacts exist and rerun hydration after populating soccer pipeline succeeds.",
        },
        {
            "_id": "rows-task",
            "title": "Verify non-empty ontology classes after hydration rerun",
            "status": "blocked",
            "description": "Verification depends on rerun hydration after populating soccer pipeline and should not be mistaken for the hydration task itself.",
        },
        {
            "_id": "reconcile-task",
            "title": "Reconcile hydrated project metadata with empty live database state",
            "status": "blocked",
        },
        {
            "_id": "publish-task",
            "title": "Diagnose connector publish failure for hydration binary artifacts",
            "status": "ready",
        },
        {
            "_id": "provenance-task",
            "title": "Repair hydration artifact provenance and freshness gates for data workflow",
            "status": "ready",
        },
        {
            "_id": "pipeline-task",
            "title": "Implement first pass soccer pipeline steps for football data and clubelo",
            "status": "backlog",
        },
    ]
    updates: list[dict] = []
    sync_calls: list[dict] = []

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {
            "state": "hydrated_on_this_device",
            "reusableArtifact": {"duckdbArtifactPath": "/tmp/onto.duckdb"},
        }

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _update_task(task_id: str, *, project=None, **fields):
        updates.append({"task_id": task_id, **fields})
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        sync_calls.append({"args": args, "kwargs": kwargs})
        return None

    monkeypatch.setattr(autopilot_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(autopilot_service, "_duckdb_has_populated_rows", lambda path: path == "/tmp/onto.duckdb")
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "update_task", _update_task)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)

    changed = asyncio.run(autopilot_service._reconcile_ontology_lifecycle_state(project, tasks))

    assert changed is True
    by_id = {item["task_id"]: item for item in updates}
    assert by_id["hydrate-task"]["status"] == "done"
    assert by_id["rerun-task"]["status"] == "done"
    assert by_id["health-task"]["status"] == "ready"
    assert by_id["rows-task"]["status"] == "ready"
    assert by_id["reconcile-task"]["status"] == "done"
    assert by_id["publish-task"]["status"] == "done"
    assert by_id["provenance-task"]["status"] == "done"
    assert by_id["pipeline-task"]["status"] == "done"
    assert sync_calls
