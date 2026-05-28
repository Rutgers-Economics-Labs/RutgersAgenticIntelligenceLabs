from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_resolve_project_from_job_doc_prefers_convex_project_id(monkeypatch):
    from app.services import hydration_worker

    async def _query(path: str, payload: dict):
        assert path == "projects:getById"
        assert payload == {"projectId": "project-123"}
        return {"_id": "project-123", "slug": "demo-project"}

    resolve_ref_called = False

    async def _resolve_project_reference(project_ref: str | None):
        nonlocal resolve_ref_called
        resolve_ref_called = True
        raise AssertionError(project_ref)

    monkeypatch.setattr(hydration_worker.convex, "query", _query)
    monkeypatch.setattr(hydration_worker.planner_service, "resolve_project_reference", _resolve_project_reference)

    project_id, project = await hydration_worker._resolve_project_from_job_doc(
        {"projectId": "project-123", "projectSlug": "demo-project"}
    )

    assert project_id == "project-123"
    assert project == {"_id": "project-123", "slug": "demo-project"}
    assert resolve_ref_called is False


async def test_resolve_project_from_job_doc_falls_back_to_repo_first_slug(monkeypatch):
    from app.services import hydration_worker

    async def _query(path: str, payload: dict):
        assert path == "projects:getById"
        return None

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    monkeypatch.setattr(hydration_worker.convex, "query", _query)
    monkeypatch.setattr(hydration_worker.planner_service, "resolve_project_reference", _resolve_project_reference)

    project_id, project = await hydration_worker._resolve_project_from_job_doc(
        {"projectId": "project-123", "projectSlug": "demo-project"}
    )

    assert project_id == "local:demo-project"
    assert project["slug"] == "demo-project"
    assert project["localRepoPath"] == "/tmp/demo-project"


async def test_resolve_project_from_job_doc_handles_slug_only_repo_project(monkeypatch):
    from app.services import hydration_worker

    convex_called = False

    async def _query(path: str, payload: dict):
        nonlocal convex_called
        convex_called = True
        raise AssertionError((path, payload))

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {"_id": "local:demo-project", "slug": "demo-project"}

    monkeypatch.setattr(hydration_worker.convex, "query", _query)
    monkeypatch.setattr(hydration_worker.planner_service, "resolve_project_reference", _resolve_project_reference)

    project_id, project = await hydration_worker._resolve_project_from_job_doc(
        {"projectSlug": "demo-project"}
    )

    assert project_id == "local:demo-project"
    assert project == {"_id": "local:demo-project", "slug": "demo-project"}
    assert convex_called is False
