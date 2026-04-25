import os
import sys
from pathlib import Path
import textwrap

API_ROOT = str(Path(__file__).parents[1])
ENGINE_ROOT = str(Path(__file__).parents[2] / "engine")
RAIL_PY_ROOT = str(Path(__file__).parents[2] / "rail-py")

for _p in (ENGINE_ROOT, RAIL_PY_ROOT):
    if _p not in sys.path:
        sys.path.append(_p)
if API_ROOT in sys.path:
    sys.path.remove(API_ROOT)
sys.path.insert(0, API_ROOT)

os.environ.setdefault("CONVEX_URL", "https://colorless-elephant-150.convex.cloud")
os.environ.setdefault("CONVEX_DEPLOY_KEY", "test-key")

from app.routers.projects import _configured_pipeline_slug, _local_hydration_configs, _manifest_metadata  # noqa: E402


def test_manifest_metadata_falls_back_for_legacy_manifest(tmp_path):
    (tmp_path / "rail.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            project:
              name: Legacy Starter
              description: Old manifest shape
            """
        ),
        encoding="utf-8",
    )

    metadata = _manifest_metadata(
        tmp_path,
        {"name": "Fallback", "slug": "fallback", "description": "Fallback description"},
    )

    assert metadata["name"] == "Legacy Starter"
    assert metadata["slug"] == "fallback"
    assert metadata["description"] == "Old manifest shape"


def test_configured_pipeline_slug_prefers_repo_hydration_file(tmp_path):
    pipeline_dir = tmp_path / ".ontology" / "pipelines"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "nj_gis_hydration.yaml").write_text("steps: []\n", encoding="utf-8")
    (pipeline_dir / "nj_hydration.yaml").write_text("steps: []\n", encoding="utf-8")

    assert _configured_pipeline_slug({"slug": "sad"}, tmp_path) == "nj_hydration"


def test_local_hydration_configs_loads_pipeline_sources_and_ontology(tmp_path):
    (tmp_path / ".ontology" / "pipelines").mkdir(parents=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True)
    (tmp_path / ".ontology" / "ontology.yaml").write_text("classes: []\n", encoding="utf-8")
    (tmp_path / ".ontology" / "sources" / "sample.yaml").write_text("name: Sample\n", encoding="utf-8")
    (tmp_path / ".ontology" / "pipelines" / "sample_hydration.yaml").write_text(
        "ontology: configs/ontology/core.yaml\nsteps:\n  - api: sample\n",
        encoding="utf-8",
    )

    configs = _local_hydration_configs(tmp_path, "sample_hydration")

    assert configs is not None
    pipeline_content, api_configs, onto_configs = configs
    assert "api: sample" in pipeline_content
    assert api_configs["sample"] == "name: Sample\n"
    assert onto_configs["configs/ontology/core.yaml"] == "classes: []\n"
    assert onto_configs["core"] == "classes: []\n"
