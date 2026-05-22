from __future__ import annotations

from pathlib import Path

import pytest

from app.services.repo_contract_service import ensure_project_boot, load_project_manifest
from rail.manifest import ManifestValidationError


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATION_ROOT = REPO_ROOT / "docs" / "validation"


@pytest.mark.parametrize(
    "project_slug",
    [
        "nj-housing-rates-study",
        "nj-labor-market-synthesis",
        "ontology-first-public",
        "time-series-econ",
        "northeast-housing-comparison",
        "nj-housing-affordability",
    ],
)
def test_validation_fixture_passes_boot_contract(project_slug: str):
    project_root = VALIDATION_ROOT / project_slug
    if not project_root.exists():
        pytest.skip(f"fixture missing: {project_root}")

    manifest = ensure_project_boot(project_root)

    assert manifest.project.slug
    assert manifest.repo_contract.source_of_truth == "git"
    assert manifest.planner.task_root == "research_plan/tasks"


def test_validation_fixture_missing_ontology_fails_boot_contract(tmp_path):
    # The document-heavy-literature fixture intentionally declares
    # research_first mode with .ontology in flexible_paths, so the live
    # fixture does NOT fail boot. Copy it to a tmp dir and rewrite the
    # rail.yaml to require .ontology in required_paths, then assert that
    # ensure_project_boot raises ManifestValidationError naming .ontology.
    import shutil

    src = VALIDATION_ROOT / "document-heavy-literature"
    if not src.exists():
        pytest.skip(f"fixture missing: {src}")
    project_root = tmp_path / "missing-ontology"
    shutil.copytree(src, project_root)
    # Strip .ontology if the fixture happens to have it (it doesn't today)
    # and rewrite rail.yaml to require it.
    onto = project_root / ".ontology"
    if onto.exists():
        shutil.rmtree(onto)
    rail_yaml = project_root / "rail.yaml"
    text = rail_yaml.read_text(encoding="utf-8")
    # Move .ontology from flexible_paths to required_paths.
    text = text.replace('    - ".ontology"\n', "")
    text = text.replace(
        'required_paths:\n    - "specs"',
        'required_paths:\n    - ".ontology"\n    - "specs"',
    )
    rail_yaml.write_text(text, encoding="utf-8")

    with pytest.raises(ManifestValidationError) as exc_info:
        ensure_project_boot(project_root)

    paths = {item.path for item in exc_info.value.violations}
    assert ".ontology" in paths


def test_load_project_manifest_returns_violations_without_raising(tmp_path):
    # Same fixture-rewrite pattern as above — surface .ontology as a
    # required-path violation without raising.
    import shutil

    src = VALIDATION_ROOT / "document-heavy-literature"
    if not src.exists():
        pytest.skip(f"fixture missing: {src}")
    project_root = tmp_path / "missing-ontology"
    shutil.copytree(src, project_root)
    onto = project_root / ".ontology"
    if onto.exists():
        shutil.rmtree(onto)
    rail_yaml = project_root / "rail.yaml"
    text = rail_yaml.read_text(encoding="utf-8")
    text = text.replace('    - ".ontology"\n', "")
    text = text.replace(
        'required_paths:\n    - "specs"',
        'required_paths:\n    - ".ontology"\n    - "specs"',
    )
    rail_yaml.write_text(text, encoding="utf-8")

    _manifest, violations = load_project_manifest(project_root)

    assert any(item.path == ".ontology" for item in violations)
