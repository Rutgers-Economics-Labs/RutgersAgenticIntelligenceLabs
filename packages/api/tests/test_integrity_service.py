from __future__ import annotations

import duckdb
import pytest

from app.services.integrity_service import (
    apply_source_freshness_policy,
    apply_reproducibility_rerun,
    build_rerun_plan,
    evaluate_default_integrity_benchmark_corpus,
    evaluate_artifact_trust_cases,
    evaluate_claim_verification_cases,
    evaluate_reproducibility_cases,
    evaluate_retrieval_benchmark,
    evaluate_integrity_gate,
    get_artifact_detail,
    get_claim_detail,
    list_claim_summaries,
    list_source_summaries,
    get_source_detail,
    get_integrity_dependency_graph,
    get_stale_dependency_graph,
    hybrid_retrieve,
    load_integrity_indexes,
    mark_script_change_and_list_stale,
    promote_artifact,
    summarize_agent_workflow_health,
    update_assumption_and_mark_stale,
)
from app.services.integrity_benchmarks import seed_default_integrity_benchmark_corpus
from rail.manifest import load_manifest
from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo


def _seed_workflow_scaffolding(root):
    """Create the workflow files most integrity tests reference in lineage.

    The artifact-lineage normalizer (commit 7ad66b6) strips inputs, scripts,
    and verification_commands that don't exist on disk, then downgrades the
    artifact's promotion_state to `draft` because no workflow support
    remains. Tests written before that hardening land on stale `draft`
    state and fail in confusing ways (e.g. "verified" transition checks
    don't fire because the artifact was silently downgraded).

    Centralizing the workflow-file creation here means tests that seed
    realistic lineage references against `topics/analyze.py`,
    `topics/labor/notes.md`, `topics/data.csv`, and
    `scripts/run-verification.sh` see those references survive the
    normalizer pass.
    """
    from pathlib import Path

    root = Path(root)
    files = {
        # Many tests reference artifacts/report.md as a verification target.
        # The verification-run normalizer strips artifact_paths that don't
        # exist AND downgrades status from "passed" to "pending" when all
        # paths are stripped — the file must exist on disk for seeded runs
        # to survive.
        "artifacts/report.md": "# stable report placeholder\n",
        "topics/analyze.py": "# analysis script placeholder\n",
        "topics/labor/notes.md": "# labor evidence notes placeholder\n",
        "topics/data.csv": "id,value\n1,100\n",
        "topics/scripts/transform.py": "# transform script placeholder\n",
        "topics/analysis.csv": "id,value\n1,100\n",
        "topics/analysis/analyze.py": "# analysis pipeline placeholder\n",
        "topics/analysis/notes.md": "# analysis notes placeholder\n",
        "topics/briefing.md": "# briefing note placeholder\n",
        "topics/notes.md": "# evidence notes placeholder\n",
        "topics/lit/synthesis.md": "# literature synthesis placeholder\n",
        "scripts/run-verification.sh": "#!/usr/bin/env bash\nexit 0\n",
        "scripts/run-rerun.sh": "#!/usr/bin/env bash\nexit 0\n",
        # bootstrap creates .ontology/pipelines/ but no default.yaml; many
        # tests reference it as a script in lineage. Skip onto.duckdb — some
        # tests open it as a real DuckDB and pre-creating it as an empty
        # file would corrupt the open call.
        ".ontology/pipelines/default.yaml": "ontology: .ontology/ontology.yaml\nsteps: []\n",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    # Many reproducibility-rerun tests reference `.ontology/onto.duckdb` as an
    # input. The lineage normalizer strips inputs that don't exist, and the
    # rerun then reports "missing reproducibility metadata" → failed → the
    # artifact cascades to `blocked`, breaking subsequent assertions. Create a
    # valid (empty) DuckDB file so the reference survives. Skip if the test
    # has already written one.
    duckdb_path = root / ".ontology" / "onto.duckdb"
    if not duckdb_path.exists():
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(duckdb_path))
        conn.close()


def test_load_integrity_indexes_reads_repo_backed_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
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


def test_summarize_agent_workflow_health_ignores_internal_hydration_metadata_dataset(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Hydration Metadata Workflow Project", slug="hydration-meta-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/.rail_hydration.json",
                "artifact_type": "dataset",
                "title": "Hydration metadata",
                "promotion_state": "draft",
                "sources": [],
            },
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Analysis dataset",
                "promotion_state": "draft",
                "sources": [],
            },
        ]
    )

    workflow = summarize_agent_workflow_health(root)

    assert ".ontology/.rail_hydration.json" not in workflow["data"]["datasetsMissingProvenance"]
    assert ".ontology/.rail_hydration.json" not in workflow["data"]["datasetsMissingFreshness"]
    assert "topics/analysis.csv" in workflow["data"]["datasetsMissingProvenance"]
    assert "topics/analysis.csv" in workflow["data"]["datasetsMissingFreshness"]


