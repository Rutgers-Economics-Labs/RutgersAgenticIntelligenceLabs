from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo


def test_integrity_repo_loads_empty_bootstrap_indexes(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    indexes = repo.load_all()

    assert indexes.assumptions == []
    assert indexes.sources == []
    assert indexes.claims == []
    assert indexes.artifact_lineage == []
    assert indexes.verification_runs == []


def test_integrity_repo_upserts_and_rebuilds_indexes(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.upsert_assumption(
        {
            "assumption_key": "years-2010-2024",
            "title": "Study period",
            "value": "Use 2010 through 2024 inclusive",
            "affected_paths": ["artifacts/report.md"],
        }
    )
    repo.upsert_source(
        {
            "source_key": "bls-laus",
            "source_type": "dataset",
            "title": "BLS LAUS",
            "url_or_path": "https://www.bls.gov/lau/",
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Unemployment fell after 2021.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/labor-market/notes.md"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Labor Market Report",
            "promotion_state": "verified",
            "assumptions": ["research_plan/state/assumptions.json#years-2010-2024"],
            "sources": ["research_plan/state/sources.json#bls-laus"],
            "claims": ["research_plan/state/claims.json#claim-001"],
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "status": "passed",
            "artifact_paths": ["artifacts/report.md"],
        }
    )

    rebuilt = repo.rebuild_all()

    assert rebuilt.assumptions[0].assumption_key == "years-2010-2024"
    assert rebuilt.sources[0].source_key == "bls-laus"
    assert rebuilt.claims[0].claim_key == "claim-001"
    assert rebuilt.artifact_lineage[0].artifact_path == "artifacts/report.md"
    assert rebuilt.verification_runs[0].run_id == "run-001"


def test_assumption_change_marks_dependent_artifacts_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_assumptions(
        [
            {
                "assumption_key": "years-2010-2024",
                "title": "Study period",
                "value": "Use 2010 through 2024 inclusive",
                "affected_paths": ["artifacts/report.md"],
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Labor Market Report",
                "promotion_state": "verified",
                "assumptions": ["research_plan/state/assumptions.json#years-2010-2024"],
            },
            {
                "artifact_path": "artifacts/chart.png",
                "artifact_type": "chart",
                "title": "Chart",
                "promotion_state": "verified",
                "assumptions": ["research_plan/state/assumptions.json#different-assumption"],
            },
        ]
    )

    updated = repo.update_assumption("years-2010-2024", value="Use 2012 through 2024 inclusive")
    lineage = repo.load_artifact_lineage()

    assert updated.value == "Use 2012 through 2024 inclusive"
    assert lineage[0].promotion_state == "stale"
    assert "assumption_changed:years-2010-2024" in lineage[0].stale_reasons
    assert lineage[0].stale_marked_at is not None
    assert lineage[1].promotion_state == "verified"


def test_integrity_repo_rejects_invalid_json_shape(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    assumptions_path = root / "research_plan/state/assumptions.json"
    assumptions_path.write_text(json.dumps({"bad": "shape"}), encoding="utf-8")

    repo = ResearchIntegrityRepo(root)
    with pytest.raises(ValueError, match="must contain a JSON array"):
        repo.load_assumptions()
