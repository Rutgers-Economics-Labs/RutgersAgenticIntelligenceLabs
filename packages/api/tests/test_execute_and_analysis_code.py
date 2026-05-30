"""Execute / analysis/run-code gates, subprocess runner, and artifact upload."""
from pathlib import Path

import duckdb
import pytest


@pytest.mark.asyncio
async def test_execute_returns_403_when_disabled(client, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "execute_python_enabled", False)
    r = await client.post("/api/v1/execute", json={"code": "print(1)"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_analysis_run_code_503_without_duckdb(client, monkeypatch):
    from app.core import config
    from app.services import sql_service

    monkeypatch.setattr(config.settings, "execute_python_enabled", True)
    sql_service.set_path("/nonexistent/path/onto.duckdb")

    r = await client.post(
        "/api/v1/analysis/run-code",
        json={"code": "print(1)", "upload_artifacts": False},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_analysis_run_code_writes_artifact(client, tmp_path, monkeypatch):
    from app.core import config
    from app.services import sql_service

    monkeypatch.setattr(config.settings, "execute_python_enabled", True)
    monkeypatch.setattr(config.settings, "execute_docker_image", "")

    db_path = tmp_path / "mini.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE t (a INTEGER); INSERT INTO t VALUES (42);")
    con.close()
    sql_service.set_path(db_path)

    code = """
import os
p = os.path.join(OUTPUT_DIR, "note.txt")
with open(p, "w", encoding="utf-8") as f:
    f.write("ok")
result_df = sql("SELECT * FROM t")
"""
    r = await client.post(
        "/api/v1/analysis/run-code",
        json={"code": code, "timeout": 60, "upload_artifacts": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("jobId")


@pytest.mark.asyncio
async def test_run_code_async_subprocess_mode(tmp_path, monkeypatch):
    from app.core import config
    from app.services import code_runner, sql_service

    monkeypatch.setattr(config.settings, "execute_python_enabled", True)
    monkeypatch.setattr(config.settings, "execute_python_mode", "subprocess")
    monkeypatch.setattr(config.settings, "execute_docker_image", "")

    db_path = tmp_path / "m2.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE u (b VARCHAR); INSERT INTO u VALUES ('x');")
    con.close()
    sql_service.set_path(db_path)

    out = await code_runner.run_code_async('df = sql("SELECT * FROM u")', timeout_seconds=60)
    assert out.get("error") is None


@pytest.mark.asyncio
async def test_analysis_run_code_accepts_project_slug_repo_first(client, monkeypatch):
    from app.routers import analysis as analysis_router

    captured: dict[str, object] = {}

    async def _resolve(project_ref: str):
        captured["project_ref"] = project_ref
        return type(
            "Artifacts",
            (),
            {"duckdb_path": "/tmp/demo/onto.duckdb"},
        )()

    async def _mutation(path: str, payload: dict):
        if path == "executions:create":
            captured["create_args"] = payload
            return {"jobId": "job-123"}
        if path == "executions:updateStatus":
            return {"ok": True}
        raise AssertionError(path)

    async def _run_user_code(*args, **kwargs):
        return {"stdout": "ok"}

    monkeypatch.setattr(analysis_router.project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(analysis_router.convex, "mutation", _mutation)
    monkeypatch.setattr(analysis_router.sql_service, "is_ready", lambda duck=None: True)
    monkeypatch.setattr(
        analysis_router.execution_manager,
        "register_job",
        lambda job_id, task: captured.setdefault("registered_job", job_id),
    )
    monkeypatch.setattr(
        "app.services.subprocess_code_runner.run_user_code",
        _run_user_code,
    )

    resp = await client.post(
        "/api/v1/analysis/run-code?projectSlug=demo-project",
        json={"code": "print(1)", "upload_artifacts": False},
    )

    assert resp.status_code == 200
    assert resp.json() == {"jobId": "job-123", "status": "queued"}
    assert captured["project_ref"] == "demo-project"
    assert "projectId" not in captured["create_args"]
