from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_command_center_reconcile_endpoint_returns_repair_summary(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _reconcile_project_reality(project: dict):
        return {
            "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
            "updatedTaskIds": ["task-1"],
            "repairedSessionIds": ["sess-1"],
            "repairedAuditSessionIds": ["sess-2"],
            "hasChanges": True,
        }

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)

    response = client.post("/api/v1/projects/demo-project/command-center/reconcile")

    assert response.status_code == 200
    assert response.json() == {
        "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
        "updatedTaskIds": ["task-1"],
        "repairedSessionIds": ["sess-1"],
        "repairedAuditSessionIds": ["sess-2"],
        "hasChanges": True,
    }


def test_create_ontology_follow_up_task_endpoint_creates_expansion_task(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    synced: list[bool] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return []

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": "expand-task", "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(projects_router.planner_service, "create_task", _create_task)
    monkeypatch.setattr(projects_router.planner_service, "sync_planner_files", _sync_planner_files)

    response = client.post(
        "/api/v1/projects/demo-project/command-center/ontology-follow-ups/expand",
        json={"title": "2. Which question requires expansion?", "classification": "requires_expansion"},
    )

    assert response.status_code == 200
    assert response.json()["created"] is True
    assert created[0]["title"] == "Expand ontology coverage for: 2. Which question requires expansion?"
    assert synced == [True]


def test_create_ontology_follow_up_task_endpoint_returns_existing_task(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "existing-task",
                "title": "Resolve data blocker for: 3. Which source is missing?",
                "status": "ready",
            }
        ]

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)

    response = client.post(
        "/api/v1/projects/demo-project/command-center/ontology-follow-ups/expand",
        json={"title": "3. Which source is missing?", "classification": "blocked_by_data"},
    )

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert response.json()["task"]["_id"] == "existing-task"


def test_create_planner_task_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "almost_ready",
            "agentRole": "data",
        },
    )

    assert response.status_code == 422
    assert "Planner task status must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"status": "almost_ready"},
    )

    assert response.status_code == 422
    assert "Planner task status must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_approval_state(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "backlog",
            "agentRole": "data",
            "approvalState": "approved-ish",
        },
    )

    assert response.status_code == 422
    assert "Planner task approval state must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_approval_state(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"approvalState": "approved-ish"},
    )

    assert response.status_code == 422
    assert "Planner task approval state must be one of" in response.json()["detail"]


def test_create_project_approval_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "approved-ish",
            "requestedByRole": "planner",
        },
    )

    assert response.status_code == 422
    assert "Approval status must be one of" in response.json()["detail"]


def test_create_project_approval_rejects_unknown_type(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_session",
            "status": "pending",
            "requestedByRole": "planner",
        },
    )

    assert response.status_code == 422
    assert "Approval type must be one of" in response.json()["detail"]