def test_update_assumption_and_mark_stale_updates_lineage(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
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
    _seed_workflow_scaffolding(root)
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


def test_evaluate_integrity_gate_blocks_semantic_suggestion_claims(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_claims(
        [
            {
                "claim_key": "claim-1",
                "claim_text": "A semantically plausible claim",
                "status": "supported",
                "source_keys": ["lead-source"],
                "evidence_kind": "semantic_suggestion",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "claims": ["research_plan/state/claims.json#claim-1"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert "claim-1" in gate["blockingClaims"]


def test_evaluate_integrity_gate_allows_supported_claim_with_attached_chunk_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "This briefing documents transmission congestion and queue delays."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-1",
                "claim_text": "Queue delays are linked to congestion.",
                "status": "supported",
                "source_keys": ["briefing-note"],
                "evidence_chunk_keys": [chunk_key],
                "evidence_kind": "direct",
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert "claim-1" not in gate["blockingClaims"]


def test_claim_verification_benchmark_evaluates_supported_and_semantic_claims(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "Congestion evidence."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-supported",
                "claim_text": "Congestion increased queue delays.",
                "status": "supported",
                "source_keys": ["briefing-note"],
                "evidence_chunk_keys": [chunk_key],
                "evidence_kind": "direct",
            },
            {
                "claim_key": "claim-semantic",
                "claim_text": "Nearby regions may show a similar pattern.",
                "status": "supported",
                "source_keys": ["briefing-note"],
                "evidence_kind": "semantic_suggestion",
            },
        ]
    )

    evaluation = evaluate_claim_verification_cases(
        root,
        [
            {
                "claimKey": "claim-supported",
                "expectedStatus": "supported",
                "expectedEvidenceComplete": True,
            },
            {
                "claimKey": "claim-semantic",
                "expectedStatus": "supported",
                "expectedEvidenceComplete": False,
            },
        ],
    )

    assert evaluation["summary"]["passedCases"] == 2


def test_artifact_trust_benchmark_flags_missing_lineage_and_stale_source_cases(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "stale-source",
                "source_type": "dataset",
                "title": "Stale Source",
                "url_or_path": "https://example.com/stale.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "stale",
                "quality_status": "validated",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/missing-lineage.md",
                "artifact_type": "report",
                "title": "Missing Lineage",
                "promotion_state": "draft",
            },
            {
                "artifact_path": "artifacts/stale-report.md",
                "artifact_type": "report",
                "title": "Stale Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "sources": ["research_plan/state/sources.json#stale-source"],
            },
        ]
    )

    evaluation = evaluate_artifact_trust_cases(
        root,
        [
            {
                "manifest": load_manifest(root),
                "action": "artifact_generation",
                "expectedBlocked": True,
                "expectedBlockingArtifacts": ["artifacts/missing-lineage.md", "artifacts/stale-report.md"],
            }
        ],
    )

    assert evaluation["summary"]["passedCases"] == 1


def test_artifact_trust_benchmark_degrades_after_stale_source_update(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "tracked-source",
                "source_type": "dataset",
                "title": "Tracked Source",
                "url_or_path": "https://example.com/tracked.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "Tracked benchmark source."},
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/tracked-report.md",
                "artifact_type": "report",
                "title": "Tracked Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "sources": ["research_plan/state/sources.json#tracked-source"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/tracked-report.md"],
            }
        ]
    )

    before = evaluate_artifact_trust_cases(
        root,
        [
            {
                "manifest": load_manifest(root),
                "action": "artifact_generation",
                "expectedBlocked": False,
                "expectedBlockingArtifacts": [],
            }
        ],
    )
    repo.update_source("tracked-source", freshness_status="stale")
    after = evaluate_artifact_trust_cases(
        root,
        [
            {
                "manifest": load_manifest(root),
                "action": "artifact_generation",
                "expectedBlocked": True,
                "expectedBlockingArtifacts": ["artifacts/tracked-report.md"],
            }
        ],
    )

    assert before["summary"]["passedCases"] == 1
    assert after["summary"]["passedCases"] == 1


def test_promote_artifact_blocks_when_only_source_is_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "stale-source",
                "source_type": "dataset",
                "title": "Stale Source",
                "url_or_path": "https://example.com/stale.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "stale",
                "quality_status": "validated",
                "provenance": {"text": "Historical extract awaiting refresh."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["stale-source"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#stale-source"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    assert result["status"] == "blocked"
    assert result["artifact"]["promotion_state"] == "partially_verified"
    assert "artifacts/report.md" in result["gate"]["blockingArtifacts"]
    assert any("stale sources" in reason.lower() for reason in result["gate"]["reasons"])


def test_reproducibility_benchmark_verifies_rerun_restores_trust_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("stable report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": [],
                "stale_reasons": ["source_changed:sample"],
            }
        ]
    )

    evaluation = evaluate_reproducibility_cases(
        root,
        [
            {
                "outputs": {"artifacts/report.md": "stable report\n"},
                "runId": "rerun-001",
                "expectedStatus": "passed",
                "expectedArtifactStates": {"artifacts/report.md": "partially_verified"},
            }
        ],
    )

    assert evaluation["summary"]["passedCases"] == 1


def test_apply_reproducibility_rerun_clears_stale_when_outputs_match(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("final report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": [],
                "stale_reasons": ["source_changed:sample"],
            }
        ]
    )

    result = apply_reproducibility_rerun(
        root,
        {"artifacts/report.md": "final report\n"},
        run_id="rerun-001",
    )

    assert result["status"] == "passed"
    assert result["verificationRun"]["status"] == "passed"
    updated = ResearchIntegrityRepo(root).load_artifact_lineage()[0]
    assert updated.promotion_state == "partially_verified"
    assert updated.stale_reasons == []


def test_apply_reproducibility_rerun_records_diff_and_keeps_artifact_blocked_or_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("final report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": [],
            }
        ]
    )

    result = apply_reproducibility_rerun(
        root,
        {"artifacts/report.md": "changed report\n"},
        run_id="rerun-002",
    )

    assert result["status"] == "failed"
    assert result["verificationRun"]["status"] == "failed"
    assert result["verificationRun"]["checks"][0]["status"] == "diff"
    assert "diff" in result["verificationRun"]["checks"][0]
    updated = ResearchIntegrityRepo(root).load_artifact_lineage()[0]
    assert updated.promotion_state in {"blocked", "stale"}
    assert "rerun_diff:rerun-002" in updated.stale_reasons


