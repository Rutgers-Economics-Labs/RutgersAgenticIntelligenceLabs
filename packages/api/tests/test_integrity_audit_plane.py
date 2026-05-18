"""Tests for Milestone 5: Integrity Audit Plane — source admissibility and artifact lineage."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

RAIL_PY_ROOT = Path(__file__).parents[3] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))


# ---------------------------------------------------------------------------
# Minimal manifest stub for tests
# ---------------------------------------------------------------------------

def _make_manifest(*, allow_synthetic: bool = False, require_lineage: bool = True, artifacts_root: str = "artifacts"):
    return SimpleNamespace(
        integrity=SimpleNamespace(
            allow_synthetic_data=allow_synthetic,
            require_lineage_for_final_artifacts=require_lineage,
        ),
        paths=SimpleNamespace(artifacts_root=artifacts_root),
    )


# ---------------------------------------------------------------------------
# audit_source_admissibility
# ---------------------------------------------------------------------------

def _write_sources(plan_root: Path, sources: list[dict]) -> None:
    state_dir = plan_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    for name in ["claims.json", "artifact_lineage.json", "verification_runs.json",
                 "assumptions.json", "source_candidates.json", "claim_candidates.json",
                 "entity_candidates.json", "conflicts.json"]:
        path = state_dir / name
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


def test_audit_source_admissibility_all_admissible(tmp_path):
    from app.services.integrity_service import audit_source_admissibility

    plan_root = tmp_path / "research_plan"
    _write_sources(plan_root, [
        {"source_key": "s1", "source_type": "api", "title": "S1", "url_or_path": "http://example.com",
         "admissibility_status": "observed"},
        {"source_key": "s2", "source_type": "api", "title": "S2", "url_or_path": "http://example2.com",
         "admissibility_status": "derived"},
    ])

    result = audit_source_admissibility(tmp_path, _make_manifest())

    assert result["admissibleCount"] == 2
    assert result["inadmissibleCount"] == 0
    assert result["inadmissibleSources"] == []
    assert result["blockers"] == []


def test_audit_source_admissibility_blocks_estimated_source(tmp_path):
    from app.services.integrity_service import audit_source_admissibility

    plan_root = tmp_path / "research_plan"
    _write_sources(plan_root, [
        {"source_key": "s-est", "source_type": "manual", "title": "Estimated",
         "url_or_path": "local/file.csv", "admissibility_status": "estimated"},
    ])

    result = audit_source_admissibility(tmp_path, _make_manifest())

    assert result["inadmissibleCount"] == 1
    assert result["inadmissibleSources"][0]["sourceKey"] == "s-est"
    assert result["inadmissibleSources"][0]["admissibilityStatus"] == "estimated"
    assert len(result["blockers"]) == 1


def test_audit_source_admissibility_blocks_synthetic_when_policy_disallows(tmp_path):
    from app.services.integrity_service import audit_source_admissibility

    plan_root = tmp_path / "research_plan"
    _write_sources(plan_root, [
        {"source_key": "s-syn", "source_type": "generated", "title": "Synthetic",
         "url_or_path": "generated/data.csv", "admissibility_status": "synthetic"},
    ])

    result = audit_source_admissibility(tmp_path, _make_manifest(allow_synthetic=False))

    assert result["inadmissibleCount"] == 1
    assert "policy" in result["inadmissibleSources"][0]["reason"].lower()


def test_audit_source_admissibility_allows_synthetic_when_policy_permits(tmp_path):
    from app.services.integrity_service import audit_source_admissibility

    plan_root = tmp_path / "research_plan"
    _write_sources(plan_root, [
        {"source_key": "s-syn", "source_type": "generated", "title": "Synthetic",
         "url_or_path": "generated/data.csv", "admissibility_status": "synthetic"},
    ])

    result = audit_source_admissibility(tmp_path, _make_manifest(allow_synthetic=True))

    assert result["admissibleCount"] == 1
    assert result["inadmissibleCount"] == 0
    assert result["blockers"] == []


# ---------------------------------------------------------------------------
# audit_artifact_lineage
# ---------------------------------------------------------------------------

def _write_artifacts(plan_root: Path, artifacts: list[dict]) -> None:
    state_dir = plan_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "artifact_lineage.json").write_text(json.dumps(artifacts), encoding="utf-8")
    for name in ["sources.json", "claims.json", "verification_runs.json",
                 "assumptions.json", "source_candidates.json", "claim_candidates.json",
                 "entity_candidates.json", "conflicts.json"]:
        path = state_dir / name
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


def test_audit_artifact_lineage_compliant_artifact(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/report.md",
        "artifact_type": "report",
        "title": "Report",
        "inputs": ["data/processed.csv"],
        "scripts": ["scripts/generate.py"],
        "verification_runs": ["run-001"],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest())

    assert result["compliantCount"] == 1
    assert result["nonCompliantArtifacts"] == []
    assert result["blockers"] == []


def test_audit_artifact_lineage_flags_missing_lineage(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/report.md",
        "artifact_type": "report",
        "title": "Report",
        "inputs": [],
        "scripts": [],
        "verification_runs": ["run-001"],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest())

    assert len(result["nonCompliantArtifacts"]) == 1
    assert result["nonCompliantArtifacts"][0]["missingLineage"] is True
    assert len(result["blockers"]) == 1


def test_audit_artifact_lineage_flags_missing_verification(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/figure1.png",
        "artifact_type": "figure",
        "title": "Figure 1",
        "inputs": ["data/processed.csv"],
        "scripts": ["scripts/plot.py"],
        "verification_runs": [],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest())

    assert len(result["nonCompliantArtifacts"]) == 1
    assert result["nonCompliantArtifacts"][0]["missingVerification"] is True


def test_audit_artifact_lineage_skips_datasets(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/raw.csv",
        "artifact_type": "dataset",
        "title": "Raw Data",
        "inputs": [],
        "scripts": [],
        "verification_runs": [],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest())

    assert result["nonCompliantArtifacts"] == []
    assert result["blockers"] == []


def test_audit_artifact_lineage_skips_manual_reproducibility(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/memo.pdf",
        "artifact_type": "report",
        "title": "Manual Memo",
        "reproducibility_mode": "manual",
        "inputs": [],
        "scripts": [],
        "verification_runs": [],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest())

    assert result["compliantCount"] == 1
    assert result["nonCompliantArtifacts"] == []


def test_audit_artifact_lineage_skips_when_policy_disabled(tmp_path):
    from app.services.integrity_service import audit_artifact_lineage

    plan_root = tmp_path / "research_plan"
    _write_artifacts(plan_root, [{
        "artifact_path": "artifacts/report.md",
        "artifact_type": "report",
        "title": "Report",
        "inputs": [],
        "scripts": [],
        "verification_runs": [],
    }])

    result = audit_artifact_lineage(tmp_path, _make_manifest(require_lineage=False))

    assert result["nonCompliantArtifacts"] == []
    assert result["blockers"] == []
