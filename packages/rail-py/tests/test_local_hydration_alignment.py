"""
Tests for WO-F8.2 — .ontology hydration alignment.

Covers:
  - ontology_root resolves from manifest paths.ontology_root
  - artifact_db_path and artifact_duckdb_path are inside ontology_root
  - reuse detection via local meta file
  - default hydration target resolution from manifest
  - project.ontology() uses artifact_db_path
  - resolve_pipeline_slug fix in hydration_registry_service
"""
from __future__ import annotations

import hashlib
import json
import sys
import textwrap
from pathlib import Path

import pytest

RAIL_PY_ROOT = Path(__file__).parents[1]  # packages/rail-py
API_ROOT = Path(__file__).parents[2] / "api"  # packages/api

for _p in (str(RAIL_PY_ROOT), str(API_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


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
      default_pipeline: "test_pipeline"
      hydration_mode: "full"

    agents:
      roles_dir: "agents"
      default_runner: "jules"
      sequential_execution: true
      approval_required_for_write_runs: true
      planner_thread_mode: "project"
      default_planner_role: "planner"

    frontend:
      topic_index_mode: "filesystem"
      artifact_index_mode: "filesystem"
""")

CUSTOM_ONTOLOGY_ROOT_YAML = MINIMAL_RAIL_YAML.replace(
    'ontology_root: ".ontology"', 'ontology_root: "custom_onto"'
).replace(
    'ontology_file: ".ontology/ontology.yaml"', 'ontology_file: "custom_onto/ontology.yaml"'
).replace(
    'sources_dir: ".ontology/sources"', 'sources_dir: "custom_onto/sources"'
).replace(
    'pipelines_dir: ".ontology/pipelines"', 'pipelines_dir: "custom_onto/pipelines"'
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Minimal RAIL project directory with rail.yaml."""
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    (tmp_path / ".ontology").mkdir()
    (tmp_path / ".ontology" / "ontology.yaml").write_text(
        "uri: http://test.org/onto.owl\nclasses: []\n", encoding="utf-8"
    )
    (tmp_path / ".ontology" / "sources").mkdir()
    (tmp_path / ".ontology" / "pipelines").mkdir()
    return tmp_path


@pytest.fixture
def engine(project_root: Path):
    from rail.local import LocalEngine
    return LocalEngine(project_path=str(project_root), engine_path=None)


# ── .ontology path alignment ──────────────────────────────────────────────────

class TestOntologyPathAlignment:
    def test_ontology_root_is_inside_project(self, engine, project_root):
        assert engine.ontology_root == (project_root / ".ontology").resolve()

    def test_artifact_db_path_inside_ontology_root(self, engine):
        assert engine.artifact_db_path == engine.ontology_root / "onto.db"

    def test_artifact_duckdb_path_inside_ontology_root(self, engine):
        assert engine.artifact_duckdb_path == engine.ontology_root / "onto.duckdb"

    def test_custom_ontology_root_is_respected(self, tmp_path):
        (tmp_path / "rail.yaml").write_text(CUSTOM_ONTOLOGY_ROOT_YAML, encoding="utf-8")
        (tmp_path / "custom_onto").mkdir()
        (tmp_path / "custom_onto" / "ontology.yaml").write_text(
            "uri: http://test.org/onto.owl\nclasses: []\n"
        )
        (tmp_path / "custom_onto" / "sources").mkdir()
        (tmp_path / "custom_onto" / "pipelines").mkdir()

        from rail.local import LocalEngine
        eng = LocalEngine(project_path=str(tmp_path))
        assert eng.ontology_root == (tmp_path / "custom_onto").resolve()
        assert eng.artifact_db_path == eng.ontology_root / "onto.db"
        assert eng.artifact_duckdb_path == eng.ontology_root / "onto.duckdb"

    def test_project_ontology_uses_artifact_db_path(self, engine, project_root):
        # project.ontology() should delegate to backend.artifact_db_path, not hardcode "ontology/onto.db"
        from rail.project import Project
        proj = Project(slug="test-project", backend=engine)
        # The OntologyView constructor may fail without a real db — we just check the path used
        from unittest.mock import patch
        with patch("rail.ontology.OntologyView.__init__", return_value=None) as mock_init:
            proj.ontology()
            called_path = mock_init.call_args[0][0]
        assert called_path == str(engine.artifact_db_path)
        assert ".ontology" in called_path
        # Must NOT use the old hardcoded path
        assert "ontology/onto.db" not in called_path or called_path.startswith(str(project_root / ".ontology"))


# ── Default hydration target resolution ──────────────────────────────────────

class TestDefaultPipelineResolution:
    def test_default_pipeline_from_manifest(self, engine):
        assert engine.manifest.hydration.default_pipeline == "test_pipeline"

    def test_hydrate_raises_when_no_default_and_no_slug(self, tmp_path):
        """When manifest has no default_pipeline and no slug is passed, raise ValueError."""
        no_default = MINIMAL_RAIL_YAML.replace(
            '  default_pipeline: "test_pipeline"\n', ""
        )
        (tmp_path / "rail.yaml").write_text(no_default, encoding="utf-8")
        (tmp_path / ".ontology").mkdir()
        (tmp_path / ".ontology" / "sources").mkdir()
        (tmp_path / ".ontology" / "pipelines").mkdir()

        from rail.local import LocalEngine
        eng = LocalEngine(project_path=str(tmp_path), engine_path=None)

        # engine package may not be available in CI — patch run_pipeline
        from unittest.mock import patch
        with patch.dict("sys.modules", {"engine.pipeline_runner": __import__("unittest.mock").mock.MagicMock()}):
            with pytest.raises(ValueError, match="pipeline_slug is required"):
                eng.hydrate()

    def test_hydrate_uses_explicit_slug_over_default(self, engine, project_root):
        """An explicit slug is used instead of the manifest default."""
        # Create a dummy pipeline YAML so the FileNotFoundError isn't hit first
        (project_root / ".ontology" / "pipelines" / "explicit_pipeline.yaml").write_text(
            "ontology: .ontology/ontology.yaml\nsteps: []\n"
        )
        # Make the artifact already "valid" so we hit the reuse path
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("explicit_pipeline", "full")

        result = engine.hydrate("explicit_pipeline")
        assert result["pipeline_slug"] == "explicit_pipeline"
        assert result["status"] == "reused"


# ── Reuse-aware hydration ─────────────────────────────────────────────────────

class TestReuseAwareHydration:
    def test_not_reusable_when_no_artifact(self, engine):
        assert not engine._is_reusable("test_pipeline", "full")

    def test_not_reusable_when_no_meta_file(self, engine):
        engine.artifact_db_path.parent.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        assert not engine._is_reusable("test_pipeline", "full")

    def test_not_reusable_when_pipeline_slug_differs(self, engine):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("other_pipeline", "full")
        assert not engine._is_reusable("test_pipeline", "full")

    def test_not_reusable_when_hydration_mode_differs(self, engine):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("test_pipeline", "incremental")
        assert not engine._is_reusable("test_pipeline", "full")

    def test_not_reusable_when_manifest_fingerprint_changed(self, engine, project_root):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        # Write meta with a stale fingerprint
        meta = {
            "manifest_fingerprint": "stale_fingerprint",
            "commit_sha": None,
            "pipeline_slug": "test_pipeline",
            "hydration_mode": "full",
        }
        engine._hydration_meta_path.write_text(json.dumps(meta), encoding="utf-8")
        assert not engine._is_reusable("test_pipeline", "full")

    def test_reusable_when_all_conditions_match(self, engine):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("test_pipeline", "full")
        # Patch _repo_commit to return None (non-git environment)
        from unittest.mock import patch
        with patch.object(engine, "_repo_commit", return_value=None):
            assert engine._is_reusable("test_pipeline", "full")

    def test_hydrate_returns_reused_when_valid_artifact_exists(self, engine):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("test_pipeline", "full")

        from unittest.mock import patch
        with patch.object(engine, "_repo_commit", return_value=None):
            result = engine.hydrate()

        assert result["status"] == "reused"
        assert result["pipeline_slug"] == "test_pipeline"
        assert result["artifact_db_path"] == str(engine.artifact_db_path)

    def test_hydrate_force_skips_reuse_check(self, engine, project_root):
        """force=True bypasses reuse even if artifact is valid."""
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine.artifact_db_path.write_bytes(b"")
        engine._write_hydration_meta("test_pipeline", "full")

        # We expect it to proceed past reuse and hit the pipeline runner
        from unittest.mock import patch, MagicMock
        mock_run = MagicMock()
        with patch("engine.pipeline_runner.run_pipeline", mock_run, create=True):
            # Patch sys.modules so the import succeeds
            import types
            mock_engine_mod = types.ModuleType("engine.pipeline_runner")
            mock_engine_mod.run_pipeline = mock_run
            sys.modules.setdefault("engine", types.ModuleType("engine"))
            sys.modules["engine.pipeline_runner"] = mock_engine_mod

            # Pipeline YAML must exist
            pipeline_file = project_root / ".ontology" / "pipelines" / "test_pipeline.yaml"
            pipeline_file.write_text(
                "ontology: .ontology/ontology.yaml\nsteps: []\n", encoding="utf-8"
            )

            with patch.object(engine, "_repo_commit", return_value=None):
                result = engine.hydrate(force=True)

        assert result["status"] == "hydrated"
        mock_run.assert_called_once()

    def test_write_and_read_hydration_meta_round_trip(self, engine):
        engine.ontology_root.mkdir(parents=True, exist_ok=True)
        engine._write_hydration_meta("my_pipeline", "incremental")
        meta = engine._read_hydration_meta()
        assert meta["pipeline_slug"] == "my_pipeline"
        assert meta["hydration_mode"] == "incremental"
        assert "manifest_fingerprint" in meta


# ── hydration_registry_service resolve_pipeline_slug fix ─────────────────────
# These tests live in packages/api/tests/test_hydration_registry.py so that the
# API conftest handles Convex mocking cleanly.  Here we verify the underlying
# parse_manifest_content helper used by the fixed implementation.

class TestResolvePipelineSlug:
    def test_parse_manifest_content_returns_default_pipeline(self):
        from rail.manifest import parse_manifest_content
        manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
        assert manifest.hydration.default_pipeline == "test_pipeline"

    def test_parse_manifest_content_none_when_absent(self):
        from rail.manifest import parse_manifest_content
        no_default = MINIMAL_RAIL_YAML.replace(
            '  default_pipeline: "test_pipeline"\n', ""
        )
        manifest = parse_manifest_content(no_default)
        assert manifest.hydration.default_pipeline is None

    def test_resolve_pipeline_slug_logic(self, project_root):
        """Simulate what resolve_pipeline_slug does: read rail.yaml and return default_pipeline."""
        from rail.manifest import parse_manifest_content
        content = (project_root / "rail.yaml").read_text(encoding="utf-8")
        manifest = parse_manifest_content(content)
        result = manifest.hydration.default_pipeline or "default"
        assert result == "test_pipeline"

    def test_resolve_pipeline_slug_fallback(self, tmp_path):
        no_default = MINIMAL_RAIL_YAML.replace(
            '  default_pipeline: "test_pipeline"\n', ""
        )
        (tmp_path / "rail.yaml").write_text(no_default, encoding="utf-8")
        from rail.manifest import parse_manifest_content
        manifest = parse_manifest_content(no_default)
        result = manifest.hydration.default_pipeline or "default"
        assert result == "default"