def test_apply_reproducibility_rerun_rejects_manual_artifacts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("manual report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "reproducibility_mode": "manual",
                "sources": ["research_plan/state/sources.json#sample"],
            }
        ]
    )

    result = apply_reproducibility_rerun(
        root,
        {"artifacts/report.md": "manual report\n"},
        run_id="rerun-manual",
    )

    assert result["status"] == "failed"
    assert result["verificationRun"]["checks"][0]["status"] == "non_reproducible"


def test_apply_source_freshness_policy_marks_sources_needs_refresh_or_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "doc-source",
                "source_type": "document",
                "title": "Document Source",
                "url_or_path": "notes/doc.md",
                "origin": "Internal",
                "acquired_at": "2025-12-01T00:00:00Z",
                "access_method": "manual",
                "freshness_status": "fresh",
            },
            {
                "source_key": "api-source",
                "source_type": "api",
                "title": "API Source",
                "url_or_path": "https://example.com/api",
                "origin": "Provider",
                "acquired_at": "2026-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
            },
        ]
    )

    result = apply_source_freshness_policy(root, as_of="2026-05-14T00:00:00Z")

    status_by_key = {item["source"]["source_key"]: item["nextStatus"] for item in result["changedSources"]}
    assert status_by_key["doc-source"] == "needs_refresh"
    assert status_by_key["api-source"] == "stale"


def test_apply_source_freshness_policy_propagates_stale_dependencies(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "api-source",
                "source_type": "api",
                "title": "API Source",
                "url_or_path": "https://example.com/api",
                "origin": "Provider",
                "acquired_at": "2026-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "A dependent claim.",
                "source_keys": ["api-source"],
                "status": "supported",
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
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#api-source"],
            }
        ]
    )

    result = apply_source_freshness_policy(root, as_of="2026-05-14T00:00:00Z")

    assert result["affectedClaims"][0]["status"] == "stale"
    assert result["affectedArtifacts"][0]["promotion_state"] == "stale"


def test_build_rerun_plan_summarizes_affected_artifacts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
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
    assert plan["assumptions"][0]["assumption_key"] == "years-2010-2024"
    assert plan["affectedPaths"] == ["artifacts/report.md"]
    assert plan["stalePaths"] == ["artifacts/report.md"]
    assert len(plan["proposedTasks"]) >= 2


def test_build_rerun_plan_orders_affected_paths_by_dependency(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "study-period",
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
                "inputs": [".ontology/onto.duckdb"],
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            },
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Ontology DuckDB",
                "promotion_state": "stale",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            },
        ]
    )

    plan = build_rerun_plan(root, "study-period")

    assert plan["affectedPaths"] == [".ontology/onto.duckdb", "artifacts/report.md"]
    assert plan["stalePaths"] == [".ontology/onto.duckdb", "artifacts/report.md"]


def test_evaluate_integrity_gate_blocks_stale_or_unprovenanced_dataset_sources(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "freshness_status": "stale",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/labor.csv",
                "artifact_type": "dataset",
                "title": "Labor Extract",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#bls-laus"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/labor.csv" in gate["blockingArtifacts"]
    assert any("provenance" in reason.lower() or "stale sources" in reason.lower() for reason in gate["reasons"])


def test_evaluate_integrity_gate_blocks_inadmissible_dataset_sources(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "synthetic-benchmark",
                "source_type": "dataset",
                "title": "Synthetic Benchmark",
                "url_or_path": "generated://synthetic.csv",
                "freshness_status": "fresh",
                "provenance": {"synthetic": True},
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/benchmark.csv",
                "artifact_type": "dataset",
                "title": "Benchmark Extract",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#synthetic-benchmark"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/benchmark.csv" in gate["blockingArtifacts"]
    assert any("synthetic" in reason.lower() or "estimated" in reason.lower() for reason in gate["reasons"])


def test_promote_artifact_blocks_dataset_without_provenance(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "freshness_status": "fresh",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Hydrated Dataset",
                "promotion_state": "partially_verified",
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "scripts": [".ontology/pipelines/default.yaml"],
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), ".ontology/onto.duckdb", target_state="verified")

    assert result["status"] == "blocked"
    assert result["artifact"]["promotion_state"] == "partially_verified"
    assert ".ontology/onto.duckdb" in result["gate"]["blockingArtifacts"]
    assert any("provenance" in reason.lower() for reason in result["gate"]["reasons"])


def test_get_claim_detail_returns_sources_artifacts_and_verification_runs(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "bls-laus",
            "source_type": "dataset",
            "title": "BLS LAUS",
            "url_or_path": "https://example.com/bls.csv",
            "provenance": {"text": "BLS unemployment extract for several years."},
        }
    )
    chunk_key = repo.chunks_for_source("bls-laus")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "evidence_chunk_keys": [chunk_key],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "caveats": ["Seasonal adjustment may revise the series."],
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
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "scope": "artifact",
                "loop_type": "analysis_reproducibility",
                "status": "passed",
                "artifacts_checked": ["artifacts/report.md"],
                "claims_checked": ["claim-001"],
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    detail = get_claim_detail(root, "claim-001")

    assert detail["claim"]["claim_key"] == "claim-001"
    assert detail["claim"]["caveats"] == ["Seasonal adjustment may revise the series."]
    assert detail["sources"][0]["source_key"] == "bls-laus"
    assert detail["chunks"][0]["source_key"] == "bls-laus"
    assert detail["artifacts"][0]["artifact_path"] == "artifacts/report.md"
    assert detail["verificationRuns"][0]["run_id"] == "run-001"


