from __future__ import annotations

import asyncio

from app.services import autopilot_service


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

    asyncio.run(autopilot_service.run_autopilot_loop("soccer-project"))

    assert created and created[0]["task_id"] == task["_id"]
    assert resolved and resolved[0]["approval_id"] == "approval-1"
    assert updates and updates[0]["approval_state"] == "granted"
    assert updates[0]["status"] == "ready"


def test_start_autopilot_marks_project_completed_when_all_tasks_terminal(monkeypatch):
    project = {"_id": "project-1", "slug": "soccer-project", "status": "draft", "pipelineConfigSlug": "soccer-pipeline"}
    mutations: list[dict] = []
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

    async def _mutation(path: str, payload: dict):
        mutations.append({"path": path, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _run_planner_turn)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(autopilot_service.convex, "mutation", _mutation)

    asyncio.run(autopilot_service.start_autopilot("soccer-project"))

    assert any(
        item["path"] == "projects:updateById" and item["payload"]["status"] == "ready"
        for item in mutations
    )
    assert planner_turns == []
    assert autopilot_service._active_autopilots.get("soccer-project") is False


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
