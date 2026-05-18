"""
Tests for WO-F8.2 — hydration_registry_service.resolve_pipeline_slug fix.

The original implementation called load_manifest(project_root / manifest_path)
which caused load_manifest to look for project_root/rail.yaml/rail.yaml (double
append).  The fix uses parse_manifest_content to read the file at the correct
path.
"""
import sys
from pathlib import Path
import textwrap

import pytest

API_ROOT = str(Path(__file__).parents[1])
ENGINE_ROOT = str(Path(__file__).parents[2] / "engine")
RAIL_PY_ROOT = str(Path(__file__).parents[2] / "rail-py")

# api package must be at position 0 so `import app` finds packages/api/app/
# (the FastAPI package) rather than packages/engine/app.py (the Streamlit app).
# LocalEngine.__init__ inserts engine_path at 0, so we must re-assert priority.
for _p in (ENGINE_ROOT, RAIL_PY_ROOT):
    if _p not in sys.path:
        sys.path.append(_p)
if API_ROOT in sys.path:
    sys.path.remove(API_ROOT)
sys.path.insert(0, API_ROOT)

# Import at module level so we pick up packages/api before LocalEngine has
# a chance to insert packages/engine at position 0 during test execution.
import os
import json
import asyncio
os.environ.setdefault("CONVEX_URL", "https://colorless-elephant-150.convex.cloud")
os.environ.setdefault("CONVEX_DEPLOY_KEY", "test-key")

from app.services.hydration_registry_service import (  # noqa: E402
    promote_project_hydration_artifact,
    register_hydration_artifact,
    resolve_pipeline_slug,
)

MINIMAL_RAIL_YAML = textwrap.dedent("""\
    version: 1

    project:
      name: "Test Project"
      slug: "test-project"
      default_branch: "main"

    paths:
      ontology_root: ".ontology"
      topics_root: "topics"
      specs_root: "specs"
      plan_root: "research_plan"
      agents_root: "agents"
      skills_root: "skills"
      artifacts_root: "artifacts"

    hydration:
      ontology_file: ".ontology/ontology.yaml"
      sources_dir: ".ontology/sources"
      pipelines_dir: ".ontology/pipelines"
      default_pipeline: "my_pipeline"
      hydration_mode: "full"

    agents:
      roles_dir: "agents"
      default_runner: "codex_cli"
      sequential_execution: true
      approval_required_for_write_runs: true
      planner_thread_mode: "project"
      default_planner_role: "planner"

    frontend:
      topic_index_mode: "filesystem"
      artifact_index_mode: "filesystem"
""")


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    return tmp_path


def test_resolve_returns_manifest_default_pipeline(project_root):
    """resolve_pipeline_slug reads default_pipeline from rail.yaml correctly."""
    from app.services.hydration_registry_service import resolve_pipeline_slug
    slug = resolve_pipeline_slug({}, project_root)
    assert slug == "my_pipeline"


def test_resolve_returns_fallback_when_no_default(tmp_path):
    """When rail.yaml has no default_pipeline, returns 'default'."""
    no_default = MINIMAL_RAIL_YAML.replace(
        '  default_pipeline: "my_pipeline"\n', ""
    )
    (tmp_path / "rail.yaml").write_text(no_default, encoding="utf-8")

    from app.services.hydration_registry_service import resolve_pipeline_slug
    slug = resolve_pipeline_slug({}, tmp_path)
    assert slug == "default"


def test_resolve_respects_custom_manifest_path(tmp_path):
    """resolve_pipeline_slug prefers the project record pipeline slug when present."""
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    from app.services.hydration_registry_service import resolve_pipeline_slug
    slug = resolve_pipeline_slug({"pipelineConfigSlug": "configured_pipeline"}, tmp_path)
    assert slug == "configured_pipeline"