def test_get_stale_dependency_graph_returns_source_claim_artifact_edges(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "freshness_status": "stale",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "source_keys": ["bls-laus"],
                "status": "stale",
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
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "stale_reasons": ["source_changed:bls-laus"],
            }
        ]
    )

    graph = get_stale_dependency_graph(root)

    assert graph["summary"]["staleSourceCount"] == 1
    assert graph["summary"]["staleClaimCount"] == 1
    assert graph["summary"]["staleArtifactCount"] == 1
    edge_pairs = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    assert ("source:bls-laus", "claim:claim-001") in edge_pairs
    assert ("claim:claim-001", "artifact:artifacts/report.md") in edge_pairs


def test_evaluate_integrity_gate_blocks_artifacts_missing_reproducibility_metadata(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert any("inputs, scripts, verification commands, and verification runs" in reason for reason in gate["reasons"])


def test_summarize_agent_workflow_health_flags_missing_verification_commands(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )

    workflow = summarize_agent_workflow_health(root)

    assert workflow["coding"]["status"] == "blocked"
    assert workflow["coding"]["artifactsMissingVerificationCommands"] == ["artifacts/report.md"]


def test_summarize_agent_workflow_health_flags_inadmissible_sources(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "estimated-series",
                "source_type": "dataset",
                "title": "Estimated Series",
                "url_or_path": "estimate://series.csv",
                "freshness_status": "fresh",
                "admissibility_status": "estimated",
            }
        ]
    )

    workflow = summarize_agent_workflow_health(root)

    assert workflow["health"]["status"] == "blocked"
    assert workflow["health"]["inadmissibleSources"] == ["estimated-series"]


def test_summarize_agent_workflow_health_ignores_manual_artifacts_for_coding_lineage(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "briefing-note",
                "source_type": "document",
                "title": "Briefing Note",
                "url_or_path": "notes/briefing.md",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
                "freshness_status": "fresh",
                "quality_status": "validated",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/manual-report.md",
                "artifact_type": "report",
                "title": "Manual Report",
                "promotion_state": "draft",
                "reproducibility_mode": "manual",
                "sources": ["research_plan/state/sources.json#briefing-note"],
            }
        ]
    )

    workflow = summarize_agent_workflow_health(root)

    assert workflow["coding"]["status"] == "ready"
    assert workflow["coding"]["artifactsMissingLineage"] == []


def test_summarize_agent_workflow_health_flags_dataset_sources_missing_freshness(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "unknown",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Analysis Dataset",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#bls-laus"],
            }
        ]
    )

    workflow = summarize_agent_workflow_health(root)

    assert workflow["data"]["status"] == "blocked"
    assert workflow["data"]["datasetsMissingFreshness"] == ["topics/analysis.csv"]


def test_evaluate_integrity_gate_blocks_unlabeled_manual_artifacts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "briefing-note",
                "source_type": "document",
                "title": "Briefing Note",
                "url_or_path": "notes/briefing.md",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/manual-report.md",
                "artifact_type": "report",
                "title": "Manual Report",
                "promotion_state": "draft",
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/manual-report.md" in gate["blockingArtifacts"]
    assert any("explicitly labeled" in reason for reason in gate["reasons"])


