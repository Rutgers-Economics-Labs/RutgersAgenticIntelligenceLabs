from __future__ import annotations

import asyncio


def test_create_running_agent_normalizes_role_alias(monkeypatch):
    from app.services import running_agent_service

    captured: list[dict] = []

    async def _mutation(path: str, payload: dict):
        captured.append({"path": path, "payload": payload})
        return {"sessionId": "sess-1"}

    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    session_id = asyncio.run(
        running_agent_service.create_running_agent(
            project_id="project-1",
            project_slug="demo-project",
            task_id="task-1",
            runtime_kind="codex_cli",
            role="developer",
            title="Run coding task",
        )
    )

    assert session_id == "sess-1"
    assert captured[0]["path"] == "agent:createSession"
    assert captured[0]["payload"]["role"] == "coding"


def test_create_running_agent_normalizes_legacy_status_alias(monkeypatch):
    from app.services import running_agent_service

    captured: list[dict] = []

    async def _mutation(path: str, payload: dict):
        captured.append({"path": path, "payload": payload})
        return {"sessionId": "sess-1"}

    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    asyncio.run(
        running_agent_service.create_running_agent(
            project_id="project-1",
            project_slug="demo-project",
            task_id="task-1",
            runtime_kind="codex_cli",
            role="coding",
            title="Run coding task",
            status="done",
        )
    )

    assert captured[0]["payload"]["status"] == "completed"


def test_get_running_agent_normalizes_legacy_role_alias(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:getSession"
        return {"_id": "sess-1", "role": "auditor", "status": "running"}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    session = asyncio.run(running_agent_service.get_running_agent("sess-1"))

    assert session is not None
    assert session["role"] == "health"


def test_get_running_agent_normalizes_legacy_status_alias(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:getSession"
        return {"_id": "sess-1", "role": "coding", "status": "done"}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    session = asyncio.run(running_agent_service.get_running_agent("sess-1"))

    assert session is not None
    assert session["status"] == "completed"


def test_list_project_running_agents_normalizes_legacy_role_aliases(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "developer", "status": "running"},
            {"_id": "sess-2", "role": "planner", "status": "done"},
        ]

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    sessions = asyncio.run(
        running_agent_service.list_project_running_agents(
            "project-1",
            active_only=False,
        )
    )

    assert [item["role"] for item in sessions] == ["coding", "planner"]


def test_update_running_agent_rejects_unknown_status(monkeypatch):
    from app.services import running_agent_service

    async def _mutation(path: str, payload: dict):
        raise AssertionError("Convex mutation should not be called for invalid status")

    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    try:
        asyncio.run(running_agent_service.update_running_agent("sess-1", status="almost_done"))
    except ValueError as exc:
        assert "Unsupported running-agent status" in str(exc)
    else:
        raise AssertionError("Expected update_running_agent() to reject unknown statuses")
