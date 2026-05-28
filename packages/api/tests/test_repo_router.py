from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rail.bootstrap import bootstrap_future_project


pytestmark = pytest.mark.asyncio


async def test_repo_tree_uses_repo_first_local_project(monkeypatch, tmp_path):
    from app.routers import repo as repo_router

    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    notes = root / "research_plan" / "notes.md"
    notes.write_text("hello\n", encoding="utf-8")

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": slug,
            "localRepoPath": str(root),
        }

    monkeypatch.setattr(repo_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    body = await repo_router.get_repo_tree("demo-project", root_dir="research_plan", max_depth=3)

    assert body.path == "research_plan"
    assert body.children is not None
    assert any(child.name == "notes.md" for child in body.children)


async def test_repo_file_uses_repo_first_local_project(monkeypatch, tmp_path):
    from app.routers import repo as repo_router

    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    brief = root / "topics" / "brief.md"
    brief.write_text("# Demo brief\n", encoding="utf-8")

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": slug,
            "localRepoPath": str(root),
        }

    monkeypatch.setattr(repo_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    body = await repo_router.get_repo_file("demo-project", path="topics/brief.md")

    assert body.content == "# Demo brief\n"


async def test_repo_init_uses_repo_first_project_lookup(client, monkeypatch, tmp_path):
    from app.routers import repo as repo_router

    target = tmp_path / "repo-target"

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {
            "_id": "project-123",
            "slug": slug,
            "name": "Demo Project",
        }

    update_project = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(repo_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(repo_router.convex, "mutation", update_project)

    resp = await client.post(
        "/api/v1/projects/demo-project/repo/init",
        json={"targetDir": str(target)},
    )

    assert resp.status_code == 200
    assert resp.json()["localRepoPath"] == str(target.resolve())
    assert (target / "rail.yaml").exists()
    update_project.assert_awaited_once_with(
        "projects:updateById",
        {"projectId": "project-123", "localRepoPath": str(target.resolve())},
    )