def test_evaluate_integrity_gate_allows_explicit_manual_artifact_label(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "briefing-note",
                "source_type": "document",
                "title": "Briefing Note",
                "url_or_path": "notes/briefing.md",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/manual-report.md",
                "artifact_type": "report",
                "title": "Manual Report",
                "promotion_state": "draft",
                "reproducibility_mode": "manual",
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert "artifacts/manual-report.md" not in gate["blockingArtifacts"]
    assert not any("explicitly labeled" in reason for reason in gate["reasons"])


def test_evaluate_integrity_gate_blocks_final_artifacts_with_unprovenanced_sources(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "briefing-note",
                "source_type": "document",
                "title": "Briefing Note",
                "url_or_path": "notes/briefing.md",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "sources": ["research_plan/state/sources.json#briefing-note"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert any("final artifacts can be promoted" in reason for reason in gate["reasons"])


def test_mark_script_change_and_list_stale_marks_linked_outputs(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Dataset",
                "promotion_state": "verified",
                "scripts": ["topics/scripts/transform.py"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "scripts": ["topics/scripts/transform.py"],
            },
        ]
    )

    stale = mark_script_change_and_list_stale(root, "topics/scripts/transform.py")

    assert {item.artifact_path for item in stale} == {"topics/analysis.csv", "artifacts/report.md"}
    assert all(item.promotion_state == "stale" for item in stale)


def test_evaluate_integrity_gate_blocks_artifacts_backed_by_blocked_sources(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "state-brief",
                "source_type": "document",
                "title": "State Brief",
                "url_or_path": "https://example.com/brief.pdf",
                "origin": "State Agency",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "web",
                "quality_status": "blocked",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "A policy reduced costs.",
                "source_keys": ["state-brief"],
                "status": "conflicted",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#state-brief"],
            }
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")

    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert any("blocked or rejected sources" in reason for reason in gate["reasons"])


def test_evaluate_integrity_gate_applies_closeout_requirements(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
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
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-002",
                "claim_text": "A semantic lead suggests a similar pattern elsewhere.",
                "artifact_path": "artifacts/report.md",
                "source_keys": ["semantic-lead"],
                "evidence_kind": "semantic_suggestion",
                "status": "supported",
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "scope": "artifact",
                "loop_type": "analysis_reproducibility",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )
    repo.write_artifact_lineage(
        [
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
        ]
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="closeout")

    assert gate["blocked"] is True
    assert "claim-002" in gate["blockingClaims"]
    assert any("Report claims need evidence" in reason for reason in gate["reasons"])


def test_contradicting_supported_claims_become_conflicted_and_block_artifacts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "source-a",
                "source_type": "document",
                "title": "Source A",
                "url_or_path": "https://example.com/a.pdf",
                "origin": "Agency A",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "web",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "Source A says costs fell after the reform."},
            },
            {
                "source_key": "source-b",
                "source_type": "document",
                "title": "Source B",
                "url_or_path": "https://example.com/b.pdf",
                "origin": "Agency B",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "web",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "Source B says costs rose after the reform."},
            },
        ]
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "verified",
            "inputs": ["topics/data.csv"],
            "scripts": ["topics/analyze.py"],
            "claims": [
                "research_plan/state/claims.json#claim-fell",
                "research_plan/state/claims.json#claim-rose",
            ],
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-fell",
            "claim_text": "Costs fell after the reform.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/analysis/fell.md"],
            "source_keys": ["source-a"],
            "status": "supported",
            "evidence_kind": "direct",
            "contradicts_claim_keys": ["claim-rose"],
        }
    )
    conflicted = repo.upsert_claim(
        {
            "claim_key": "claim-rose",
            "claim_text": "Costs rose after the reform.",
            "artifact_path": "artifacts/report.md",
            "evidence_paths": ["topics/analysis/rose.md"],
            "source_keys": ["source-b"],
            "status": "supported",
            "evidence_kind": "direct",
            "contradicts_claim_keys": ["claim-fell"],
        }
    )

    gate = evaluate_integrity_gate(root, load_manifest(root), action="artifact_generation")
    detail = get_claim_detail(root, "claim-fell")
    updated_artifact = next(item for item in repo.load_artifact_lineage() if item.artifact_path == "artifacts/report.md")

    assert conflicted.status == "conflicted"
    assert detail["claim"]["status"] == "conflicted"
    assert detail["contradictoryClaims"][0]["claim_key"] == "claim-rose"
    assert updated_artifact.promotion_state == "blocked"
    assert "claim_conflicted:claim-fell" in updated_artifact.stale_reasons
    assert gate["blocked"] is True
    assert "artifacts/report.md" in gate["blockingArtifacts"]
    assert any("Conflicted claims must be resolved" in reason for reason in gate["reasons"])


def test_promote_artifact_transitions_to_verified_when_gate_passes(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "topics" / "labor").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "report.md").write_text("report", encoding="utf-8")
    (root / "topics" / "data.csv").write_text("value\n1\n", encoding="utf-8")
    (root / "topics" / "analyze.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "run-verification.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (root / "topics" / "labor" / "notes.md").write_text("evidence", encoding="utf-8")
    (root / ".ontology").mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(root / ".ontology" / "onto.duckdb"))
    conn.execute("CREATE TABLE county (name VARCHAR)")
    conn.execute("INSERT INTO county VALUES ('Middlesex')")
    conn.close()
    (root / ".ontology" / ".rail_hydration.json").write_text("{}", encoding="utf-8")
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "admissibility_status": "observed",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    assert result["status"] == "promoted"
    assert result["artifact"]["promotion_state"] == "verified"


def test_promote_artifact_blocks_report_when_ontology_hydration_duckdb_is_empty(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "topics" / "labor").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "artifacts" / "report.md").write_text("report", encoding="utf-8")
    (root / "topics" / "data.csv").write_text("value\n1\n", encoding="utf-8")
    (root / "topics" / "analyze.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "run-verification.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (root / "topics" / "labor" / "notes.md").write_text("evidence", encoding="utf-8")
    (root / ".ontology").mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(root / ".ontology" / "onto.duckdb"))
    conn.execute("CREATE TABLE county (name VARCHAR)")
    conn.close()
    (root / ".ontology" / ".rail_hydration.json").write_text("{}", encoding="utf-8")
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "admissibility_status": "observed",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    assert result["status"] == "blocked"
    assert "artifacts/report.md" in result["gate"]["blockingArtifacts"]
    assert any("does not contain populated rows" in reason for reason in result["gate"]["reasons"])


def test_promote_artifact_blocks_report_when_ontology_hydration_is_missing(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="verified")

    assert result["status"] == "blocked"
    assert "artifacts/report.md" in result["gate"]["blockingArtifacts"]
    assert any("Ontology hydration must exist" in reason for reason in result["gate"]["reasons"])


