import pytest

pytestmark = pytest.mark.asyncio


async def test_search_data_registry_tool_returns_results():
    from app.services.agent_service import _execute_tool

    result = await _execute_tool("search_data_registry", {
        "query": "unemployment",
        "provider": "fred",
        "geography": "state",
    })

    assert "results" in result
    assert len(result["results"]) > 0
    assert all(item["provider"] == "fred" for item in result["results"])
    assert all(item["geography"] == "state" for item in result["results"])


async def test_resolve_duckdb_path_uses_repo_first_artifacts_for_local_project(monkeypatch, tmp_path):
    from app.services import agent_service
    from app.services import project_artifacts_service

    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    duckdb_path = ontology_root / "onto.duckdb"
    duckdb_path.write_bytes(b"duck")

    async def _resolve(identifier: str):
        assert identifier == "local:demo-project"
        return project_artifacts_service.ProjectArtifacts(
            project_id=identifier,
            db_path=str(ontology_root / "onto.db"),
            owl_path=None,
            duckdb_path=str(duckdb_path),
            embeddings_path=str(ontology_root / "embeddings.db"),
        )

    monkeypatch.setattr(project_artifacts_service, "resolve", _resolve)

    result = await agent_service._resolve_duckdb_path(project_id="local:demo-project")

    assert result == str(duckdb_path.resolve())


async def test_build_context_snapshot_uses_repo_first_project_and_artifacts(monkeypatch, tmp_path):
    from app.services import agent_service
    from app.services import project_artifacts_service
    from app.services import sql_service

    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    duckdb_path = ontology_root / "onto.duckdb"
    duckdb_path.write_bytes(b"duck")

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "name": "Demo Project",
            "status": "hydrated",
            "localRepoPath": str(tmp_path),
        }

    async def _resolve(identifier: str):
        assert identifier == "demo-project"
        return project_artifacts_service.ProjectArtifacts(
            project_id=identifier,
            db_path=str(ontology_root / "onto.db"),
            owl_path=None,
            duckdb_path=str(duckdb_path),
            embeddings_path=str(ontology_root / "embeddings.db"),
        )

    monkeypatch.setattr("app.services.planner_service.resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr(project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(sql_service, "get_schema_ddl", lambda duckdb_path=None: "CREATE TABLE demo();")
    monkeypatch.setattr(sql_service, "list_tables", lambda duckdb_path=None: ["demo"])
    monkeypatch.setattr(
        sql_service,
        "run_query",
        lambda query, duckdb_path=None: {"rows": [{"n": 3}]},
    )

    snapshot = await agent_service._build_context_snapshot("demo-project")

    assert snapshot["project"]["slug"] == "demo-project"
    assert snapshot["ontology"]["schema_ddl"] == "CREATE TABLE demo();"
    assert snapshot["ontology"]["classes"] == [{"name": "demo", "instance_count": 3}]
