from __future__ import annotations

import asyncio

import httpx


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


def test_create_running_agent_normalizes_runner_name(monkeypatch):
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
            runtime_kind="CODEX_CLI",
            role="coding",
            title="Run coding task",
        )
    )

    assert captured[0]["payload"]["runner"] == "codex_cli"
    assert captured[0]["payload"]["model"] == "runtime:codex_cli"


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


def test_get_running_agent_normalizes_runner_name(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:getSession"
        return {"_id": "sess-1", "role": "coding", "status": "running", "runner": "CODEX_CLI"}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    session = asyncio.run(running_agent_service.get_running_agent("sess-1"))

    assert session is not None
    assert session["runner"] == "codex_cli"


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


def test_list_project_running_agents_returns_empty_on_convex_timeout(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    sessions = asyncio.run(
        running_agent_service.list_project_running_agents(
            "project-1",
            active_only=False,
        )
    )

    assert sessions == []


def test_create_running_agent_rejects_unknown_runner(monkeypatch):
    from app.services import running_agent_service

    async def _mutation(path: str, payload: dict):
        raise AssertionError("Convex mutation should not be called for invalid runner")

    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    try:
        asyncio.run(
            running_agent_service.create_running_agent(
                project_id="project-1",
                project_slug="demo-project",
                task_id="task-1",
                runtime_kind="writerbot",
                role="coding",
                title="Run coding task",
            )
        )
    except ValueError as exc:
        assert "Unsupported running-agent runner" in str(exc)
    else:
        raise AssertionError("Expected create_running_agent() to reject unknown runners")


def test_create_running_agent_falls_back_to_local_state_on_convex_timeout(monkeypatch):
    from app.services import running_agent_service

    async def _mutation(path: str, payload: dict):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)
    monkeypatch.setattr(running_agent_service, "_LOCAL_RUNNING_AGENTS", {})

    session_id = asyncio.run(
        running_agent_service.create_running_agent(
            project_id="project-1",
            project_slug="demo-project",
            task_id="task-1",
            runtime_kind="claude_code",
            role="coding",
            title="Run coding task",
        )
    )

    assert session_id.startswith("local_runner_")
    session = asyncio.run(running_agent_service.get_running_agent(session_id))
    assert session is not None
    assert session["_id"] == session_id
    assert session["projectId"] == "project-1"
    assert session["runner"] == "claude_code"
    assert session["status"] == "queued"


def test_update_and_finalize_local_running_agent(monkeypatch):
    from app.services import running_agent_service

    monkeypatch.setattr(
        running_agent_service,
        "_LOCAL_RUNNING_AGENTS",
        {
            "local_runner_abc123": {
                "_id": "local_runner_abc123",
                "projectId": "project-1",
                "projectSlug": "demo-project",
                "taskId": "task-1",
                "runner": "claude_code",
                "role": "coding",
                "title": "Run coding task",
                "externalSessionId": "",
                "sessionPath": "",
                "status": "queued",
            }
        },
    )

    asyncio.run(
        running_agent_service.update_running_agent(
            "local_runner_abc123",
            status="running",
            externalSessionId="claude_code_123",
        )
    )
    updated = asyncio.run(running_agent_service.get_running_agent("local_runner_abc123"))
    assert updated is not None
    assert updated["status"] == "running"
    assert updated["externalSessionId"] == "claude_code_123"

    asyncio.run(
        running_agent_service.finalize_running_agent(
            "local_runner_abc123",
            status="cancelled",
        )
    )
    finalized = asyncio.run(running_agent_service.get_running_agent("local_runner_abc123"))
    assert finalized is not None
    assert finalized["status"] == "cancelled"


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


def test_list_running_agent_status_drift_reports_legacy_status_aliases(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "coding", "status": "done"},
            {"_id": "sess-2", "role": "coding", "status": "completed"},
        ]

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    drift = asyncio.run(running_agent_service.list_running_agent_status_drift("project-1"))

    assert drift == [{"sessionId": "sess-1", "status": "done", "canonicalStatus": "completed"}]


def test_list_running_agent_role_drift_reports_legacy_role_aliases(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "developer", "status": "running"},
            {"_id": "sess-2", "role": "coding", "status": "running"},
        ]

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    drift = asyncio.run(running_agent_service.list_running_agent_role_drift("project-1"))

    assert drift == [{"sessionId": "sess-1", "role": "developer", "canonicalRole": "coding"}]


def test_list_running_agent_runner_drift_reports_legacy_runner_aliases(monkeypatch):
    from app.services import running_agent_service

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "coding", "runner": "CODEX_CLI", "status": "running"},
            {"_id": "sess-2", "role": "coding", "runner": "codex_cli", "status": "running"},
        ]

    monkeypatch.setattr(running_agent_service.convex, "query", _query)

    drift = asyncio.run(running_agent_service.list_running_agent_runner_drift("project-1"))

    assert drift == [{"sessionId": "sess-1", "runner": "CODEX_CLI", "canonicalRunner": "codex_cli"}]


def test_repair_running_agent_status_drift_updates_legacy_status_aliases(monkeypatch):
    from app.services import running_agent_service

    mutations: list[dict] = []

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "coding", "status": "done"},
            {"_id": "sess-2", "role": "coding", "status": "completed"},
        ]

    async def _mutation(path: str, payload: dict):
        mutations.append({"path": path, "payload": payload})
        return {}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)
    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    result = asyncio.run(running_agent_service.repair_running_agent_status_drift("project-1"))

    assert result == {"repairedSessionIds": ["sess-1"]}
    assert mutations == [
        {
            "path": "agent:updateSessionState",
            "payload": {"sessionId": "sess-1", "status": "completed"},
        }
    ]


def test_repair_running_agent_role_drift_updates_legacy_role_aliases(monkeypatch):
    from app.services import running_agent_service

    mutations: list[dict] = []

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "developer", "status": "running"},
            {"_id": "sess-2", "role": "coding", "status": "running"},
        ]

    async def _mutation(path: str, payload: dict):
        mutations.append({"path": path, "payload": payload})
        return {}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)
    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    result = asyncio.run(running_agent_service.repair_running_agent_role_drift("project-1"))

    assert result == {"repairedSessionIds": ["sess-1"]}
    assert mutations == [
        {
            "path": "agent:updateSession",
            "payload": {"sessionId": "sess-1", "role": "coding"},
        }
    ]


def test_repair_running_agent_runner_drift_updates_legacy_runner_aliases(monkeypatch):
    from app.services import running_agent_service

    mutations: list[dict] = []

    async def _query(path: str, payload: dict):
        assert path == "agent:listByProjectId"
        return [
            {"_id": "sess-1", "role": "coding", "runner": "CODEX_CLI", "status": "running"},
            {"_id": "sess-2", "role": "coding", "runner": "codex_cli", "status": "running"},
        ]

    async def _mutation(path: str, payload: dict):
        mutations.append({"path": path, "payload": payload})
        return {}

    monkeypatch.setattr(running_agent_service.convex, "query", _query)
    monkeypatch.setattr(running_agent_service.convex, "mutation", _mutation)

    result = asyncio.run(running_agent_service.repair_running_agent_runner_drift("project-1"))

    assert result == {"repairedSessionIds": ["sess-1"]}
    assert mutations == [
        {
            "path": "agent:updateSession",
            "payload": {"sessionId": "sess-1", "runner": "codex_cli"},
        }
    ]