def test_get_artifact_detail_returns_linked_records_and_trust_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "baseline-window",
                "title": "Baseline window",
                "value": "2018-2020",
            }
        ]
    )
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
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
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "assumptions": ["research_plan/state/assumptions.json#baseline-window"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    detail = get_artifact_detail(root, "artifacts/report.md", manifest=load_manifest(root))

    assert detail["artifact"]["artifact_path"] == "artifacts/report.md"
    assert detail["sources"][0]["source_key"] == "bls-laus"
    assert detail["claims"][0]["claim_key"] == "claim-001"
    assert detail["assumptions"][0]["assumption_key"] == "baseline-window"
    assert detail["verificationRuns"][0]["run_id"] == "run-001"
    assert detail["trustState"]["currentState"] == "verified"
    assert detail["trustState"]["isTrusted"] is True
    assert detail["trustSummary"]["recommendedNextAction"] == "Trust state is current."
    assert detail["trustSummary"]["hasEvidence"] is True
    assert detail["trustSummary"]["isReproducible"] is True


def test_get_claim_detail_returns_claim_state_summary(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "Congestion increased queue delays."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays increased after congestion worsened.",
                "artifact_path": "artifacts/report.md",
                "evidence_chunk_keys": [chunk_key],
                "source_keys": ["briefing-note"],
                "status": "supported",
                "evidence_kind": "direct",
                "caveats": ["Regional coverage is incomplete."],
                "open_questions": ["Does the same hold in winter peaks?"],
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
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    detail = get_claim_detail(root, "claim-001")

    assert detail["claimState"]["status"] == "supported"
    assert detail["claimState"]["evidenceComplete"] is True
    assert detail["claimState"]["isExplicitEvidence"] is True
    assert detail["claimState"]["caveatCount"] == 1
    assert detail["claimState"]["openQuestionCount"] == 1
    assert detail["trustSummary"]["entityType"] == "claim"
    assert detail["trustSummary"]["isTrusted"] is True
    assert detail["trustSummary"]["recommendedNextAction"] == "Claim state is current."


def test_get_source_detail_returns_source_state_summary(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "needs_refresh",
            "quality_status": "validated",
            "provenance": {"text": "Congestion increased queue delays."},
        }
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays increased after congestion worsened.",
                "artifact_path": "artifacts/report.md",
                "source_keys": ["briefing-note"],
                "status": "supported",
                "evidence_kind": "direct",
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
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    detail = get_source_detail(root, "briefing-note")

    assert detail["sourceState"]["freshnessStatus"] == "needs_refresh"
    assert detail["sourceState"]["needsRefresh"] is True
    assert detail["sourceState"]["isFresh"] is False
    assert detail["sourceState"]["dependentClaimCount"] == 1
    assert detail["sourceState"]["dependentArtifactCount"] == 1
    assert detail["trustSummary"]["entityType"] == "source"
    assert detail["trustSummary"]["isTrusted"] is False
    assert detail["trustSummary"]["recommendedNextAction"] == "Refresh this source and rerun dependent analyses."


def test_list_source_summaries_include_source_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "freshness_status": "stale",
            "quality_status": "validated",
            "provenance": {"text": "Congestion increased queue delays."},
        }
    )

    sources = list_source_summaries(root)

    assert sources[0]["source_key"] == "briefing-note"
    assert sources[0]["sourceState"]["isStale"] is True


def test_list_claim_summaries_include_claim_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays increased after congestion worsened.",
                "status": "needs_evidence",
                "open_questions": ["Does the same hold in winter peaks?"],
            }
        ]
    )

    claims = list_claim_summaries(root)

    assert claims[0]["claim_key"] == "claim-001"
    assert claims[0]["claimState"]["evidenceComplete"] is False
    assert claims[0]["claimState"]["openQuestionCount"] == 1


def test_get_integrity_dependency_graph_returns_explicit_relationships(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "baseline-window",
                "title": "Baseline window",
                "value": "2018-2020",
            }
        ]
    )
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "Congestion increased queue delays in the region."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays increased after congestion worsened.",
                "artifact_path": "artifacts/report.md",
                "evidence_chunk_keys": [chunk_key],
                "source_keys": ["briefing-note"],
                "status": "supported",
                "evidence_kind": "direct",
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
                "scripts": ["topics/analyze.py"],
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "assumptions": ["research_plan/state/assumptions.json#baseline-window"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    graph = get_integrity_dependency_graph(root)
    relationships = {(item["from"], item["to"], item["relationship"]) for item in graph["edges"]}

    assert ("source:briefing-note", f"chunk:{chunk_key}", "chunked_as") in relationships
    assert ("source:briefing-note", "claim:claim-001", "supports") in relationships
    assert (f"chunk:{chunk_key}", "claim:claim-001", "supports") in relationships
    assert ("claim:claim-001", "artifact:artifacts/report.md", "supports") in relationships
    assert ("artifact:artifacts/report.md", "source:briefing-note", "derived_from") in relationships
    assert ("artifact:artifacts/report.md", "assumption:baseline-window", "depends_on") in relationships
    assert ("artifact:artifacts/report.md", "method:topics/analyze.py", "generated_by") in relationships
    assert any(item["edgeKey"] == "source:briefing-note|supports|claim:claim-001" for item in graph["edges"])


def test_get_integrity_dependency_graph_exposes_dataset_nodes_and_dependencies(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Hydrated Dataset",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "scripts": ["pipelines/hydrate.py"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
            },
        ]
    )

    graph = get_integrity_dependency_graph(root)
    node_types = {item["id"]: item["type"] for item in graph["nodes"]}
    relationships = {(item["from"], item["to"], item["relationship"]) for item in graph["edges"]}

    assert node_types["dataset:.ontology/onto.duckdb"] == "dataset"
    assert ("dataset:.ontology/onto.duckdb", "source:bls-laus", "derived_from") in relationships
    assert ("dataset:.ontology/onto.duckdb", "method:pipelines/hydrate.py", "generated_by") in relationships
    assert ("artifact:artifacts/report.md", "dataset:.ontology/onto.duckdb", "depends_on") in relationships
    assert graph["summary"]["datasetCount"] == 1


def test_promote_artifact_returns_blocked_when_gate_fails(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unsupported claim.",
                "artifact_path": "artifacts/report.md",
                "status": "needs_evidence",
            }
        ]
    )

    result = promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="partially_verified")

    assert result["status"] == "blocked"
    assert result["artifact"]["promotion_state"] == "draft"
    assert result["gate"]["blocked"] is True


