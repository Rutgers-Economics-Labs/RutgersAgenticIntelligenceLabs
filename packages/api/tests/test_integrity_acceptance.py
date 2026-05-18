from __future__ import annotations

from pathlib import Path

from app.services.integrity_service import apply_reproducibility_rerun, evaluate_integrity_gate, promote_artifact
from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo, sync_sources_from_configs
from rail.local import LocalEngine
from rail.manifest import load_manifest


def _bootstrap_hydrated_project(tmp_path: Path):
    root = bootstrap_future_project(tmp_path, name="Acceptance Project", slug="acceptance-project")
    (root / ".ontology" / "sources" / "sample.yaml").write_text(
        "name: Sample Source\nurl: https://example.com/sample.csv\nfields:\n  - name: value\n",
        encoding="utf-8",
    )
    (root / ".ontology" / "pipelines" / "acceptance_pipeline.yaml").write_text(
        "ontology: .ontology/ontology.yaml\nsteps:\n  - api: sample\n",
        encoding="utf-8",
    )
    manifest_text = (root / "rail.yaml").read_text(encoding="utf-8").replace(
        'default_pipeline: "default"',
        'default_pipeline: "acceptance_pipeline"',
    )
    (root / "rail.yaml").write_text(manifest_text, encoding="utf-8")
    engine = LocalEngine(str(root))
    engine.artifact_duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    engine.artifact_duckdb_path.write_bytes(b"")
    engine._write_hydration_meta("acceptance_pipeline", "full")
    sync_sources_from_configs(root, sources_dir=".ontology/sources", source_keys=["sample"])
    engine._record_hydration_lineage("acceptance_pipeline")
    return root, ResearchIntegrityRepo(root)


def test_acceptance_scenario_1_can_ingest_hydrate_and_promote_with_evidence(tmp_path):
    root, repo = _bootstrap_hydrated_project(tmp_path)
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Sample values increased after 2021.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/analysis/notes.md"],
            "source_keys": ["sample"],
            "status": "supported",
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifacts_checked": [".ontology/onto.duckdb", "artifacts/report.md"],
            "claims_checked": ["claim-001"],
            "artifact_paths": [".ontology/onto.duckdb", "artifacts/report.md"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "partially_verified",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "verification_commands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#sample"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
        }
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    promotion = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    assert gate["blocked"] is False
    assert promotion["status"] == "promoted"
    assert promotion["artifact"]["promotion_state"] == "verified"
    dataset = next(item for item in repo.load_artifact_lineage() if item.artifact_path == ".ontology/onto.duckdb")
    assert dataset.sources == ["research_plan/state/sources.json#sample"]


def test_acceptance_scenario_2_source_change_propagates_stale_and_rerun_restores(tmp_path):
    root, repo = _bootstrap_hydrated_project(tmp_path)
    report_path = root / "artifacts" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("stable report\n", encoding="utf-8")
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Sample values increased after 2021.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/analysis/notes.md"],
            "source_keys": ["sample"],
            "status": "supported",
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifacts_checked": ["artifacts/report.md"],
            "claims_checked": ["claim-001"],
            "artifact_paths": ["artifacts/report.md"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "verified",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "verification_commands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#sample"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
        }
    )

    updated, stale_claims, stale_artifacts = repo.update_source("sample", freshness_status="stale")
    blocked_gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert updated.freshness_status == "stale"
    assert stale_claims[0].status == "stale"
    assert stale_artifacts[0].promotion_state == "stale"
    assert blocked_gate["blocked"] is True

    refreshed, refreshed_claims, refreshed_artifacts = repo.update_source("sample", freshness_status="fresh")
    rerun = apply_reproducibility_rerun(
        root,
        {
            ".ontology/onto.duckdb": b"",
            "artifacts/report.md": "stable report\n",
        },
        run_id="run-002",
    )
    promotion = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    restored_gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    restored = next(item for item in repo.load_artifact_lineage() if item.artifact_path == "artifacts/report.md")
    assert refreshed.freshness_status == "fresh"
    assert refreshed_claims[0].status == "supported"
    assert refreshed_artifacts[0].promotion_state == "partially_verified"
    assert rerun["status"] == "passed"
    assert promotion["status"] == "promoted"
    assert restored_gate["blocked"] is False
    assert restored.promotion_state == "verified"


def test_acceptance_scenario_3_semantic_lead_does_not_become_trusted_evidence(tmp_path):
    root, repo = _bootstrap_hydrated_project(tmp_path)
    repo.upsert_source(
        {
            "source_key": "semantic-lead",
            "source_type": "document",
            "title": "Related Blog Post",
            "url_or_path": "https://example.com/blog",
            "origin": "Example Blog",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "web",
            "freshness_status": "fresh",
            "quality_status": "candidate",
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-002",
            "claim_text": "A semantic lead suggests a similar pattern elsewhere.",
            "artifact_path": "artifacts/report.md",
            "source_keys": ["semantic-lead"],
            "evidence_kind": "semantic_suggestion",
            "status": "supported",
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifact_paths": ["artifacts/report.md"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "draft",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "sources": ["research_plan/state/sources.json#semantic-lead"],
            "claims": ["research_plan/state/claims.json#claim-002"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
        }
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    promotion = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="partially_verified")

    assert gate["blocked"] is True
    assert "claim-002" in gate["blockingClaims"]
    assert promotion["status"] == "blocked"
    assert promotion["artifact"]["promotion_state"] == "needs_evidence"


def test_acceptance_scenario_4_missing_lineage_prevents_verification(tmp_path):
    root, repo = _bootstrap_hydrated_project(tmp_path)
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "draft",
            "sources": ["research_plan/state/sources.json#sample"],
        }
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    promotion = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="partially_verified")

    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert promotion["status"] == "blocked"
    assert promotion["artifact"]["promotion_state"] == "draft"


def test_acceptance_scenario_5_conflicting_source_blocks_instead_of_silent_promotion(tmp_path):
    root, repo = _bootstrap_hydrated_project(tmp_path)
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Sample values increased after 2021.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/analysis/notes.md"],
            "source_keys": ["sample"],
            "status": "supported",
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifact_paths": ["artifacts/report.md"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "verified",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "sources": ["research_plan/state/sources.json#sample"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
        }
    )

    updated, conflicted_claims, blocked_artifacts = repo.update_source(
        "sample",
        quality_status="blocked",
        quality_notes="Conflicts with the audited upstream dataset.",
    )
    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    promotion = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="partially_verified")

    assert updated.quality_status == "blocked"
    assert conflicted_claims[0].status == "conflicted"
    assert blocked_artifacts[0].promotion_state == "blocked"
    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert promotion["status"] == "blocked"
    assert promotion["artifact"]["promotion_state"] == "blocked"
