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
            "updatedApprovalIds": ["approval-1"],
            "repairedSecretPolicyRoles": ["coding"],
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
        "updatedApprovalIds": ["approval-1"],
        "repairedSecretPolicyRoles": ["coding"],
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


def test_create_planner_task_rejects_unknown_runner(monkeypatch):
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
            "runner": "magic_runner",
        },
    )

    assert response.status_code == 422
    assert "Planner task runner must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_runner(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"runner": "magic_runner"},
    )

    assert response.status_code == 422
    assert "Planner task runner must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_priority(monkeypatch):
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
            "priority": "urgent",
        },
    )

    assert response.status_code == 422
    assert "Planner task priority must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_priority(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"priority": "urgent"},
    )

    assert response.status_code == 422
    assert "Planner task priority must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_agent_role(monkeypatch):
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
            "agentRole": "writer",
        },
    )

    assert response.status_code == 422
    assert "Planner task agent role must be one of" in response.json()["detail"]


def test_create_planner_task_normalizes_agent_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    synced: list[bool] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg, session_id=None):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": "task-1", "agentRole": kwargs["agent_role"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "create_task", _create_task)
    monkeypatch.setattr(projects_router.planner_service, "sync_planner_files", _sync_planner_files)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Alias task",
            "description": "Should normalize role alias",
            "status": "backlog",
            "agentRole": "developer",
        },
    )

    assert response.status_code == 200
    assert created[0]["agent_role"] == "coding"
    assert response.json()["agentRole"] == "coding"
    assert synced == [True]


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


def test_create_project_approval_rejects_unknown_requested_by_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "pending",
            "requestedByRole": "writer",
        },
    )

    assert response.status_code == 422
    assert "Approval requestedByRole must be one of" in response.json()["detail"]


def test_create_project_approval_normalizes_requested_by_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    wakes: list[str] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-1"

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr("app.services.autopilot_service.trigger_wake", lambda slug: wakes.append(slug))

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "pending",
            "requestedByRole": "auditor",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"approvalId": "approval-1"}
    assert created[0]["requested_by_role"] == "health"
    assert wakes == ["demo-project"]


def test_create_runner_session_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "writer",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 422
    assert "Runner session role must be one of" in response.json()["detail"]


def test_create_runner_session_normalizes_role_aliases(monkeypatch):
    import app.routers.projects as projects_router
    from app.runners import session_lifecycle

    created: list[dict] = []
    polled: list[tuple[str, str]] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    async def _create_runner_session(**kwargs):
        created.append(kwargs)
        return {"convex_session_id": "sess-1", "status": "queued"}

    async def _poll_session_until_done(session_id: str, project_id: str | None = None):
        polled.append((session_id, str(project_id)))
        return None

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(session_lifecycle, "create_runner_session", _create_runner_session)
    monkeypatch.setattr(session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "developer",
            "agentRoleForSecrets": "auditor",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 200
    assert created[0]["role"] == "coding"
    assert created[0]["agent_role_for_secrets"] == "health"
    assert polled == [("sess-1", "project-1")]


def test_create_runner_session_rejects_unknown_secret_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "data",
            "agentRoleForSecrets": "writer",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 422
    assert "Runner agentRoleForSecrets must be one of" in response.json()["detail"]


def test_append_planner_message_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/planner/messages",
        json={
            "role": "narrator",
            "content": "hello",
        },
    )

    assert response.status_code == 422
    assert "Planner message role must be one of" in response.json()["detail"]


def test_append_planner_message_normalizes_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    appended: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_planner_thread(project_id: str):
        return "planner"

    async def _append_planner_message(**kwargs):
        appended.append(kwargs)
        return None

    async def _list_planner_messages(project_arg, thread_id: str = "planner", limit: int = 200):
        return [{"role": "research", "content": "hello", "messageType": "chat"}]

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_planner_thread", _ensure_planner_thread)
    monkeypatch.setattr(projects_router.planner_service, "append_planner_message", _append_planner_message)
    monkeypatch.setattr(projects_router.planner_service, "list_planner_messages", _list_planner_messages)

    response = client.post(
        "/api/v1/projects/demo-project/planner/messages",
        json={
            "role": "researcher",
            "content": "hello",
        },
    )

    assert response.status_code == 200
    assert appended[0]["role"] == "research"


def test_worker_update_planner_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/planner/worker-update",
        json={
            "role": "narrator",
            "message": "done",
        },
    )

    assert response.status_code == 422
    assert "Worker update role must be one of" in response.json()["detail"]


def test_worker_update_planner_normalizes_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    appended: list[dict] = []
    wakes: list[str] = []

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _append_planner_message(**kwargs):
        appended.append(kwargs)
        return None

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "append_planner_message", _append_planner_message)
    monkeypatch.setattr("app.services.autopilot_service.trigger_wake", lambda slug: wakes.append(slug))

    response = client.post(
        "/api/v1/projects/demo-project/planner/worker-update",
        json={
            "role": "auditor",
            "message": "done",
        },
    )

    assert response.status_code == 200
    assert appended[0]["role"] == "health"
    assert wakes == ["demo-project"]