def test_promote_artifact_rejects_invalid_transition(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    # Seed inputs/scripts so the artifact-lineage normalizer preserves the
    # "verified" promotion_state; without them it gets silently downgraded
    # to "draft" because there's no workflow support evidence.
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
            }
        ]
    )

    with pytest.raises(ValueError, match="Invalid promotion transition"):
        promote_artifact(root, load_manifest(root), "artifacts/report.md", target_state="draft")


def test_hybrid_retrieve_returns_explicit_evidence_and_semantic_suggestions(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS Labor Force Data",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
            {
                "source_key": "regional-brief",
                "source_type": "document",
                "title": "Regional labor narrative brief",
                "url_or_path": "notes/brief.md",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-supported",
                "claim_text": "Labor market unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            },
            {
                "claim_key": "claim-semantic",
                "claim_text": "A labor pattern appears comparable in nearby regions.",
                "artifact_path": "artifacts/report.md",
                "source_keys": ["regional-brief"],
                "status": "supported",
                "evidence_kind": "semantic_suggestion",
            },
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Labor Report",
                "promotion_state": "verified",
                "sources": [
                    "research_plan/state/sources.json#bls-laus",
                    "research_plan/state/sources.json#regional-brief",
                ],
                "claims": [
                    "research_plan/state/claims.json#claim-supported",
                    "research_plan/state/claims.json#claim-semantic",
                ],
            }
        ]
    )

    result = hybrid_retrieve(root, "labor unemployment report", limit=6)

    assert result["summary"]["explicitEvidenceCount"] >= 1
    assert result["summary"]["semanticSuggestionCount"] >= 1
    claim_results = {item["recordKey"]: item for item in result["results"] if item["recordType"] == "claim"}
    assert claim_results["claim-supported"]["resultType"] == "explicit_evidence"
    assert claim_results["claim-semantic"]["resultType"] == "semantic_suggestion"


def test_hybrid_retrieve_excludes_stale_sources_unless_requested(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "stale-source",
                "source_type": "dataset",
                "title": "Stale unemployment extract",
                "url_or_path": "https://example.com/stale.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "stale",
                "quality_status": "validated",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-stale",
                "claim_text": "Unemployment changed in the stale extract.",
                "source_keys": ["stale-source"],
                "status": "stale",
            }
        ]
    )

    filtered = hybrid_retrieve(root, "stale unemployment", limit=5)
    included = hybrid_retrieve(root, "stale unemployment", limit=5, include_stale=True)

    assert filtered["results"] == []
    assert {item["recordKey"] for item in included["results"]} >= {"stale-source", "claim-stale"}


def test_hybrid_retrieve_excludes_blocked_sources_unless_requested(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "blocked-source",
                "source_type": "dataset",
                "title": "Blocked unemployment extract",
                "url_or_path": "https://example.com/blocked.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "blocked",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-blocked",
                "claim_text": "Unemployment changed in the blocked extract.",
                "source_keys": ["blocked-source"],
                "status": "conflicted",
            }
        ]
    )

    filtered = hybrid_retrieve(root, "blocked unemployment", limit=5)
    included = hybrid_retrieve(root, "blocked unemployment", limit=5, include_blocked=True)

    assert filtered["results"] == []
    assert "blocked-source" in {item["recordKey"] for item in included["results"]}


def test_hybrid_retrieve_supports_date_window_filters(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "older-source",
                "source_type": "dataset",
                "title": "Older labor extract",
                "url_or_path": "https://example.com/older.csv",
                "origin": "BLS",
                "acquired_at": "2024-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
            {
                "source_key": "recent-source",
                "source_type": "dataset",
                "title": "Recent labor extract",
                "url_or_path": "https://example.com/recent.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
        ]
    )

    filtered = hybrid_retrieve(
        root,
        "labor extract",
        limit=10,
        date_from="2026-01-01T00:00:00Z",
        date_to="2026-12-31T23:59:59Z",
    )

    result_keys = {item["recordKey"] for item in filtered["results"] if item["recordType"] == "source"}
    assert "recent-source" in result_keys
    assert "older-source" not in result_keys
    assert filtered["filters"]["dateFrom"] == "2026-01-01T00:00:00Z"
    assert filtered["filters"]["dateTo"] == "2026-12-31T23:59:59Z"


def test_hybrid_retrieve_returns_chunk_results_with_source_metadata(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "This note covers interconnection queues, transmission congestion, and reliability planning in several regions."
            },
        }
    )

    result = hybrid_retrieve(root, "transmission congestion planning", limit=5)

    chunk_results = [item for item in result["results"] if item["recordType"] == "chunk"]
    assert chunk_results
    assert chunk_results[0]["resultType"] == "semantic_suggestion"
    assert chunk_results[0]["sourceMetadata"]["source_title"] == "Briefing Note"
    stored_chunk = repo.chunks_for_source("briefing-note")[0]
    assert stored_chunk.embedding_model == "token_hash_v1"
    assert len(stored_chunk.embedding) == 256


