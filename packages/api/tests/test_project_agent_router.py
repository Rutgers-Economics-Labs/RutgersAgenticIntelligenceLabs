from __future__ import annotations

import pytest

from app.routers import project_agent as project_agent_router
from rail.bootstrap import bootstrap_future_project
from rail.manifest import load_manifest


pytestmark = pytest.mark.asyncio


async def test_get_project_info_uses_repo_first_local_project(monkeypatch):
    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {
            "_id": "local:demo-project",
            "name": "Demo Project",
            "slug": "demo-project",
            "status": "ready",
            "ontologyConfigSlug": "demo-ontology",
            "pipelineConfigSlug": "demo-pipeline",
            "apiConfigSlugs": ["demo-source"],
            "localRepoPath": "/tmp/demo-project",
        }

    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    result = await project_agent_router._execute_project_tool("get_project_info", {}, "local:demo-project")

    assert result == {
        "name": "Demo Project",
        "slug": "demo-project",
        "status": "ready",
        "ontologyConfigSlug": "demo-ontology",
        "pipelineConfigSlug": "demo-pipeline",
        "apiConfigSlugs": ["demo-source"],
    }


async def test_link_pipeline_persists_to_local_manifest(monkeypatch, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    project = {
        "_id": "local:demo-project",
        "name": "Demo Project",
        "slug": "demo-project",
        "status": "draft",
        "localRepoPath": str(root),
        "apiConfigSlugs": [],
    }

    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return project

    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(
        project_agent_router.planner_service,
        "project_root_from_record",
        lambda record: root,
    )

    result = await project_agent_router._execute_project_tool(
        "link_pipeline",
        {"slug": "demo-pipeline"},
        "local:demo-project",
    )

    manifest = load_manifest(root)

    assert result == {"linked": True, "pipelineConfigSlug": "demo-pipeline"}
    assert manifest.hydration.default_pipeline == "demo-pipeline"


async def test_add_data_source_persists_linked_sources_to_local_manifest(monkeypatch, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    project = {
        "_id": "local:demo-project",
        "name": "Demo Project",
        "slug": "demo-project",
        "status": "draft",
        "localRepoPath": str(root),
        "apiConfigSlugs": ["existing-source"],
    }

    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return project

    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(
        project_agent_router.planner_service,
        "project_root_from_record",
        lambda record: root,
    )

    result = await project_agent_router._execute_project_tool(
        "add_data_source",
        {"slug": "new-source"},
        "local:demo-project",
    )

    manifest = load_manifest(root)

    assert result == {"added": True, "slug": "new-source"}
    assert manifest.hydration.linked_sources == ["existing-source", "new-source"]


async def test_save_to_knowledge_base_uses_project_slug_for_local_project(monkeypatch):
    captured: dict[str, object] = {}

    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    async def _mutation(path: str, payload: dict):
        captured["path"] = path
        captured["payload"] = payload
        return "doc-123"

    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.convex, "mutation", _mutation)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    result = await project_agent_router._execute_project_tool(
        "save_to_knowledge_base",
        {"name": "Repo-first note", "content": "Persist this finding."},
        "local:demo-project",
    )

    assert result == {"saved": True, "id": "doc-123", "name": "Repo-first note"}
    assert captured["path"] == "context:create"
    assert captured["payload"]["projectSlug"] == "demo-project"
    assert "projectId" not in captured["payload"]
    assert "createdAt" not in captured["payload"]
    assert "updatedAt" not in captured["payload"]


async def test_get_recent_jobs_uses_project_slug_for_local_project(monkeypatch):
    captured: dict[str, object] = {}

    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        if path == "jobs:listByProject":
            captured["payload"] = payload
            return [{"_id": "job-1", "status": "success", "createdAt": 123, "stepResults": []}]
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {"_id": "local:demo-project", "slug": "demo-project", "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    result = await project_agent_router._execute_project_tool(
        "get_recent_jobs",
        {"limit": 3},
        "local:demo-project",
    )

    assert captured["payload"] == {"projectSlug": "demo-project", "limit": 3}
    assert result["jobs"][0]["jobId"] == "job-1"


async def test_resolve_project_record_prefers_repo_first_local_project(monkeypatch):
    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {"_id": "local:demo-project", "slug": "demo-project", "localRepoPath": "/tmp/demo-project"}

    async def _query(path: str, payload: dict):
        raise AssertionError((path, payload))

    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(project_agent_router.convex, "query", _query)

    project = await project_agent_router._resolve_project_record("local:demo-project")

    assert project["_id"] == "local:demo-project"


async def test_persist_project_patch_prefers_repo_first_refresh_for_convex_project(monkeypatch):
    project = {"_id": "project-1", "slug": "demo-project", "name": "Demo"}
    updated_payloads: list[dict] = []

    async def _mutation(path: str, payload: dict):
        assert path == "projects:updateById"
        updated_payloads.append(payload)
        return None

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {"_id": "project-1", "slug": slug, "name": "Updated Demo", "status": "ready"}

    async def _query(path: str, payload: dict):
        if path == "projects:getById":
            raise AssertionError("_persist_project_patch should prefer planner_service refresh")
        raise AssertionError(path)

    monkeypatch.setattr(project_agent_router.convex, "mutation", _mutation)
    monkeypatch.setattr(project_agent_router.convex, "query", _query)
    monkeypatch.setattr(project_agent_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    refreshed = await project_agent_router._persist_project_patch(project, {"name": "Updated Demo"})

    assert refreshed["name"] == "Updated Demo"
    assert updated_payloads[0]["projectId"] == "project-1"