def test_register_hydration_artifact_syncs_repo_dataset_lineage(project_root, monkeypatch):
    (project_root / ".ontology").mkdir(exist_ok=True)
    (project_root / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    (project_root / ".ontology" / "pipelines").mkdir(parents=True, exist_ok=True)
    (project_root / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (project_root / "research_plan" / "state" / "sources.json").write_text(
        json.dumps(
            [
                {
                    "source_key": "sample",
                    "source_type": "dataset",
                    "title": "Sample Source",
                    "url_or_path": "https://example.com/sample.csv",
                }
            ]
        ),
        encoding="utf-8",
    )
    (project_root / ".ontology" / "sources" / "sample.yaml").write_text("name: Sample\n", encoding="utf-8")
    (project_root / ".ontology" / "pipelines" / "my_pipeline.yaml").write_text(
        "ontology: .ontology/ontology.yaml\nsteps:\n  - api: sample\n",
        encoding="utf-8",
    )
    duckdb_path = project_root / ".ontology" / "onto.duckdb"
    duckdb_path.write_bytes(b"")

    async def _fake_mutation(path: str, payload: dict):
        assert path == "hydrationArtifacts:register"
        return "artifact-1"

    monkeypatch.setattr("app.services.hydration_registry_service.convex.mutation", _fake_mutation)

    artifact_id = asyncio.run(
        register_hydration_artifact(
            project={
                "_id": "project-1",
                "localRepoPath": str(project_root),
                "manifestPath": "rail.yaml",
            },
            pipeline_slug="my_pipeline",
            hydration_mode="full",
            ontology_artifact_path=str(project_root / ".ontology" / "onto.db"),
            duckdb_artifact_path=str(duckdb_path),
            status="valid",
        )
    )

    assert artifact_id == "artifact-1"
    lineage = json.loads((project_root / "research_plan" / "state" / "artifact_lineage.json").read_text(encoding="utf-8"))
    sources = json.loads((project_root / "research_plan" / "state" / "sources.json").read_text(encoding="utf-8"))
    dataset_entry = next(item for item in lineage if item["artifact_path"] == ".ontology/onto.duckdb")
    source_entry = next(item for item in sources if item["source_key"] == "sample")
    assert dataset_entry["sources"] == ["research_plan/state/sources.json#sample"]
    assert dataset_entry["scripts"] == [".ontology/pipelines/my_pipeline.yaml"]
    assert dataset_entry["inputs"] == [".ontology/sources/sample.yaml"]
    assert source_entry["title"] == "Sample"
    assert source_entry["access_method"] == "api"
    assert source_entry["freshness_status"] == "fresh"
    assert source_entry["provenance"]["config_path"] == ".ontology/sources/sample.yaml"


def test_promote_project_hydration_artifact_updates_active_paths(project_root, monkeypatch):
    ontology_root = project_root / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    hydration_meta = ontology_root / ".rail_hydration.json"
    owl = ontology_root / "populated_ontology.owl"
    embeddings = ontology_root / "embeddings.db"
    onto_db.write_bytes(b"db")
    onto_duckdb.write_bytes(b"duck")
    hydration_meta.write_text('{"pipeline_slug":"my_pipeline","hydration_mode":"full"}', encoding="utf-8")
    owl.write_text("owl", encoding="utf-8")
    embeddings.write_bytes(b"emb")

    calls: list[tuple[str, dict]] = []

    async def _fake_mutation(path: str, payload: dict):
        calls.append((path, payload))
        return "ok"

    monkeypatch.setattr("app.services.hydration_registry_service.convex.mutation", _fake_mutation)

    asyncio.run(
        promote_project_hydration_artifact(
            project={"_id": "project-1"},
            ontology_artifact_path=str(onto_db),
            duckdb_artifact_path=str(onto_duckdb),
        )
    )

    assert len(calls) == 1
    path, payload = calls[0]
    assert path == "projects:updateById"
    assert payload["projectId"] == "project-1"
    assert payload["status"] == "hydrated"
    assert payload["activeOntologyDbPath"] == str(onto_db)
    assert payload["activeOntologyDuckdbPath"] == str(onto_duckdb)
    assert payload["activeOntologyOwlPath"] == str(owl)
    assert payload["activeOntologyEmbeddingsPath"] == str(embeddings)
    assert isinstance(payload["lastHydratedAt"], int)


def test_promote_project_hydration_artifact_rejects_missing_hydration_metadata(project_root):
    ontology_root = project_root / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    onto_db.write_bytes(b"db")
    onto_duckdb.write_bytes(b"duck")

    with pytest.raises(ValueError, match="Hydration metadata must exist before promoting active ontology artifacts."):
        asyncio.run(
            promote_project_hydration_artifact(
                project={"_id": "project-1"},
                ontology_artifact_path=str(onto_db),
                duckdb_artifact_path=str(onto_duckdb),
            )
        )
