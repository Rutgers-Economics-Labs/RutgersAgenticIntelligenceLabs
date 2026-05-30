from __future__ import annotations

import asyncio

import pytest

from app.services import project_artifacts_service


pytestmark = pytest.mark.asyncio


async def test_sql_schema_accepts_project_slug(client, monkeypatch):
    from app.routers import sql as sql_router

    async def _resolve(project_ref: str):
        assert project_ref == "demo-project"
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_ref,
            db_path="/tmp/demo/onto.db",
            owl_path=None,
            duckdb_path="/tmp/demo/onto.duckdb",
            embeddings_path="/tmp/demo/embeddings.db",
        )

    monkeypatch.setattr(sql_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(sql_router.sql_service, "get_schema", lambda duckdb_path=None: {"demo": [{"name": "value", "type": "INTEGER"}]})

    resp = await client.get("/api/v1/sql/schema", params={"projectSlug": "demo-project"})

    assert resp.status_code == 200
    assert resp.json() == {"demo": [{"name": "value", "type": "INTEGER"}]}


async def test_sql_tables_accepts_project_slug(client, monkeypatch):
    from app.routers import sql as sql_router

    async def _resolve(project_ref: str):
        assert project_ref == "demo-project"
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_ref,
            db_path="/tmp/demo/onto.db",
            owl_path=None,
            duckdb_path="/tmp/demo/onto.duckdb",
            embeddings_path="/tmp/demo/embeddings.db",
        )

    monkeypatch.setattr(sql_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(sql_router.sql_service, "list_tables", lambda duckdb_path=None: ["demo"])

    resp = await client.get("/api/v1/sql/tables", params={"projectSlug": "demo-project"})

    assert resp.status_code == 200
    assert resp.json() == ["demo"]


async def test_translate_sql_accepts_project_slug(client, monkeypatch):
    from app.routers import sql as sql_router

    async def _resolve(project_ref: str):
        assert project_ref == "demo-project"
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_ref,
            db_path="/tmp/demo/onto.db",
            owl_path=None,
            duckdb_path="/tmp/demo/onto.duckdb",
            embeddings_path="/tmp/demo/embeddings.db",
        )

    async def _translate(question: str, model: str | None = None, duckdb_path: str | None = None):
        return {"sql": "SELECT 1 AS value", "explanation": "demo"}

    monkeypatch.setattr(sql_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(sql_router.sql_service, "translate_to_sql", _translate)
    monkeypatch.setattr(sql_router.sql_service, "run_query", lambda query, duckdb_path=None: {"rows": [{"value": 1}]})

    resp = await client.post(
        "/api/v1/sql/translate?projectSlug=demo-project",
        json={"question": "show me the value"},
    )

    assert resp.status_code == 200
    assert resp.json()["sql"] == "SELECT 1 AS value"
    assert resp.json()["rows"] == [{"value": 1}]
