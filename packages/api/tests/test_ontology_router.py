"""
Tests for ontology routes, including semantic search.
"""
import sqlite3

import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_semantic_search_route(client):
    expected = [
        {
            "id": "County_Monmouth",
            "iri": "http://example.org/County_Monmouth",
            "class": "County",
            "properties": {"hasName": "Monmouth County"},
        }
    ]

    with patch("app.routers.ontology.embedding_service.search", new=AsyncMock(return_value=expected)) as search_mock:
        resp = await client.get(
            "/api/v1/ontology/semantic-search",
            params={"q": "coastal counties", "types": "County", "limit": 10},
        )

    assert resp.status_code == 200
    assert resp.json() == expected
    search_mock.assert_awaited_once_with("coastal counties", top_k=10, types=["County"], project_id=None)


async def test_semantic_search_unavailable(client):
    with patch(
        "app.routers.ontology.embedding_service.search",
        new=AsyncMock(side_effect=RuntimeError("Semantic index not ready")),
    ):
        resp = await client.get("/api/v1/ontology/semantic-search", params={"q": "coastal counties"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Semantic index not ready"


async def test_classes_route_accepts_repo_first_project_slug(client, monkeypatch, tmp_path):
    from app.services import project_artifacts_service

    project_root = tmp_path / "demo-project"
    ontology_root = project_root / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    with sqlite3.connect(onto_db) as conn:
        conn.execute("CREATE TABLE demo(id INTEGER)")
    onto_duckdb.write_bytes(b"duck")

    async def _query(path: str, payload: dict):
        if path in {"projects:getById", "projects:get"}:
            return None
        raise AssertionError(path)

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "local:demo-project",
            "slug": slug,
            "localRepoPath": str(project_root),
        }

    project_artifacts_service._resolution_cache.clear()
    monkeypatch.setattr("app.services.project_artifacts_service.convex.query", _query)
    monkeypatch.setattr("app.services.planner_service.get_project_by_slug", _get_project_by_slug)

    with patch(
        "app.routers.ontology.ontology_service._run_with_ensure",
        new=AsyncMock(return_value=["County", "City"]),
    ) as run_mock:
        resp = await client.get("/api/v1/ontology/classes", params={"projectId": "demo-project"})

    assert resp.status_code == 200
    assert resp.json() == {"classes": ["County", "City"]}
    run_mock.assert_awaited_once()
    args = run_mock.await_args.args
    assert args[0] == "demo-project"
    assert args[1] == str(onto_db.resolve())
