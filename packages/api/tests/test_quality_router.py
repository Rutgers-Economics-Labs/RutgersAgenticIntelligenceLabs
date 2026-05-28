from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from app.main import app
from app.services.project_artifacts_service import ProjectArtifacts


client = TestClient(app)


def test_quality_report_uses_repo_first_artifact_resolution(monkeypatch, tmp_path):
    import app.routers.quality as quality_router

    duckdb_path = tmp_path / "onto.duckdb"
    conn = duckdb.connect(str(duckdb_path))
    conn.execute("CREATE TABLE demo(id INTEGER, value VARCHAR)")
    conn.execute("INSERT INTO demo VALUES (1, 'a'), (2, NULL)")
    conn.close()

    async def _resolve(project_id: str):
        assert project_id == "demo-project"
        return ProjectArtifacts(
            project_id=project_id,
            db_path=str(tmp_path / "onto.db"),
            owl_path=None,
            duckdb_path=str(duckdb_path),
            embeddings_path=str(tmp_path / "embeddings.db"),
        )

    monkeypatch.setattr(quality_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(quality_router.sql_service, "get_path", lambda: None)

    response = client.get("/api/v1/quality/report", params={"project_id": "demo-project"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == "demo-project"
    assert Path(payload["dbPath"]) == duckdb_path
    assert payload["summary"]["tableCount"] == 1
    assert payload["tables"][0]["table"] == "demo"
    assert payload["tables"][0]["rowCount"] == 2


def test_quality_report_accepts_project_slug(monkeypatch, tmp_path):
    import app.routers.quality as quality_router

    duckdb_path = tmp_path / "onto.duckdb"
    conn = duckdb.connect(str(duckdb_path))
    conn.execute("CREATE TABLE demo(id INTEGER)")
    conn.execute("INSERT INTO demo VALUES (1)")
    conn.close()

    async def _resolve(project_ref: str):
        assert project_ref == "demo-project"
        return ProjectArtifacts(
            project_id=project_ref,
            db_path=str(tmp_path / "onto.db"),
            owl_path=None,
            duckdb_path=str(duckdb_path),
            embeddings_path=str(tmp_path / "embeddings.db"),
        )

    monkeypatch.setattr(quality_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(quality_router.sql_service, "get_path", lambda: None)

    response = client.get("/api/v1/quality/report", params={"projectSlug": "demo-project"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectId"] == "demo-project"
    assert payload["summary"]["totalRows"] == 1
