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


def test_validation_fixture_missing_ontology_fails_boot_contract():
    project_root = VALIDATION_ROOT / "document-heavy-literature"
    if not project_root.exists():
        pytest.skip(f"fixture missing: {project_root}")

    with pytest.raises(ManifestValidationError) as exc_info:
        ensure_project_boot(project_root)

    paths = {item.path for item in exc_info.value.violations}
    assert ".ontology" in paths


def test_load_project_manifest_returns_violations_without_raising():
    project_root = VALIDATION_ROOT / "document-heavy-literature"
    if not project_root.exists():
        pytest.skip(f"fixture missing: {project_root}")

    _manifest, violations = load_project_manifest(project_root)

    assert any(item.path == ".ontology" for item in violations)
