from __future__ import annotations

import pytest

from app.routers import questions as questions_router
from app.services import project_artifacts_service
from app.services import sql_service


pytestmark = pytest.mark.asyncio


async def test_run_sql_uses_repo_first_artifacts_for_local_project(monkeypatch):
    seen: dict[str, object] = {}

    async def _resolve(project_id: str):
        seen["project_id"] = project_id
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_id,
            db_path="/tmp/demo/onto.db",
            owl_path=None,
            duckdb_path="/tmp/demo/onto.duckdb",
            embeddings_path="/tmp/demo/embeddings.db",
        )

    monkeypatch.setattr(project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(sql_service, "set_path", lambda path: seen.setdefault("duckdb_path", path))
    monkeypatch.setattr(sql_service, "run_query", lambda query: {"rows": [{"value": 1}], "query": query})

    result = await questions_router._execute_tool(
        "run_sql",
        {"query": "select 1 as value", "project_id": "local:demo-project"},
    )

    assert seen == {
        "project_id": "local:demo-project",
        "duckdb_path": "/tmp/demo/onto.duckdb",
    }
    assert result["rows"] == [{"value": 1}]


async def test_save_to_knowledge_base_uses_project_slug_for_local_project(monkeypatch):
    captured: dict[str, object] = {}

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    async def _query(path: str, payload: dict):
        if path in {"projects:get", "projects:getById"}:
            return None
        raise AssertionError(path)

    async def _mutation(path: str, payload: dict):
        captured["path"] = path
        captured["payload"] = payload
        return "doc-123"

    monkeypatch.setattr(questions_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(questions_router.convex, "query", _query)
    monkeypatch.setattr(questions_router.convex, "mutation", _mutation)

    result = await questions_router._execute_tool(
        "save_to_knowledge_base",
        {
            "name": "Repo-first note",
            "content": "Persist this finding.",
            "project_id": "local:demo-project",
        },
    )

    assert result == {"saved": True, "id": "doc-123", "name": "Repo-first note"}
    assert captured["path"] == "context:create"
    assert captured["payload"]["projectSlug"] == "demo-project"
    assert "projectId" not in captured["payload"]
    assert "createdAt" not in captured["payload"]
    assert "updatedAt" not in captured["payload"]


async def test_search_context_uses_project_slug_for_local_project(monkeypatch):
    captured: dict[str, object] = {}

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    async def _query(path: str, payload: dict):
        if path == "projects:get":
            return None
        if path == "projects:getById":
            return None
        if path == "context:list":
            captured["payload"] = payload
            return [
                {"name": "Queue Note", "type": "text", "content": "Queue backlogs increased in 2024."},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(questions_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(questions_router.convex, "query", _query)

    result = await questions_router._execute_tool(
        "search_context",
        {"query": "queue", "project_id": "local:demo-project"},
    )

    assert captured["payload"] == {"projectSlug": "demo-project"}
    assert result["results"][0]["name"] == "Queue Note"


async def test_resolve_project_record_prefers_repo_first_local_project(monkeypatch):
    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {"_id": "local:demo-project", "slug": "demo-project", "localRepoPath": "/tmp/demo-project"}

    async def _query(path: str, payload: dict):
        raise AssertionError((path, payload))

    monkeypatch.setattr(questions_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(questions_router.convex, "query", _query)

    project = await questions_router._resolve_project_record("local:demo-project")

    assert project["_id"] == "local:demo-project"
