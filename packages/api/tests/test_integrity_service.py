from __future__ import annotations

from app.services.integrity_service import (
    build_rerun_plan,
    evaluate_integrity_gate,
    load_integrity_indexes,
    update_assumption_and_mark_stale,
)
from rail.manifest import load_manifest
from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo


def test_load_integrity_indexes_reads_repo_backed_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_assumption(
        {
            "assumption_key": "baseline-window",
            "title": "Baseline window",
            "value": "2018-2020",
        }
    )

    indexes = load_integrity_indexes(root)

    assert len(indexes.assumptions) == 1
    assert indexes.assumptions[0].assumption_key == "baseline-window"


def test_update_assumption_and_mark_stale_updates_lineage(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "years-2010-2024",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "assumptions": ["research_plan/state/assumptions.json#years-2010-2024"],
            }
        ]
    )

    updated, stale = update_assumption_and_mark_stale(root, "years-2010-2024", {"value": "2012-2024"})

    assert updated.value == "2012-2024"
    assert len(stale) == 1
    assert stale[0].artifact_path == "artifacts/report.md"
    assert stale[0].promotion_state == "stale"


def test_evaluate_integrity_gate_blocks_promotion_when_claims_need_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_claims(
        [
            {
                "claim_key": "claim-1",
                "claim_text": "A material claim",
                "status": "needs_evidence",
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "claim-1" in gate["blockingClaims"]


def test_build_rerun_plan_summarizes_affected_artifacts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "years-2010-2024",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "assumptions": ["research_plan/state/assumptions.json#years-2010-2024"],
                "stale_reasons": ["assumption_changed:years-2010-2024"],
            }
        ]
    )

    plan = build_rerun_plan(root, "years-2010-2024")

    assert plan["assumption"]["assumption_key"] == "years-2010-2024"
    assert plan["affectedPaths"] == ["artifacts/report.md"]
    assert plan["stalePaths"] == ["artifacts/report.md"]
    assert len(plan["proposedTasks"]) >= 2
