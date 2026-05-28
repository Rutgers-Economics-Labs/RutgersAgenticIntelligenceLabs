from __future__ import annotations

import sqlite3

import pytest

from app.services import project_artifacts_service


@pytest.mark.asyncio
async def test_resolve_uses_repo_first_local_artifacts_when_convex_project_missing(monkeypatch, tmp_path):
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

    monkeypatch.setattr(project_artifacts_service.convex, "query", _query)
    monkeypatch.setattr("app.services.planner_service.get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "ensure_loaded_async", pytest.fail)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "export_to_duckdb", pytest.fail)

    artifacts = await project_artifacts_service.resolve("demo-project")

    assert artifacts.project_id == "demo-project"
    assert artifacts.db_path == str(onto_db.resolve())
    assert artifacts.duckdb_path == str(onto_duckdb.resolve())
    assert artifacts.owl_path is None
    assert artifacts.embeddings_path == str((ontology_root / "embeddings.db").resolve())
