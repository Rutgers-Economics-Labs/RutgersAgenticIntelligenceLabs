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
os.environ.setdefault("CONVEX_URL", "https://colorless-elephant-150.convex.cloud")
os.environ.setdefault("CONVEX_DEPLOY_KEY", "test-key")

from app.services.hydration_registry_service import resolve_pipeline_slug  # noqa: E402

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
    slug = resolve_pipeline_slug(project_root)
    assert slug == "my_pipeline"


def test_resolve_returns_fallback_when_no_default(tmp_path):
    """When rail.yaml has no default_pipeline, returns 'default'."""
    no_default = MINIMAL_RAIL_YAML.replace(
        '  default_pipeline: "my_pipeline"\n', ""
    )
    (tmp_path / "rail.yaml").write_text(no_default, encoding="utf-8")

    from app.services.hydration_registry_service import resolve_pipeline_slug
    slug = resolve_pipeline_slug(tmp_path)
    assert slug == "default"


def test_resolve_respects_custom_manifest_path(tmp_path):
    """resolve_pipeline_slug uses manifest_path argument correctly (no double-append)."""
    custom_path = tmp_path / "custom.yaml"
    custom_path.write_text(MINIMAL_RAIL_YAML, encoding="utf-8")

    from app.services.hydration_registry_service import resolve_pipeline_slug
    slug = resolve_pipeline_slug(tmp_path, manifest_path="custom.yaml")
    assert slug == "my_pipeline"
