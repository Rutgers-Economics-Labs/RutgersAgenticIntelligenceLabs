"""
Tests for task board, task, task event, and approval storage (WO-F3.3).
Covers: planner_service helpers, and the projects router endpoints
that expose the task board and approvals surfaces.
"""
import json

import httpx
import pytest

pytestmark = pytest.mark.asyncio

PROJECT_ID = "project-id-abc"
BOARD_ID = "board-id-xyz"
TASK_ID = "task-id-001"
APPROVAL_ID = "approval-id-111"

PROJECT_DOC = {
    "_id": PROJECT_ID,
    "name": "Test Project",
    "slug": "test-project",
    "status": "ready",
    "localRepoPath": None,
    "apiConfigSlugs": [],
}

BOARD_DOC = {
    "_id": BOARD_ID,
    "projectId": PROJECT_ID,
    "title": "Main Board",
    "status": "active",
    "createdAt": 1000,
    "updatedAt": 1000,
}

TASK_DOC = {
    "_id": TASK_ID,
    "boardId": BOARD_ID,
    "projectId": PROJECT_ID,
    "title": "Add county labor source",
    "description": "Add and validate a new county labor data source.",
    "status": "backlog",
    "agentRole": "data",
    "repoPaths": [".ontology/sources/county_labor.yaml"],
    "acceptanceCriteria": ["YAML validates", "dry run passes"],
    "dependsOnTaskIds": [],
    "approvalState": None,
    "gitSnapshotPath": None,
    "createdAt": 1000,
    "updatedAt": 1000,
}

APPROVAL_DOC = {
    "_id": APPROVAL_ID,
    "projectId": PROJECT_ID,
    "taskId": TASK_ID,
    "approvalType": "run_task",
    "status": "pending",
    "requestedByRole": "planner",
    "requestedAt": 1000,
    "resolvedAt": None,
}


def _query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    args = payload.get("args", {})

    if path in ("projects:get", "projects:getBySlug"):
        return httpx.Response(200, json={"value": PROJECT_DOC})
    if path == "taskBoards:listByProject":
        return httpx.Response(200, json={"value": [BOARD_DOC]})
    if path == "tasks:listByBoard":
        return httpx.Response(200, json={"value": [TASK_DOC]})
    if path == "taskEvents:listByTask":
        return httpx.Response(200, json={"value": []})
    if path == "approvals:listByProject":
        return httpx.Response(200, json={"value": [APPROVAL_DOC]})
    if path == "plannerMessages:listByProjectThread":
        return httpx.Response(200, json={"value": []})

    return httpx.Response(200, json={"value": None})


def _mutation_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")

    if path == "tasks:create":
        return httpx.Response(200, json={"value": TASK_ID})
    if path == "taskEvents:append":
        return httpx.Response(200, json={"value": "event-id-1"})
    if path == "tasks:update":
        return httpx.Response(200, json={"value": None})
    if path == "approvals:create":
        return httpx.Response(200, json={"value": APPROVAL_ID})
    if path == "approvals:resolve":
        return httpx.Response(200, json={"value": None})

    return httpx.Response(200, json={"value": "ok"})


# ---------------------------------------------------------------------------
# Task board endpoints
# ---------------------------------------------------------------------------


async def test_get_planner_board(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)

    resp = await client.get("/api/v1/projects/test-project/planner/board")
    assert resp.status_code == 200
    data = resp.json()
    assert data["board"]["_id"] == BOARD_ID
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["_id"] == TASK_ID


async def test_create_planner_task(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation_dispatch)

    resp = await client.post(
        "/api/v1/projects/test-project/planner/tasks",
        json={
            "title": "Add county labor source",
            "description": "Add and validate a new county labor data source.",
            "status": "backlog",
            "agentRole": "data",
            "repoPaths": [".ontology/sources/county_labor.yaml"],
            "acceptanceCriteria": ["YAML validates", "dry run passes"],
        },
    )
    assert resp.status_code == 200
    task = resp.json()
    assert task["_id"] == TASK_ID
    assert task["status"] == "backlog"


async def test_update_planner_task(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation_dispatch)

    resp = await client.patch(
        f"/api/v1/projects/test-project/planner/tasks/{TASK_ID}",
        json={"status": "ready"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Approval endpoints
# ---------------------------------------------------------------------------


async def test_list_approvals(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)

    resp = await client.get("/api/v1/projects/test-project/approvals")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["approvals"]) == 1
    assert data["approvals"][0]["approvalType"] == "run_task"
    assert data["approvals"][0]["status"] == "pending"


async def test_create_approval(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation_dispatch)

    resp = await client.post(
        "/api/v1/projects/test-project/approvals",
        json={
            "taskId": TASK_ID,
            "approvalType": "run_task",
            "status": "pending",
            "requestedByRole": "planner",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["approvalId"] == APPROVAL_ID


async def test_resolve_approval_approved(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation_dispatch)

    resp = await client.post(
        f"/api/v1/projects/test-project/approvals/{APPROVAL_ID}/resolve",
        json={"status": "approved", "grantedByUserId": "user-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approvalId"] == APPROVAL_ID
    assert data["status"] == "approved"


async def test_resolve_approval_rejected(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation_dispatch)

    resp = await client.post(
        f"/api/v1/projects/test-project/approvals/{APPROVAL_ID}/resolve",
        json={"status": "rejected"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# planner_service unit-level tests
# ---------------------------------------------------------------------------


async def test_ensure_main_board_creates_when_empty(convex_mock):
    """ensure_main_board creates a board when none exist for the project."""
    from app.services import planner_service

    call_count = {"n": 0}

    def _dispatch(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "taskBoards:listByProject":
            # First call returns empty; second call returns the created board
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(200, json={"value": []})
            return httpx.Response(200, json={"value": [BOARD_DOC]})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_dispatch)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": BOARD_ID})
    )

    board = await planner_service.ensure_main_board(PROJECT_ID)
    assert board["_id"] == BOARD_ID


async def test_create_task_emits_created_event(convex_mock):
    """create_task should insert the task and emit a 'created' taskEvent."""
    from app.services import planner_service

    mutations_called = []

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "tasks:listByBoard":
            return httpx.Response(200, json={"value": [TASK_DOC]})
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append(payload.get("path"))
        if payload.get("path") == "tasks:create":
            return httpx.Response(200, json={"value": TASK_ID})
        return httpx.Response(200, json={"value": "ok"})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    task = await planner_service.create_task(
        board_id=BOARD_ID,
        project_id=PROJECT_ID,
        title="Add county labor source",
        description="Desc",
        status="backlog",
        agent_role="data",
    )

    assert "tasks:create" in mutations_called
    assert "taskEvents:append" in mutations_called
    assert task["_id"] == TASK_ID


async def test_update_task_emits_status_changed_event(convex_mock):
    """update_task should emit a status_changed taskEvent when status changes."""
    from app.services import planner_service

    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append(payload.get("path"))
        return httpx.Response(200, json={"value": "ok"})

    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    await planner_service.update_task(TASK_ID, status="ready")

    assert "tasks:update" in mutations_called
    assert "taskEvents:append" in mutations_called


async def test_update_task_no_event_without_status_change(convex_mock):
    """update_task with no status field should not emit a taskEvent."""
    from app.services import planner_service

    mutations_called = []

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        mutations_called.append(payload.get("path"))
        return httpx.Response(200, json={"value": "ok"})

    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    await planner_service.update_task(TASK_ID, priority="high")

    assert "tasks:update" in mutations_called
    assert "taskEvents:append" not in mutations_called
