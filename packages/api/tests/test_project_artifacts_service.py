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

    convex_called = False

    async def _query(path: str, payload: dict):
        nonlocal convex_called
        convex_called = True
        raise AssertionError((path, payload))

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": str(project_root),
        }

    monkeypatch.setattr(project_artifacts_service.convex, "query", _query)
    monkeypatch.setattr("app.services.planner_service.resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "ensure_loaded_async", pytest.fail)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "export_to_duckdb", pytest.fail)

    artifacts = await project_artifacts_service.resolve("demo-project")

    assert artifacts.project_id == "demo-project"
    assert artifacts.db_path == str(onto_db.resolve())
    assert artifacts.duckdb_path == str(onto_duckdb.resolve())
    assert artifacts.owl_path is None
    assert artifacts.embeddings_path == str((ontology_root / "embeddings.db").resolve())
    assert convex_called is False


@pytest.mark.asyncio
async def test_resolve_accepts_local_prefixed_project_id_for_repo_only_projects(monkeypatch, tmp_path):
    project_root = tmp_path / "demo-project"
    ontology_root = project_root / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    with sqlite3.connect(onto_db) as conn:
        conn.execute("CREATE TABLE demo(id INTEGER)")
    onto_duckdb.write_bytes(b"duck")

    convex_called = False

    async def _query(path: str, payload: dict):
        nonlocal convex_called
        convex_called = True
        raise AssertionError((path, payload))

    seen_refs: list[str | None] = []

    async def _resolve_project_reference(project_ref: str | None):
        seen_refs.append(project_ref)
        if project_ref != "local:demo-project":
            raise ValueError(project_ref)
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "localRepoPath": str(project_root),
        }

    monkeypatch.setattr(project_artifacts_service.convex, "query", _query)
    monkeypatch.setattr("app.services.planner_service.resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "ensure_loaded_async", pytest.fail)
    monkeypatch.setattr(project_artifacts_service.ontology_service, "export_to_duckdb", pytest.fail)

    artifacts = await project_artifacts_service.resolve("local:demo-project")

    assert seen_refs == ["local:demo-project"]
    assert artifacts.project_id == "local:demo-project"
    assert artifacts.db_path == str(onto_db.resolve())
    assert artifacts.duckdb_path == str(onto_duckdb.resolve())
    assert convex_called is False
