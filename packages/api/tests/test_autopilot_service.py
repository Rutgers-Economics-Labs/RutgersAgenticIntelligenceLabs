from __future__ import annotations

import asyncio
from pathlib import Path

from app.services import autopilot_service
from app.services import reconciliation_service
from rail.bootstrap import bootstrap_future_project


def test_autopilot_auto_approves_ready_pending_task(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project"}
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
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": task_id, **fields}

    async def _sync_planner_files(*args, **kwargs):
        return None

    async def _list_decision_events(*args, **kwargs):
        return []

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

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert created and created[0]["task_id"] == task["_id"]
    assert resolved and resolved[0]["approval_id"] == "approval-1"
    assert updates and updates[0]["approval_state"] == "granted"
    assert updates[0]["status"] == "ready"


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
    monkeypatch.setattr(
        autopilot_service,
        "_closeout_gate",
        lambda project_arg, tasks: asyncio.sleep(0, result={"blocked": True, "reason": "Integrity closeout gate is blocked."}),
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

    asyncio.run(autopilot_service.start_autopilot("soccer-project"))

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
        return [{"_id": "task-1", "title": "Existing completed task", "status": "done", "dependsOnTaskIds": []}]

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

    assert created_titles == ["Resolve closeout blockers"]
    assert launches == [{"task_ids": ["repair-closeout"]}]
    assert events == []


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
    assert "Hydrate project ontology and register active artifacts" in created_titles
    assert "Verify hydrated ontology health before research" in created_titles
    assert "Launch ontology-backed research after hydration" in created_titles
    assert "Propose ontology-answerable follow-up questions" in created_titles
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


def test_autopilot_launches_ready_task_when_planner_does_not(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []

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

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert launched == [{"task_ids": ["hydrate-task"]}]


def test_autopilot_filters_ready_tasks_when_ontology_auditor_is_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []

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

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
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

    assert launched == [{"task_ids": ["hydrate-task"]}]


def test_autopilot_filters_ready_tasks_when_integrity_auditor_is_blocked(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "name": "Soccer Project", "localRepoPath": "/tmp/soccer-project"}
    launched: list[dict] = []

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

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _sync_planner_files)
    monkeypatch.setattr(autopilot_service, "_launch_ready_task", _launch_ready_task)
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
        ready_tasks,
        {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        },
    )

    ranked_ids = [task["_id"] for task in sorted(filtered, key=autopilot_service._task_priority)]
    assert ranked_ids[0] == "task-2"


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

    assert autopilot_service._should_skip_planner_for_ready_repair(tasks, auditors) is True


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

    assert autopilot_service._should_skip_planner_for_ready_repair(tasks, auditors) is False


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
    project = {"_id": "project-1", "slug": "soccer-project", "localRepoPath": str(tmp_path)}

    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_task_files", lambda project_arg: asyncio.sleep(0, result={"removed": ["research_plan/tasks/old.md"]}))
    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_task_session_states", lambda project_arg: asyncio.sleep(0, result={"updated": ["task-1"]}))
    monkeypatch.setattr(reconciliation_service.planner_service, "reconcile_planner_metadata", lambda project_arg: asyncio.sleep(0, result={"updatedTaskIds": ["task-2"], "updatedApprovalIds": ["approval-1"]}))
    monkeypatch.setattr(reconciliation_service, "repair_agent_secret_policy_roles", lambda project_arg: asyncio.sleep(0, result={"repairedRoles": ["coding"]}))
    monkeypatch.setattr(reconciliation_service, "repair_stale_active_sessions", lambda project_arg: asyncio.sleep(0, result={"repairedSessionIds": ["sess-1"]}))
    monkeypatch.setattr(reconciliation_service, "repair_stale_session_audits", lambda project_arg, project_root: asyncio.sleep(0, result={"repairedSessionIds": ["sess-2"]}))
    monkeypatch.setattr(
        reconciliation_service,
        "repair_active_ontology_registry_drift",
        lambda project_arg: asyncio.sleep(
            0,
            result={"repaired": True, "previousDuckdbPath": "/tmp/old.duckdb", "nextDuckdbPath": "/tmp/new.duckdb"},
        ),
    )

    result = asyncio.run(reconciliation_service.reconcile_project_reality(project))

    assert result == {
        "removedTaskFiles": ["research_plan/tasks/old.md"],
        "updatedTaskIds": ["task-1", "task-2"],
        "updatedApprovalIds": ["approval-1"],
        "repairedSecretPolicyRoles": ["coding"],
        "repairedSessionIds": ["sess-1"],
        "repairedAuditSessionIds": ["sess-2"],
        "repairedOntologyArtifact": {
            "repaired": True,
            "previousDuckdbPath": "/tmp/old.duckdb",
            "nextDuckdbPath": "/tmp/new.duckdb",
        },
        "hasChanges": True,
    }


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

    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert status["hasDrift"] is True
    assert status["duplicateTaskFileCount"] == 1
    assert status["taskSessionMismatchCount"] == 1
    assert status["staleRuntimeSessionCount"] == 1
    assert status["terminalSessionCount"] == 1
    assert status["details"]["duplicateTaskFiles"] == ["research_plan/tasks/task-b.md"]
    assert status["details"]["taskSessionMismatchTaskIds"] == ["task-a"]
    assert status["details"]["staleRuntimeSessionIds"] == ["sess-1"]


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

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))

    assert snapshot["duplicateTaskFiles"] == ["research_plan/tasks/task-b.md"]
    assert snapshot["taskSessionMismatchTaskIds"] == ["task-a"]
    assert snapshot["staleRuntimeSessionIds"] == ["sess-1"]
    assert snapshot["terminalSessionIds"] == ["sess-1"]
    assert snapshot["activeRuntimeSessionIds"] == ["sess-1"]
    assert snapshot["ontologyArtifactDrift"]["hasDrift"] is True
    assert snapshot["ontologyArtifactDrift"]["reason"] == "active_ontology_path_missing_on_disk"
    assert snapshot["ontologyArtifactDrift"]["expectedDuckdbPath"] == str(tmp_path / ".ontology" / "onto.duckdb")
    assert snapshot["artifactRegistryDrift"]["hasDrift"] is False


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
        reconciliation_service.hydration_registry_service,
        "get_hydration_status",
        lambda **kwargs: asyncio.sleep(0, result={"reusableArtifact": {}, "currentDeviceArtifacts": []}),
    )

    snapshot = asyncio.run(reconciliation_service.project_reality_snapshot(project))
    status = asyncio.run(reconciliation_service.project_reality_status(project))

    assert snapshot["artifactRegistryDrift"]["hasDrift"] is True
    assert snapshot["artifactRegistryDrift"]["untrackedArtifactPaths"] == ["artifacts/untracked.md"]
    assert snapshot["artifactRegistryDrift"]["missingArtifactPaths"] == ["artifacts/missing.md"]
    assert status["artifactRegistryDriftCount"] == 2


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
    assert created == []
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
        return [{"_id": "task-1", "status": "ready", "approvalState": "granted", "dependsOnTaskIds": []}]

    async def _raise_decision_event(project_arg, **kwargs):
        events.append(kwargs)
        autopilot_service._active_autopilots["soccer-project"] = False
        return {"_id": "event-1"}

    async def _launch_ready_task(project_arg, ready_tasks: list[dict]):
        launches.append({"task_ids": [str(item["_id"]) for item in ready_tasks]})
        return {"convex_session_id": "session-1"}

    def _audit_gate_status(project_root: Path):
        return {"blocked": False, "reason": None, "staleSessionIds": []}

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

    autopilot_service._active_autopilots["soccer-project"] = True
    autopilot_service._autopilot_configs["soccer-project"] = {"auto_approve": True}
    autopilot_service._wake_events["soccer-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert reconciled == ["soccer-project"]
    assert planner_turns
    assert events == []


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

    assert repaired_calls == [{"project": "soccer-project"}]
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
    assert any(item["title"] == "Populate ontology pipeline steps for attachable sources" for item in created)


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