def test_hybrid_retrieve_marks_attached_chunk_as_explicit_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "policy-note",
            "source_type": "document",
            "title": "Policy Note",
            "url_or_path": "topics/policy-note.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "This policy note explains queue delays and transmission congestion."
            },
        }
    )
    chunk_key = repo.chunks_for_source("policy-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays are tied to transmission congestion.",
                "source_keys": ["policy-note"],
                "evidence_chunk_keys": [chunk_key],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )

    result = hybrid_retrieve(root, "queue delays transmission congestion", limit=5)

    chunk_results = {item["recordKey"]: item for item in result["results"] if item["recordType"] == "chunk"}
    assert chunk_results[chunk_key]["resultType"] == "explicit_evidence"
    assert chunk_results[chunk_key]["claimKeys"] == ["claim-001"]
    assert chunk_results[chunk_key]["graphPath"] == [f"chunk:{chunk_key}", "claim:claim-001"]
    assert chunk_results[chunk_key]["trustBasis"] == "matched chunk with persisted chunk->claim support edge"


def test_hybrid_retrieve_uses_persisted_edges_for_explicit_expansion(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "policy-note",
            "source_type": "document",
            "title": "Policy Note",
            "url_or_path": "topics/policy-note.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "This policy note explains queue delays and transmission congestion."
            },
        }
    )
    chunk_key = repo.chunks_for_source("policy-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays are tied to transmission congestion.",
                "source_keys": ["policy-note"],
                "evidence_chunk_keys": [],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )

    result = hybrid_retrieve(root, "queue delays transmission congestion", limit=5)

    chunk_results = {item["recordKey"]: item for item in result["results"] if item["recordType"] == "chunk"}
    assert chunk_results[chunk_key]["resultType"] == "semantic_suggestion"
    assert chunk_results[chunk_key]["graphPath"] == [f"chunk:{chunk_key}"]
    assert chunk_results[chunk_key]["trustBasis"] == "semantic_match_only"


def test_stale_dependency_graph_includes_invalidated_chunks(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "policy-memo",
            "source_type": "document",
            "title": "Policy Memo",
            "url_or_path": "topics/policy.md",
            "origin": "State Agency",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "A policy memo about congestion and expansion."},
        }
    )

    repo.update_source("policy-memo", freshness_status="stale")

    graph = get_stale_dependency_graph(root)

    assert graph["summary"]["staleChunkCount"] >= 1
    edge_pairs = {(edge["from"], edge["to"]) for edge in graph["edges"]}
    assert any(pair[0] == "source:policy-memo" and pair[1].startswith("chunk:policy-memo#chunk-") for pair in edge_pairs)


def test_retrieval_benchmark_shows_hybrid_beats_vector_only_on_multi_hop_query(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "queue-brief",
            "source_type": "document",
            "title": "Queue Brief",
            "url_or_path": "topics/queue-brief.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "This brief discusses interconnection queue delays caused by regional transmission congestion."
            },
        }
    )
    chunk_key = repo.chunks_for_source("queue-brief")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Backlog pressure rises when grid expansion stalls.",
                "source_keys": ["queue-brief"],
                "evidence_chunk_keys": [chunk_key],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/output.md",
                "artifact_type": "report",
                "title": "System Output",
                "promotion_state": "verified",
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#queue-brief"],
            }
        ]
    )

    benchmark = evaluate_retrieval_benchmark(
        root,
        [
            {
                "query": "interconnection delays from transmission congestion",
                "expectedRecordKeys": ["claim-001", "artifacts/output.md"],
                "expectedRecordTypes": ["claim", "artifact"],
            }
        ],
        limit=5,
    )

    summary = benchmark["summary"]
    assert summary["hybridHits"] == 1
    assert summary["vectorOnlyHits"] == 0
    assert summary["hybridOutperformsVectorOnly"] is True


def test_default_integrity_benchmark_corpus_exercises_all_evaluation_layers(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)
    corpus = seed_default_integrity_benchmark_corpus(root)

    retrieval = evaluate_retrieval_benchmark(root, corpus["retrievalCases"], limit=5)
    claims = evaluate_claim_verification_cases(root, corpus["claimVerificationCases"])
    artifacts = evaluate_artifact_trust_cases(root, corpus["artifactTrustCases"])
    reproducibility = evaluate_reproducibility_cases(root, corpus["reproducibilityCases"])

    assert corpus["metadata"]["claimKeys"] == ["claim-supported", "claim-semantic"]
    assert retrieval["summary"]["caseCount"] == 2
    assert retrieval["summary"]["hybridHits"] == 2
    assert retrieval["summary"]["hybridOutperformsVectorOnly"] is True
    assert claims["summary"]["passedCases"] == 2
    assert artifacts["summary"]["passedCases"] == 2
    assert reproducibility["summary"]["passedCases"] == 1
    semantic_artifact_case = next(
        case
        for case in artifacts["cases"]
        if "artifacts/semantic-output.md" in case["expectedBlockingArtifacts"]
    )
    assert semantic_artifact_case["passed"] is True


def test_evaluate_default_integrity_benchmark_corpus_returns_combined_report(tmp_path):
    root = bootstrap_future_project(tmp_path, name="API Integrity Project", slug="api-integrity-project")
    _seed_workflow_scaffolding(root)

    report = evaluate_default_integrity_benchmark_corpus(root, retrieval_limit=5)

    assert report["metadata"]["claimKeys"] == ["claim-supported", "claim-semantic"]
    assert report["retrieval"]["summary"]["caseCount"] == 2
    assert report["claims"]["summary"]["passedCases"] == 2
    assert report["artifacts"]["summary"]["passedCases"] == 2
    assert report["reproducibility"]["summary"]["passedCases"] == 1
    assert report["summary"]["caseCount"] == 7
    assert report["summary"]["passedCases"] == 7
    assert report["summary"]["failedCases"] == 0
    assert report["summary"]["hybridOutperformsVectorOnly"] is True
