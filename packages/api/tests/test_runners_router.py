from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_create_runner_session_blocks_research_launch_when_ontology_auditor_is_blocked(monkeypatch):
    import app.routers.runners as runners_router

    class _FakeRunner:
        async def create_session(self, task_payload):
            raise AssertionError("runner should not be called when auditors block launch")

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/project"}

    async def _list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50):
        return []

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {
                "status": "blocked",
                "blockers": ["Ontology hydration state is `not_hydrated`."],
                "state": "not_hydrated",
            },
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(runners_router, "_get_runner", lambda runner_name: _FakeRunner())
    monkeypatch.setattr("app.services.planner_service.get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr("app.services.running_agent_service.list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    response = client.post(
        "/api/v1/runners/codex_cli/sessions",
        json={
            "project_slug": "ontology-gate-project",
            "role": "research",
            "task_id": "task-1",
            "repo_url": "https://github.com/example/repo",
            "branch": "main",
            "task_description": "Write narrative findings",
            "allowed_paths": ["research_plan", "artifacts"],
            "acceptance_criteria": [],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Ontology hydration state is `not_hydrated`."


def test_create_runner_session_allows_repair_launch_when_ontology_auditor_is_blocked(monkeypatch):
    import app.routers.runners as runners_router

    class _FakeRunner:
        async def create_session(self, task_payload):
            return {"session_id": "external-default-1", "status": "running"}

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/project"}

    async def _list_project_running_agents(project_id: str, *, active_only: bool = True, limit: int = 50):
        return []

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {
                "status": "blocked",
                "blockers": ["Ontology hydration state is `not_hydrated`."],
                "state": "not_hydrated",
            },
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(runners_router, "_get_runner", lambda runner_name: _FakeRunner())
    monkeypatch.setattr("app.services.planner_service.get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr("app.services.running_agent_service.list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)

    response = client.post(
        "/api/v1/runners/codex_cli/sessions",
        json={
            "project_slug": "ontology-gate-project",
            "role": "data",
            "task_id": "task-2",
            "repo_url": "https://github.com/example/repo",
            "branch": "main",
            "task_description": "Repair pipeline and hydrate ontology",
            "allowed_paths": [".ontology", "research_plan"],
            "acceptance_criteria": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "running"
