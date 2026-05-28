from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_agent_chat_prefers_repo_first_project_resolution(monkeypatch):
    import app.routers.agent as agent_router

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    async def _stream_planner_turn(*, project: dict, user_message: str, history: list[dict], model: str | None, persist: bool):
        assert project["slug"] == "demo-project"
        assert user_message == "hello"
        assert history == []
        assert persist is True
        yield {"type": "done", "assistant_message": "repo-first hello"}

    monkeypatch.setattr(agent_router.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(agent_router.planner_runtime, "stream_planner_turn", _stream_planner_turn)

    response = client.post(
        "/api/v1/agent/chat?project=demo-project",
        json={"message": "hello", "history": []},
    )

    assert response.status_code == 200
    assert "repo-first hello" in response.text
