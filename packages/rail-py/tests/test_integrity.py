from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.bootstrap import bootstrap_future_project
from rail.integrity import (
    ArtifactLineageRecord,
    AssumptionRecord,
    ClaimRecord,
    EvidenceChunkRecord,
    IntegrityEdgeRecord,
    ResearchIntegrityRepo,
    STATE_FILE_NAMES,
    SourceRecord,
    VerificationRunRecord,
    sync_sources_from_configs,
)
import rail
from rail import cli as rail_cli


def test_integrity_repo_loads_empty_bootstrap_indexes(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    indexes = repo.load_all()

    assert indexes.assumptions == []
    assert indexes.sources == []
    assert indexes.claims == []
    assert indexes.artifact_lineage == []
    assert indexes.verification_runs == []
    assert indexes.integrity_edges == []


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
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifacts_checked": ["artifacts/report.md"],
            "claims_checked": ["claim-001"],
            "artifact_paths": ["artifacts/report.md"],
        }
    )

    rebuilt = repo.rebuild_all()

    assert rebuilt.assumptions[0].assumption_key == "years-2010-2024"
    assert rebuilt.sources[0].source_key == "bls-laus"
    assert rebuilt.claims[0].claim_key == "claim-001"
    assert rebuilt.artifact_lineage[0].artifact_path == "artifacts/report.md"
    assert rebuilt.verification_runs[0].run_id == "run-001"
    assert any(item.relationship == "supports" for item in rebuilt.integrity_edges)


def test_integrity_repo_loads_legacy_verification_run_records(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    path = root / "research_plan" / "state" / "verification_runs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-05-16T00:00:00Z",
                    "agent_role": "health",
                    "check_type": "deterministic_repo_audit",
                    "command": "bash scripts/run-verification.sh",
                    "status": "failed",
                    "scope": "repo hygiene and ontology-expansion verification audit",
                    "failures": [
                        "Placeholder ontology source configs remain.",
                        "Legacy panel verification is still enabled.",
                    ],
                    "notes": "Legacy health worker output.",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    run = ResearchIntegrityRepo(root).load_verification_runs()[0]

    assert run.scope == "repo hygiene and ontology-expansion verification audit"
    assert run.status == "failed"
    assert run.created_at == "2026-05-16T00:00:00Z"
    assert run.blockers == [
        "Placeholder ontology source configs remain.",
        "Legacy panel verification is still enabled.",
    ]
    assert run.checks[0]["name"] == "deterministic_repo_audit"


def test_integrity_repo_loads_legacy_planner_claim_candidate_records(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    path = root / "research_plan" / "state" / "claims.json"
    path.write_text(
        json.dumps(
            [
                {
                    "claim_id": "ucl_participation_plan_claim_001",
                    "claim": "The ranked UEFA participation source stack is sufficient for a first-pass hydration design.",
                    "status": "candidate",
                    "scope": "planning_evidence",
                    "confidence": "supported",
                    "artifacts": [
                        {"path": "research_plan/uefa_plan.md", "lines": "10-20"},
                        {"path": "artifacts/uefa_execution.md", "lines": "7-14"},
                    ],
                    "notes": "Legacy planner-side claim candidate.",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    claim = ResearchIntegrityRepo(root).load_claims()[0]

    assert claim.claim_key == "ucl_participation_plan_claim_001"
    assert claim.claim_text == "The ranked UEFA participation source stack is sufficient for a first-pass hydration design."
    assert claim.status == "needs_evidence"
    assert claim.artifact_path == "research_plan/uefa_plan.md"
    assert claim.evidence_paths == ["research_plan/uefa_plan.md", "artifacts/uefa_execution.md"]
    assert "Legacy planner-side claim candidate." in claim.caveats
    assert "legacy_scope:planning_evidence" in claim.caveats


def test_integrity_record_models_validate_required_fields():
    with pytest.raises(ValidationError):
        AssumptionRecord.model_validate({"title": "Missing key", "value": "2018-2020"})
    with pytest.raises(ValidationError):
        SourceRecord.model_validate({"source_key": "src-1", "title": "Missing type", "url_or_path": "x"})
    with pytest.raises(ValidationError):
        ClaimRecord.model_validate({"claim_key": "claim-1"})
    with pytest.raises(ValidationError):
        ArtifactLineageRecord.model_validate({"artifact_path": "artifacts/report.md", "title": "Missing type"})
    with pytest.raises(ValidationError):
        VerificationRunRecord.model_validate({"run_id": "run-1"})
    with pytest.raises(ValidationError):
        EvidenceChunkRecord.model_validate(
            {
                "chunk_key": "chunk-1",
                "source_key": "src-1",
                "text": "chunk body",
                "ordinal": 0,
                "content_hash": "abc123",
            }
        )
    with pytest.raises(ValidationError):
        IntegrityEdgeRecord.model_validate({"from_id": "a", "to_id": "b", "relationship": "supports"})


def test_integrity_repo_traverses_claim_and_artifact_lineage(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    source = repo.upsert_source(
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
    chunk_key = repo.chunks_for_source(source.source_key)[0].chunk_key
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Queue delays increased after congestion worsened.",
            "artifact_path": "artifacts/report.md",
            "evidence_chunk_keys": [chunk_key],
            "source_keys": [source.source_key],
            "status": "supported",
            "evidence_kind": "direct",
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "verified",
            "sources": [f"research_plan/state/sources.json#{source.source_key}"],
            "claims": ["research_plan/state/claims.json#claim-001"],
        }
    )

    linked_chunks = repo.chunks_for_claim("claim-001")
    source_artifacts = repo.artifacts_for_source(source.source_key)
    claim_artifacts = repo.artifacts_for_claim("claim-001")

    assert [chunk.chunk_key for chunk in linked_chunks] == [chunk_key]
    assert [artifact.artifact_path for artifact in source_artifacts] == ["artifacts/report.md"]
    assert [artifact.artifact_path for artifact in claim_artifacts] == ["artifacts/report.md"]


def test_rebuild_all_preserves_stable_identifiers_for_graph_records(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    source = repo.upsert_source(
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
    repo.upsert_assumption(
        {
            "assumption_key": "baseline-window",
            "title": "Baseline window",
            "value": "2018-2020",
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Queue delays increased after congestion worsened.",
            "artifact_path": "artifacts/report.md",
            "evidence_chunk_keys": [chunk_key],
            "source_keys": [source.source_key],
            "status": "supported",
            "evidence_kind": "direct",
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": ".ontology/onto.duckdb",
            "artifact_type": "dataset",
            "title": "Hydrated Dataset",
            "promotion_state": "verified",
            "sources": [f"research_plan/state/sources.json#{source.source_key}"],
            "scripts": ["pipelines/hydrate.py"],
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "verified",
            "inputs": [".ontology/onto.duckdb"],
            "sources": [f"research_plan/state/sources.json#{source.source_key}"],
            "assumptions": ["research_plan/state/assumptions.json#baseline-window"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "scripts": ["topics/analyze.py"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
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

    assert rebuilt.sources[0].source_key == "briefing-note"
    assert rebuilt.evidence_chunks[0].chunk_key == chunk_key
    assert rebuilt.claims[0].claim_key == "claim-001"
    assert {item.artifact_path for item in rebuilt.artifact_lineage} == {".ontology/onto.duckdb", "artifacts/report.md"}
    assert rebuilt.verification_runs[0].run_id == "run-001"
    assert "source:briefing-note|supports|claim:claim-001" in {item.edge_key for item in rebuilt.integrity_edges}


def test_integrity_repo_persists_explicit_edge_records(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
            "provenance": {"text": "Congestion increased queue delays in the region."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Queue delays increased after congestion worsened.",
            "source_keys": ["briefing-note"],
            "evidence_chunk_keys": [chunk_key],
            "status": "supported",
            "evidence_kind": "direct",
        }
    )

    edge_file = root / "research_plan" / "state" / STATE_FILE_NAMES["integrity_edges"]
    edge_records = repo.load_integrity_edges()

    assert edge_file.exists()
    assert "source:briefing-note|supports|claim:claim-001" in {item.edge_key for item in edge_records}
    supports_edge = next(item for item in edge_records if item.edge_key == "source:briefing-note|supports|claim:claim-001")
    assert supports_edge.edge_class == "explicit"
    assert supports_edge.source_record_key == "briefing-note"


def test_integrity_repo_compile_truth_report_writes_outputs(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    (root / "research").mkdir(parents=True, exist_ok=True)
    (root / "research" / "paper.md").write_text(
        "This is a preliminary assessment. Median family income remains an ACS proxy.\n",
        encoding="utf-8",
    )

    source = repo.upsert_source(
        {
            "source_key": "bls-laus",
            "source_type": "dataset",
            "title": "BLS LAUS",
            "url_or_path": "topics/data/raw/bls.csv",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "Employment conditions improved after 2021."},
        }
    )
    chunk_key = repo.chunks_for_source(source.source_key)[0].chunk_key
    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "Employment improved after 2021.",
            "source_keys": [source.source_key],
            "evidence_chunk_keys": [chunk_key],
            "evidence_kind": "direct",
            "status": "supported",
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "partially_verified",
            "sources": [f"research_plan/state/sources.json#{source.source_key}"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            "inputs": ["topics/data/raw/bls.csv"],
            "scripts": ["topics/analyze.py"],
            "verification_commands": ["python topics/analyze.py"],
        }
    )
    repo.upsert_verification_run(
        {
            "run_id": "run-001",
            "scope": "artifact",
            "loop_type": "analysis_reproducibility",
            "status": "passed",
            "artifacts_checked": ["artifacts/report.md"],
            "artifact_paths": ["artifacts/report.md"],
            "claims_checked": ["claim-001"],
        }
    )

    report = repo.compile_truth_report(
        write_files=True,
        alignment_paths=["research/paper.md"],
    )

    assert report["summary"]["projectStatus"] == "partially_verified"
    assert report["claims"]["supported"][0]["claimKey"] == "claim-001"
    assert report["artifacts"]["partiallyVerified"][0]["artifactPath"] == "artifacts/report.md"
    assert repo.compiled_truth_report_path().exists()
    assert repo.artifact_support_matrix_path().exists()
    assert repo.paper_alignment_report_path().exists()
    assert repo.compiled_truth_summary_path().exists()


def test_integrity_repo_extracts_candidates_and_conflicts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    note = root / "topics" / "discovery.md"
    note.write_text(
        "# Discovery\n\n"
        "- Claim: Evidence suggests New Jersey municipalities saw stronger retail activity after the reform.\n"
        "- Finding: We find that observed Treasury candidates remain incomplete for the full period.\n"
        "- Source: https://example.com/data-source\n"
        "New Jersey Economic Development Authority coordinated with Rutgers University.\n",
        encoding="utf-8",
    )

    extracted = repo.extract_candidates_from_paths(["topics/discovery.md"])

    assert extracted["sourceCandidateCount"] >= 1
    assert extracted["claimCandidateCount"] >= 2
    assert extracted["entityCandidateCount"] >= 1
    assert any(item.url_or_path == "https://example.com/data-source" for item in repo.load_source_candidates())
    assert any("New Jersey" in item.name for item in repo.load_entity_candidates())

    repo.upsert_claim(
        {
            "claim_key": "claim-a",
            "claim_text": "Retail activity improved.",
            "status": "supported",
            "evidence_paths": ["topics/discovery.md"],
            "contradicts_claim_keys": ["claim-b"],
        }
    )
    repo.upsert_claim(
        {
            "claim_key": "claim-b",
            "claim_text": "Retail activity worsened.",
            "status": "supported",
            "evidence_paths": ["topics/discovery.md"],
            "contradicts_claim_keys": ["claim-a"],
        }
    )

    conflicts = repo.rebuild_conflicts()

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "claim_contradiction"
    assert "claim-a" in conflicts[0].left_ref
    compiled = repo.compile_truth_report(write_files=False)
    assert compiled["summary"]["conflictCount"] == 1
    assert compiled["summary"]["claimCandidateCount"] >= 2


def test_integrity_repo_can_promote_candidates_and_resolve_conflicts(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    note = root / "topics" / "discovery.md"
    note.write_text(
        "Claim: Evidence suggests retail activity improved after the reform.\n"
        "Source: https://example.com/source-a\n",
        encoding="utf-8",
    )
    repo.extract_candidates_from_paths(["topics/discovery.md"])

    source_candidate = repo.load_source_candidates()[0]
    claim_candidate = repo.load_claim_candidates()[0]

    source_result = repo.promote_source_candidate(source_candidate.candidate_key, source_type="report")
    claim_result = repo.promote_claim_candidate(claim_candidate.candidate_key, status="supported")

    assert source_result["status"] == "promoted"
    assert source_result["candidate"]["status"] == "promoted"
    assert source_result["source"]["quality_status"] == "candidate"
    assert claim_result["status"] == "promoted"
    assert claim_result["candidate"]["status"] == "promoted"
    assert claim_result["claim"]["status"] == "supported"
    assert claim_result["claim"]["source_keys"] == [source_result["source"]["source_key"]]

    repo.upsert_claim(
        {
            "claim_key": "claim-b",
            "claim_text": "Retail activity worsened after the reform.",
            "evidence_paths": ["topics/discovery.md"],
            "status": "supported",
            "evidence_kind": "direct",
            "contradicts_claim_keys": [claim_result["claim"]["claim_key"]],
        }
    )
    repo.upsert_claim(
        {
            "claim_key": claim_result["claim"]["claim_key"],
            "claim_text": claim_result["claim"]["claim_text"],
            "evidence_paths": claim_result["claim"]["evidence_paths"],
            "source_keys": claim_result["claim"]["source_keys"],
            "status": "supported",
            "evidence_kind": "direct",
            "contradicts_claim_keys": ["claim-b"],
        }
    )

    conflict = repo.rebuild_conflicts()[0]
    resolution = repo.resolve_conflict(
        conflict.conflict_key,
        status="resolved",
        favored_claim_key=claim_result["claim"]["claim_key"],
        explanation="Keep the candidate-promoted claim and supersede the contradictory draft.",
    )

    assert resolution["status"] == "resolved"
    resolved_conflict = repo.get_conflict(conflict.conflict_key)
    assert resolved_conflict is not None
    assert resolved_conflict.status == "resolved"
    assert repo.get_claim("claim-b").status == "superseded"
    assert repo.get_claim(claim_result["claim"]["claim_key"]).status == "supported"


def test_cli_integrity_candidate_promotion_and_conflict_resolution(capsys):
    class _Project:
        def apply_integrity_source_candidate_promotion(self, candidate_key, *, source_key=None, source_type=None):
            return {
                "candidate_key": candidate_key,
                "source_key": source_key,
                "source_type": source_type,
                "status": "promoted",
            }

        def apply_integrity_claim_candidate_promotion(self, candidate_key, *, claim_key=None, status=None, artifact_path=None):
            return {
                "candidate_key": candidate_key,
                "claim_key": claim_key,
                "status": status,
                "artifact_path": artifact_path,
            }

        def apply_integrity_conflict_resolution(self, conflict_key, *, status, favored_claim_key=None, explanation=None):
            return {
                "conflict_key": conflict_key,
                "status": status,
                "favored_claim_key": favored_claim_key,
                "explanation": explanation,
            }

    source_args = type(
        "Args",
        (),
        {
            "integrity_command": "promote-source-candidate",
            "candidate_key": "source:example",
            "source_key": "source-example",
            "source_type": "report",
        },
    )()
    rail_cli.cmd_integrity(_Project(), source_args)
    source_payload = json.loads(capsys.readouterr().out)
    assert source_payload["candidate_key"] == "source:example"
    assert source_payload["status"] == "promoted"

    claim_args = type(
        "Args",
        (),
        {
            "integrity_command": "promote-claim-candidate",
            "candidate_key": "claim:example",
            "claim_key": "claim-example",
            "status": "needs_evidence",
            "artifact_path": "artifacts/report.md",
        },
    )()
    rail_cli.cmd_integrity(_Project(), claim_args)
    claim_payload = json.loads(capsys.readouterr().out)
    assert claim_payload["candidate_key"] == "claim:example"
    assert claim_payload["artifact_path"] == "artifacts/report.md"

    conflict_args = type(
        "Args",
        (),
        {
            "integrity_command": "resolve-conflict",
            "conflict_key": "claim-conflict:claim-a::claim-b",
            "status": "resolved",
            "favored_claim_key": "claim-a",
            "explanation": "Prefer the better-supported claim.",
        },
    )()
    rail_cli.cmd_integrity(_Project(), conflict_args)
    conflict_payload = json.loads(capsys.readouterr().out)
    assert conflict_payload["conflict_key"] == "claim-conflict:claim-a::claim-b"
    assert conflict_payload["status"] == "resolved"


def test_sync_sources_from_configs_rejects_invalid_yaml(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    sources_dir = root / ".ontology" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "broken.yaml").write_text("name: Broken Source: [", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML in source config"):
        sync_sources_from_configs(root, sources_dir=".ontology/sources", source_keys=["broken"])


def test_sync_sources_from_configs_rejects_non_mapping_config(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    sources_dir = root / ".ontology" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "broken.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must decode to a mapping"):
        sync_sources_from_configs(root, sources_dir=".ontology/sources", source_keys=["broken"])


def test_sync_sources_from_configs_records_local_file_provenance(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    sources_dir = root / ".ontology" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "local-file.yaml").write_text(
        "name: Local File Source\n"
        "type: file\n"
        "path: data/raw/local.csv\n"
        "description: Uploaded local extract.\n",
        encoding="utf-8",
    )

    synced = sync_sources_from_configs(root, sources_dir=".ontology/sources", source_keys=["local-file"])

    assert len(synced) == 1
    assert synced[0].source_type == "file"
    assert synced[0].url_or_path == "data/raw/local.csv"
    assert synced[0].provenance["config_path"] == ".ontology/sources/local-file.yaml"
    assert synced[0].provenance["path"] == "data/raw/local.csv"


def test_sync_sources_from_configs_records_api_source_freshness_metadata(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    sources_dir = root / ".ontology" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "labor-api.yaml").write_text(
        "name: Labor API Source\n"
        "type: api\n"
        "url: https://api.example.com/labor\n"
        "provider: Bureau of Labor Statistics\n"
        "acquired_at: 2026-05-14T00:00:00Z\n"
        "retrieved_at: 2026-05-14T01:00:00Z\n"
        "access_method: http_get\n"
        "freshness_status: fresh\n"
        "fields:\n"
        "  - series_id\n"
        "  - value\n",
        encoding="utf-8",
    )

    synced = sync_sources_from_configs(root, sources_dir=".ontology/sources", source_keys=["labor-api"])

    assert len(synced) == 1
    assert synced[0].source_type == "api"
    assert synced[0].origin == "Bureau of Labor Statistics"
    assert synced[0].acquired_at == "2026-05-14T00:00:00Z"
    assert synced[0].retrieved_at == "2026-05-14T01:00:00Z"
    assert synced[0].access_method == "http_get"
    assert synced[0].freshness_status == "fresh"
    assert synced[0].provenance["config_path"] == ".ontology/sources/labor-api.yaml"
    assert synced[0].provenance["url"] == "https://api.example.com/labor"
    assert synced[0].provenance["fields"] == ["series_id", "value"]


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


def test_clear_artifact_stale_marks_artifact_partially_verified(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "stale_reasons": ["assumption_changed:years-2010-2024"],
            }
        ]
    )

    updated = repo.clear_artifact_stale(["artifacts/report.md"])

    assert len(updated) == 1
    assert updated[0].promotion_state == "partially_verified"
    assert updated[0].stale_reasons == []
    assert updated[0].stale_marked_at is None


def test_source_change_marks_dependent_claims_and_artifacts_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor-market/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
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
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
            }
        ]
    )

    updated, stale_claims, stale_artifacts = repo.update_source(
        "bls-laus",
        freshness_status="stale",
        quality_notes="Upstream publisher replaced the historical extract.",
    )

    assert updated.freshness_status == "stale"
    assert stale_claims[0].claim_key == "claim-001"
    assert stale_claims[0].status == "stale"
    assert stale_artifacts[0].artifact_path == "artifacts/report.md"
    assert stale_artifacts[0].promotion_state == "stale"
    assert "source_changed:bls-laus" in stale_artifacts[0].stale_reasons
    chunks = repo.chunks_for_source("bls-laus")
    assert chunks == []


def test_upsert_claim_downgrades_supported_status_without_explicit_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    claim = repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "This should not be marked supported yet.",
            "status": "supported",
            "evidence_kind": "semantic_suggestion",
        }
    )

    assert claim.status == "needs_evidence"


def test_write_claims_downgrades_supported_status_without_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "This should not be marked supported yet.",
                "status": "supported",
            }
        ]
    )

    stored = repo.get_claim("claim-001")
    assert stored is not None
    assert stored.status == "needs_evidence"


def test_upsert_claim_strips_unknown_references_and_downgrades_supported_status(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    claim = repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "This should not be marked supported yet.",
            "status": "supported",
            "evidence_kind": "direct",
            "evidence_paths": ["topics/missing-evidence.md"],
            "source_keys": ["missing-source"],
            "evidence_chunk_keys": ["missing-chunk"],
        }
    )

    assert claim.status == "needs_evidence"
    assert claim.evidence_paths == []
    assert claim.source_keys == []
    assert claim.evidence_chunk_keys == []


def test_write_claims_strips_unknown_references_before_persisting(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "This should not be marked supported yet.",
                "status": "supported",
                "evidence_kind": "direct",
                "evidence_paths": ["topics/missing-evidence.md"],
                "source_keys": ["missing-source"],
                "evidence_chunk_keys": ["missing-chunk"],
            }
        ]
    )

    stored = repo.get_claim("claim-001")
    assert stored is not None
    assert stored.status == "needs_evidence"
    assert stored.evidence_paths == []
    assert stored.source_keys == []
    assert stored.evidence_chunk_keys == []


def test_upsert_source_downgrades_validated_status_without_provenance(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    source = repo.upsert_source(
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
            "admissibility_status": "observed",
        }
    )

    assert source.quality_status == "candidate"


def test_write_sources_downgrades_validated_derived_status_without_lineage(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_sources(
        [
            {
                "source_key": "derived-series",
                "source_type": "dataset",
                "title": "Derived Series",
                "url_or_path": "https://example.com/derived.csv",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "admissibility_status": "derived",
                "provenance": {"text": "Computed from upstream series."},
            }
        ]
    )

    stored = repo.get_source("derived-series")
    assert stored is not None
    assert stored.quality_status == "candidate"


def test_write_artifact_lineage_downgrades_verified_without_verification_runs(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": ["topics/analysis/notes.md"],
                "scripts": ["topics/analysis/analyze.py"],
            }
        ]
    )

    stored = repo.load_artifact_lineage()[0]
    assert stored.promotion_state == "partially_verified"


def test_upsert_artifact_lineage_downgrades_partially_verified_without_workflow_support(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    stored = repo.upsert_artifact_lineage(
        {
            "artifact_path": "artifacts/report.md",
            "artifact_type": "report",
            "title": "Report",
            "promotion_state": "partially_verified",
        }
    )

    assert stored.promotion_state == "draft"


def test_write_artifact_lineage_drops_unknown_verification_runs_from_trusted_state(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": ["topics/analysis/notes.md"],
                "scripts": ["topics/analysis/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#missing-run"],
            }
        ]
    )

    stored = repo.load_artifact_lineage()[0]
    assert stored.promotion_state == "partially_verified"
    assert stored.verification_runs == []


def test_write_artifact_lineage_strips_unknown_references_before_persisting(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/missing-input.md"],
                "scripts": ["topics/missing-script.py"],
                "sources": ["research_plan/state/sources.json#missing-source"],
                "assumptions": ["research_plan/state/assumptions.json#missing-assumption"],
                "claims": ["research_plan/state/claims.json#missing-claim"],
                "verification_runs": ["research_plan/state/verification_runs.json#missing-run"],
            }
        ]
    )

    stored = repo.load_artifact_lineage()[0]
    assert stored.promotion_state == "draft"
    assert stored.inputs == []
    assert stored.scripts == []
    assert stored.sources == []
    assert stored.assumptions == []
    assert stored.claims == []
    assert stored.verification_runs == []


def test_write_source_candidates_downgrades_promoted_without_canonical_source(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_source_candidates(
        [
            {
                "candidate_key": "source-candidate-1",
                "title": "BLS Source",
                "url_or_path": "https://example.com/bls.csv",
                "status": "promoted",
            }
        ]
    )

    stored = repo.load_source_candidates()[0]
    assert stored.status == "candidate"


def test_write_claim_candidates_downgrades_promoted_without_canonical_claim(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)

    repo.write_claim_candidates(
        [
            {
                "candidate_key": "claim-candidate-1",
                "claim_text": "Employment rose after the reform.",
                "status": "promoted",
            }
        ]
    )

    stored = repo.load_claim_candidates()[0]
    assert stored.status == "candidate"


def test_source_refresh_clears_dependent_stale_state_when_revalidated(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
                "freshness_status": "stale",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor-market/notes.md"],
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
                "title": "Labor Market Report",
                "promotion_state": "stale",
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "verification_commands": ["scripts/run-verification.sh"],
                "stale_reasons": ["source_changed:bls-laus"],
            }
        ]
    )

    updated, refreshed_claims, refreshed_artifacts = repo.update_source(
        "bls-laus",
        freshness_status="fresh",
        quality_notes="Source revalidated with no material change.",
    )

    assert updated.freshness_status == "fresh"
    assert refreshed_claims[0].status == "supported"
    assert refreshed_artifacts[0].promotion_state == "partially_verified"
    assert refreshed_artifacts[0].stale_reasons == []


def test_source_refresh_only_clears_related_stale_reasons(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "source-a",
                "source_type": "dataset",
                "title": "Source A",
                "url_or_path": "https://example.com/a.csv",
                "origin": "A",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "stale",
            },
            {
                "source_key": "source-b",
                "source_type": "dataset",
                "title": "Source B",
                "url_or_path": "https://example.com/b.csv",
                "origin": "B",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "stale",
            },
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-a",
                "claim_text": "Claim A",
                "artifact_path": "artifacts/report-a.md",
                "evidence_paths": ["topics/a.md"],
                "source_keys": ["source-a"],
                "status": "stale",
                "evidence_kind": "direct",
            },
            {
                "claim_key": "claim-b",
                "claim_text": "Claim B",
                "artifact_path": "artifacts/report-b.md",
                "evidence_paths": ["topics/b.md"],
                "source_keys": ["source-b"],
                "status": "stale",
                "evidence_kind": "direct",
            },
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report-a.md",
                "artifact_type": "report",
                "title": "Report A",
                "promotion_state": "stale",
                "sources": ["research_plan/state/sources.json#source-a"],
                "claims": ["research_plan/state/claims.json#claim-a"],
                "stale_reasons": ["source_changed:source-a", "assumption_changed:window"],
            },
            {
                "artifact_path": "artifacts/report-b.md",
                "artifact_type": "report",
                "title": "Report B",
                "promotion_state": "stale",
                "sources": ["research_plan/state/sources.json#source-b"],
                "claims": ["research_plan/state/claims.json#claim-b"],
                "stale_reasons": ["source_changed:source-b"],
            },
        ]
    )

    updated, refreshed_claims, refreshed_artifacts = repo.update_source("source-a", freshness_status="fresh")

    claims = {item.claim_key: item for item in repo.load_claims()}
    artifacts = {item.artifact_path: item for item in repo.load_artifact_lineage()}

    assert updated.freshness_status == "fresh"
    assert {item.claim_key for item in refreshed_claims} == {"claim-a"}
    assert {item.artifact_path for item in refreshed_artifacts} == {"artifacts/report-a.md"}
    assert claims["claim-a"].status == "supported"
    assert claims["claim-b"].status == "stale"
    assert artifacts["artifacts/report-a.md"].promotion_state == "stale"
    assert artifacts["artifacts/report-a.md"].stale_reasons == ["assumption_changed:window"]
    assert artifacts["artifacts/report-b.md"].promotion_state == "stale"
    assert artifacts["artifacts/report-b.md"].stale_reasons == ["source_changed:source-b"]


def test_claim_support_updates_move_artifact_into_and_out_of_needs_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "claims": ["research_plan/state/claims.json#claim-001"],
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

    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "An unsupported claim.",
            "artifact_path": "artifacts/report.md",
            "status": "needs_evidence",
        }
    )

    unsupported = repo.load_artifact_lineage()[0]
    assert unsupported.promotion_state == "needs_evidence"
    assert "claim_needs_evidence:claim-001" in unsupported.stale_reasons

    repo.upsert_claim(
        {
            "claim_key": "claim-001",
            "claim_text": "A supported claim.",
            "artifact_path": "artifacts/report.md",
            "status": "supported",
            "evidence_kind": "direct",
            "source_keys": ["bls-laus"],
        }
    )

    restored = repo.load_artifact_lineage()[0]
    assert restored.promotion_state == "partially_verified"
    assert "claim_needs_evidence:claim-001" not in restored.stale_reasons


def test_source_text_is_chunked_and_source_updates_mark_chunks_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    source = repo.upsert_source(
        {
            "source_key": "policy-memo",
            "source_type": "document",
            "title": "Policy Memo",
            "url_or_path": "notes/policy-memo.md",
            "origin": "State Agency",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "Paragraph one about grid congestion.\n\nParagraph two about capacity expansion.\n\nParagraph three about reliability and cost."
            },
        }
    )

    chunks = repo.chunks_for_source("policy-memo")

    assert source.source_key == "policy-memo"
    assert len(chunks) >= 1
    assert all(chunk.source_key == "policy-memo" for chunk in chunks)
    assert all(chunk.status == "active" for chunk in chunks)

    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Capacity expansion could lower congestion costs.",
                "source_keys": ["policy-memo"],
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
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#policy-memo"],
            }
        ]
    )

    repo.update_source("policy-memo", freshness_status="stale")

    stale_chunks = repo.chunks_for_source("policy-memo")
    assert all(chunk.status == "stale" for chunk in stale_chunks)


def test_rebuild_chunks_for_source_is_deterministic_for_same_text(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "notes/briefing-note.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": (
                    "Paragraph one about labor market shifts.\n\n"
                    "Paragraph two about commuting costs and congestion.\n\n"
                    "Paragraph three about grid reliability."
                )
            },
        }
    )

    first_pass = repo.rebuild_chunks_for_source("briefing-note")
    second_pass = repo.rebuild_chunks_for_source("briefing-note")

    assert [chunk.chunk_key for chunk in first_pass] == [chunk.chunk_key for chunk in second_pass]
    assert [chunk.ordinal for chunk in first_pass] == [chunk.ordinal for chunk in second_pass]
    assert [chunk.text for chunk in first_pass] == [chunk.text for chunk in second_pass]
    assert [chunk.content_hash for chunk in first_pass] == [chunk.content_hash for chunk in second_pass]
    assert [chunk.embedding for chunk in first_pass] == [chunk.embedding for chunk in second_pass]
    assert [chunk.metadata for chunk in first_pass] == [chunk.metadata for chunk in second_pass]


def test_vector_only_retrieval_finds_semantically_relevant_chunk(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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

    result = repo.hybrid_retrieve(
        "delays from transmission congestion",
        limit=5,
        expand_explicit=False,
    )

    chunk_results = [item for item in result["results"] if item["recordType"] == "chunk"]
    assert chunk_results
    assert chunk_results[0]["recordKey"].startswith("queue-brief#chunk-")
    assert chunk_results[0]["resultType"] == "semantic_suggestion"
    assert result["filters"]["expandExplicit"] is False


def test_script_change_marks_dependent_artifacts_stale(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "topics/analysis.csv",
                "artifact_type": "dataset",
                "title": "Analysis Dataset",
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

    stale = repo.mark_artifacts_stale_for_script("topics/scripts/transform.py")

    assert len(stale) == 2
    assert {item.artifact_path for item in stale} == {"topics/analysis.csv", "artifacts/report.md"}
    assert all(item.promotion_state == "stale" for item in stale)
    assert all("script_changed:topics/scripts/transform.py" in item.stale_reasons for item in stale)


def test_blocked_source_marks_dependent_claims_conflicted_and_artifacts_blocked(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "state-brief",
                "source_type": "document",
                "title": "State Brief",
                "url_or_path": "https://example.com/brief.pdf",
                "quality_status": "validated",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "A policy reduced costs.",
                "artifact_path": "artifacts/report.md",
                "source_keys": ["state-brief"],
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
                "sources": ["research_plan/state/sources.json#state-brief"],
            }
        ]
    )

    updated, conflicted_claims, blocked_artifacts = repo.update_source(
        "state-brief",
        quality_status="blocked",
        quality_notes="Conflicts with the primary audited source.",
    )

    assert updated.quality_status == "blocked"
    assert conflicted_claims[0].status == "conflicted"
    assert blocked_artifacts[0].promotion_state == "blocked"
    assert "source_blocked:state-brief" in blocked_artifacts[0].stale_reasons


def test_local_project_can_preview_and_apply_integrity_rerun_plan(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Ontology DuckDB",
                "promotion_state": "stale",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "inputs": [".ontology/onto.duckdb"],
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            }
        ]
    )

    project = rail.local(str(root))
    preview = project.integrity_rerun_plan("study-period")
    applied = project.apply_integrity_rerun_plan("study-period")

    assert preview["assumption"]["assumption_key"] == "study-period"
    assert preview["affectedPaths"] == [".ontology/onto.duckdb", "artifacts/report.md"]
    assert preview["mode"] == "local"
    assert applied["createdTasks"] == []
    assert applied["rerunPlan"]["stalePaths"] == [".ontology/onto.duckdb", "artifacts/report.md"]


def test_local_project_exposes_integrity_detail_views(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "bls-laus",
            "source_type": "dataset",
            "title": "BLS LAUS",
            "url_or_path": "https://example.com/bls.csv",
            "freshness_status": "stale",
            "provenance": {"text": "BLS extract about unemployment."},
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
                "status": "stale",
                "open_questions": ["Does the pattern hold for peer regions?"],
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
                "verification_commands": ["scripts/run-verification.sh"],
                "stale_reasons": ["source_changed:bls-laus"],
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

    project = rail.local(str(root))
    source_detail = project.integrity_source_detail("bls-laus")
    claim_detail = project.integrity_claim_detail("claim-001")
    stale_graph = project.integrity_stale_graph()
    verification = project.integrity_verification_runs()
    benchmark = project.integrity_benchmark(retrieval_limit=5)
    lineage = project.integrity_artifact_lineage()

    assert source_detail["source"]["source_key"] == "bls-laus"
    assert source_detail["sourceState"]["isStale"] is True
    assert source_detail["trustSummary"]["recommendedNextAction"] == "Refresh this source and rerun dependent analyses."
    assert source_detail["dependentClaims"][0]["claim_key"] == "claim-001"
    assert claim_detail["claim"]["open_questions"] == ["Does the pattern hold for peer regions?"]
    assert claim_detail["claimState"]["openQuestionCount"] == 1
    assert claim_detail["trustSummary"]["entityType"] == "claim"
    assert claim_detail["chunks"][0]["chunk_key"] == chunk_key
    assert claim_detail["verificationRuns"][0]["run_id"] == "run-001"
    assert stale_graph["summary"]["staleArtifactCount"] == 1
    assert verification["summary"]["count"] == 1
    assert verification["summary"]["loopTypeCounts"]["analysis_reproducibility"] == 1
    assert benchmark["summary"]["caseCount"] == 7
    assert benchmark["summary"]["passedCases"] == 7
    assert benchmark["summary"]["hybridOutperformsVectorOnly"] is True
    assert benchmark["mode"] == "local"
    report_entry = next(item for item in lineage if item["artifact_path"] == "artifacts/report.md")
    assert report_entry["verification_commands"] == ["scripts/run-verification.sh"]


def test_local_project_integrity_status_matches_richer_summary_shape(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
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
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "stale_reasons": [],
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

    project = rail.local(str(root))
    status = project.integrity_status()

    assert status["mode"] == "local"
    assert status["summary"]["sourceCount"] == 1
    assert status["summary"]["promotionStateCounts"]["verified"] == 1
    assert status["agentWorkflow"]["health"]["status"] == "ready"


def test_local_project_exposes_artifact_detail(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
                "promotion_state": "verified",
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

    project = rail.local(str(root))
    detail = project.integrity_artifact_detail("artifacts/report.md")

    assert detail["mode"] == "local"
    assert detail["artifact"]["artifact_path"] == "artifacts/report.md"
    assert detail["artifact"]["verification_commands"] == ["scripts/run-verification.sh"]
    assert detail["trustState"]["currentState"] == "verified"
    assert detail["trustState"]["isTrusted"] is True
    assert detail["trustSummary"]["recommendedNextAction"] == "Trust state is current."
    assert detail["claims"][0]["claim_key"] == "claim-001"


def test_local_project_exposes_dependency_graph(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    project = rail.local(str(root))
    graph = project.integrity_dependency_graph()

    relationships = {(item["from"], item["to"], item["relationship"]) for item in graph["edges"]}
    assert graph["mode"] == "local"
    assert ("source:briefing-note", f"chunk:{chunk_key}", "chunked_as") in relationships
    assert ("source:briefing-note", "claim:claim-001", "supports") in relationships
    assert ("claim:claim-001", "artifact:artifacts/report.md", "supports") in relationships


def test_local_project_dependency_graph_exposes_dataset_nodes(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
            },
        ]
    )

    project = rail.local(str(root))
    graph = project.integrity_dependency_graph()

    node_types = {item["id"]: item["type"] for item in graph["nodes"]}
    relationships = {(item["from"], item["to"], item["relationship"]) for item in graph["edges"]}
    assert node_types["dataset:.ontology/onto.duckdb"] == "dataset"
    assert ("artifact:artifacts/report.md", "dataset:.ontology/onto.duckdb", "depends_on") in relationships


def test_local_project_exposes_hybrid_integrity_retrieval(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Labor market unemployment fell after 2021.",
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
                "title": "Labor Report",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    project = rail.local(str(root))
    retrieval = project.integrity_retrieve("labor unemployment report", limit=5)

    assert retrieval["mode"] == "local"
    assert retrieval["summary"]["explicitEvidenceCount"] >= 1
    assert any(
        item["recordType"] == "claim" and item["resultType"] == "explicit_evidence"
        for item in retrieval["results"]
    )


def test_local_project_hybrid_retrieval_returns_chunk_suggestions_with_source_metadata(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
                "text": "This briefing discusses interconnection queues, grid congestion, and regional transmission costs in detail."
            },
        }
    )

    project = rail.local(str(root))
    retrieval = project.integrity_retrieve("regional transmission congestion", limit=5)

    chunk_results = [item for item in retrieval["results"] if item["recordType"] == "chunk"]
    assert chunk_results
    assert chunk_results[0]["resultType"] == "semantic_suggestion"
    assert chunk_results[0]["sourceMetadata"]["source_title"] == "Briefing Note"
    stored_chunk = repo.chunks_for_source("briefing-note")[0]
    assert stored_chunk.embedding_model == "token_hash_v1"
    assert len(stored_chunk.embedding) == 256
    assert any(value > 0 for value in stored_chunk.embedding)


def test_local_project_hybrid_retrieval_supports_date_filters(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "older-source",
                "source_type": "dataset",
                "title": "Older Source",
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
                "title": "Recent Source",
                "url_or_path": "https://example.com/recent.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
        ]
    )

    project = rail.local(str(root))
    retrieval = project.integrity_retrieve(
        "source",
        limit=10,
        date_from="2026-01-01T00:00:00Z",
        date_to="2026-12-31T23:59:59Z",
    )

    result_keys = {item["recordKey"] for item in retrieval["results"] if item["recordType"] == "source"}
    assert "recent-source" in result_keys
    assert "older-source" not in result_keys
    assert retrieval["filters"]["dateFrom"] == "2026-01-01T00:00:00Z"


def test_local_project_can_apply_reproducibility_rerun(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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

    project = rail.local(str(root))
    result = project.apply_integrity_reproducibility_rerun(
        {"artifacts/report.md": "stable report\n"},
        run_id="rerun-001",
    )

    assert result["mode"] == "local"
    assert result["status"] == "passed"
    updated = ResearchIntegrityRepo(root).load_artifact_lineage()[0]
    assert updated.promotion_state == "partially_verified"


def test_cli_integrity_reproduce_uses_outputs_json(tmp_path, capsys):
    outputs_path = tmp_path / "outputs.json"
    outputs_path.write_text(json.dumps({"artifacts/report.md": "stable report\n"}), encoding="utf-8")

    class _Project:
        def apply_integrity_reproducibility_rerun(self, outputs, *, run_id="rerun-verification", scope="health"):
            return {
                "status": "passed",
                "outputs": outputs,
                "run_id": run_id,
                "scope": scope,
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "reproduce",
            "outputs_json": str(outputs_path),
            "run_id": "rerun-001",
            "scope": "health",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "passed"
    assert payload["outputs"]["artifacts/report.md"] == "stable report\n"
    assert payload["run_id"] == "rerun-001"


def test_cli_integrity_freshness_evaluate_uses_as_of(capsys):
    class _Project:
        def apply_integrity_freshness_evaluation(self, *, as_of=None):
            return {
                "status": "evaluated",
                "as_of": as_of,
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "freshness-evaluate",
            "as_of": "2026-05-14T00:00:00Z",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "evaluated"
    assert payload["as_of"] == "2026-05-14T00:00:00Z"


def test_cli_integrity_artifact_uses_artifact_path(capsys):
    class _Project:
        def integrity_artifact_detail(self, artifact_path):
            return {
                "artifact": {"artifact_path": artifact_path},
                "trustState": {
                    "currentState": "verified",
                    "isTrusted": True,
                    "isBlocked": False,
                    "isStale": False,
                },
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "artifact",
            "artifact_path": "artifacts/report.md",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["artifact"]["artifact_path"] == "artifacts/report.md"
    assert payload["trustState"]["currentState"] == "verified"
    assert payload["trustState"]["isTrusted"] is True
    assert payload["trustState"]["isBlocked"] is False
    assert payload["trustState"]["isStale"] is False


def test_cli_integrity_benchmark_prints_combined_report(capsys):
    class _Project:
        def integrity_benchmark(self, *, retrieval_limit=10):
            return {
                "summary": {
                    "caseCount": 7,
                    "passedCases": 7,
                    "failedCases": 0,
                    "hybridOutperformsVectorOnly": True,
                },
                "metadata": {"claimKeys": ["claim-supported", "claim-semantic"]},
                "retrieval": {"summary": {"caseCount": 2}},
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "benchmark",
            "limit": 5,
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["caseCount"] == 7
    assert payload["summary"]["passedCases"] == 7
    assert payload["summary"]["hybridOutperformsVectorOnly"] is True


def test_cli_integrity_compile_uses_alignment_paths(capsys):
    class _Project:
        def integrity_compile(self, *, write_files=True, alignment_paths=None):
            return {
                "summary": {"projectStatus": "partially_verified"},
                "paperAlignment": {"checkedPaths": alignment_paths or []},
                "writeFiles": write_files,
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "compile",
            "no_write": False,
            "alignment_path": ["research/paper.md", "research/summary.md"],
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["projectStatus"] == "partially_verified"
    assert payload["paperAlignment"]["checkedPaths"] == ["research/paper.md", "research/summary.md"]
    assert payload["writeFiles"] is True


def test_cli_integrity_source_uses_source_key(capsys):
    class _Project:
        def integrity_source_detail(self, source_key):
            return {
                "source": {"source_key": source_key},
                "sourceState": {"isFresh": True},
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "source",
            "source_key": "briefing-note",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["source"]["source_key"] == "briefing-note"
    assert payload["sourceState"]["isFresh"] is True


def test_cli_integrity_claim_uses_claim_key(capsys):
    class _Project:
        def integrity_claim_detail(self, claim_key):
            return {
                "claim": {"claim_key": claim_key},
                "claimState": {"evidenceComplete": True},
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "claim",
            "claim_key": "claim-001",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["claim"]["claim_key"] == "claim-001"
    assert payload["claimState"]["evidenceComplete"] is True


def test_cli_integrity_verification_runs_prints_summary(capsys):
    class _Project:
        def integrity_verification_runs(self):
            return {
                "summary": {"loopTypeCounts": {"analysis_reproducibility": 1}},
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "verification-runs",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["loopTypeCounts"]["analysis_reproducibility"] == 1


def test_cli_integrity_stale_graph_prints_summary(capsys):
    class _Project:
        def integrity_stale_graph(self):
            return {
                "summary": {"staleArtifactCount": 1},
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "stale-graph",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["staleArtifactCount"] == 1


def test_cli_integrity_graph_prints_dependency_graph(capsys):
    class _Project:
        def integrity_dependency_graph(self):
            return {
                "nodes": [{"id": "source:briefing-note"}],
                "edges": [{"from": "source:briefing-note", "to": "claim:claim-001", "relationship": "supports"}],
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "graph",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["edges"][0]["relationship"] == "supports"


def test_cli_integrity_promote_uses_artifact_path_and_target_state(capsys):
    class _Project:
        def apply_integrity_artifact_promotion(self, artifact_path, *, target_state):
            return {
                "status": "promoted",
                "artifact_path": artifact_path,
                "target_state": target_state,
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "promote",
            "artifact_path": "artifacts/report.md",
            "target_state": "verified",
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["status"] == "promoted"
    assert payload["artifact_path"] == "artifacts/report.md"
    assert payload["target_state"] == "verified"


def test_cli_integrity_retrieve_uses_date_filters(capsys):
    class _Project:
        def integrity_retrieve(self, query, **kwargs):
            return {
                "query": query,
                "filters": kwargs,
            }

    args = type(
        "Args",
        (),
        {
            "integrity_command": "retrieve",
            "query_text": "labor source",
            "limit": 5,
            "artifact_types": None,
            "claim_statuses": None,
            "source_freshness": None,
            "date_from": "2026-01-01T00:00:00Z",
            "date_to": "2026-12-31T23:59:59Z",
            "include_stale": False,
            "include_blocked": False,
        },
    )()

    rail_cli.cmd_integrity(_Project(), args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["filters"]["date_from"] == "2026-01-01T00:00:00Z"
    assert payload["filters"]["date_to"] == "2026-12-31T23:59:59Z"


def test_local_project_can_apply_freshness_evaluation(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "api-source",
                "source_type": "api",
                "title": "API Source",
                "url_or_path": "https://example.com/data.json",
                "origin": "Example",
                "acquired_at": "2026-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            }
        ]
    )

    project = rail.local(str(root))
    result = project.apply_integrity_freshness_evaluation(as_of="2026-05-14T00:00:00Z")

    assert result["mode"] == "local"
    assert result["summary"]["stale"] == 1
    updated = ResearchIntegrityRepo(root).load_sources()[0]
    assert updated.freshness_status == "stale"


def test_local_project_can_apply_artifact_promotion(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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
    from rail.local import LocalEngine

    engine = LocalEngine(str(root))
    engine.artifact_duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    engine.artifact_duckdb_path.write_bytes(b"")
    engine._write_hydration_meta("default", "full")
    engine._record_hydration_lineage("default")

    project = rail.local(str(root))
    result = project.apply_integrity_artifact_promotion("artifacts/report.md", target_state="verified")

    assert result["mode"] == "local"
    assert result["status"] == "promoted"
    updated = ResearchIntegrityRepo(root).load_artifact_lineage()[0]
    assert updated.promotion_state == "verified"


def test_local_project_blocks_trusted_artifact_promotion_without_hydration(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
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

    project = rail.local(str(root))
    with pytest.raises(ValueError, match="Trusted artifact promotion requires local hydrated ontology state"):
        project.apply_integrity_artifact_promotion("artifacts/report.md", target_state="verified")


def test_local_project_can_promote_source_and_claim_candidates(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    note = root / "topics" / "discovery.md"
    note.write_text(
        "Claim: Evidence suggests employment rose after the reform.\n"
        "Source: https://example.com/employment-source\n",
        encoding="utf-8",
    )
    repo.extract_candidates_from_paths(["topics/discovery.md"])
    source_candidate_key = repo.load_source_candidates()[0].candidate_key
    claim_candidate_key = repo.load_claim_candidates()[0].candidate_key

    project = rail.local(str(root))
    source_result = project.apply_integrity_source_candidate_promotion(source_candidate_key, source_type="dataset")
    claim_result = project.apply_integrity_claim_candidate_promotion(claim_candidate_key, status="supported")

    assert source_result["mode"] == "local"
    assert source_result["source"]["source_type"] == "dataset"
    assert source_result["source"]["quality_status"] == "candidate"
    assert claim_result["mode"] == "local"
    assert claim_result["claim"]["status"] == "supported"


def test_promote_source_candidate_rejects_validated_without_explicit_provenance(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    note = root / "topics" / "discovery.md"
    note.write_text(
        "Source: https://example.com/employment-source\n",
        encoding="utf-8",
    )
    repo.extract_candidates_from_paths(["topics/discovery.md"])
    source_candidate_key = repo.load_source_candidates()[0].candidate_key

    with pytest.raises(ValueError, match="Validated source promotion requires explicit provenance metadata."):
        repo.promote_source_candidate(source_candidate_key, source_type="dataset", quality_status="validated")


def test_promote_claim_candidate_rejects_supported_status_without_explicit_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    claim_candidate = repo.upsert_claim_candidate(
        {
            "candidate_key": "claim-candidate-unsupported",
            "claim_text": "Employment rose after the reform.",
            "snippet": "Semantic retrieval lead without explicit evidence.",
        }
    )

    with pytest.raises(ValueError, match="Supported claims require explicit recorded evidence before claim-candidate promotion."):
        repo.promote_claim_candidate(claim_candidate.candidate_key, status="supported")


def test_local_project_blocks_claim_candidate_supported_promotion_without_explicit_evidence(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    claim_candidate = repo.upsert_claim_candidate(
        {
            "candidate_key": "claim-candidate-unsupported",
            "claim_text": "Employment rose after the reform.",
            "snippet": "Semantic retrieval lead without explicit evidence.",
        }
    )

    project = rail.local(str(root))
    with pytest.raises(ValueError, match="Supported claims require explicit recorded evidence before claim-candidate promotion."):
        project.apply_integrity_claim_candidate_promotion(claim_candidate.candidate_key, status="supported")


def test_local_claim_detail_exposes_contradictory_claims(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Project", slug="integrity-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_claims(
        [
            {
                "claim_key": "claim-a",
                "claim_text": "Costs fell.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/a.md"],
                "status": "supported",
                "evidence_kind": "direct",
                "contradicts_claim_keys": ["claim-b"],
            },
            {
                "claim_key": "claim-b",
                "claim_text": "Costs rose.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/b.md"],
                "status": "supported",
                "evidence_kind": "direct",
                "contradicts_claim_keys": ["claim-a"],
            },
        ]
    )
    repo.reconcile_claim_conflicts()

    project = rail.local(str(root))
    detail = project.integrity_claim_detail("claim-a")

    assert detail["claim"]["status"] == "conflicted"
    assert detail["contradictoryClaims"][0]["claim_key"] == "claim-b"


def test_project_exposes_freshness_evaluation_on_backend():
    class _Backend:
        def apply_integrity_freshness_evaluation(self, slug, *, as_of=None):
            return {
                "slug": slug,
                "as_of": as_of,
                "status": "evaluated",
            }

    project = rail.Project("integrity-project", _Backend())
    result = project.apply_integrity_freshness_evaluation(as_of="2026-05-14T00:00:00Z")

    assert result["slug"] == "integrity-project"
    assert result["as_of"] == "2026-05-14T00:00:00Z"


def test_project_exposes_artifact_detail_on_backend():
    class _Backend:
        def get_integrity_artifact_detail(self, slug, artifact_path):
            return {
                "slug": slug,
                "artifact": {"artifact_path": artifact_path},
                "trustState": {"currentState": "verified"},
            }

    project = rail.Project("integrity-project", _Backend())
    result = project.integrity_artifact_detail("artifacts/report.md")

    assert result["slug"] == "integrity-project"
    assert result["artifact"]["artifact_path"] == "artifacts/report.md"


def test_project_exposes_dependency_graph_on_backend():
    class _Backend:
        def get_integrity_dependency_graph(self, slug):
            return {
                "slug": slug,
                "edges": [{"from": "source:briefing-note", "to": "claim:claim-001", "relationship": "supports"}],
            }

    project = rail.Project("integrity-project", _Backend())
    result = project.integrity_dependency_graph()

    assert result["slug"] == "integrity-project"
    assert result["edges"][0]["relationship"] == "supports"


def test_project_exposes_artifact_promotion_on_backend():
    class _Backend:
        def apply_integrity_artifact_promotion(self, slug, artifact_path, *, target_state):
            return {
                "slug": slug,
                "artifact_path": artifact_path,
                "target_state": target_state,
                "status": "promoted",
            }

    project = rail.Project("integrity-project", _Backend())
    result = project.apply_integrity_artifact_promotion("artifacts/report.md", target_state="verified")

    assert result["slug"] == "integrity-project"
    assert result["artifact_path"] == "artifacts/report.md"
    assert result["target_state"] == "verified"


def test_project_exposes_candidate_promotion_and_conflict_resolution_on_backend():
    class _Backend:
        def apply_integrity_source_candidate_promotion(self, slug, candidate_key, *, source_key=None, source_type=None):
            return {
                "slug": slug,
                "candidate_key": candidate_key,
                "source_key": source_key,
                "source_type": source_type,
            }

        def apply_integrity_claim_candidate_promotion(self, slug, candidate_key, *, claim_key=None, status=None, artifact_path=None):
            return {
                "slug": slug,
                "candidate_key": candidate_key,
                "claim_key": claim_key,
                "status": status,
                "artifact_path": artifact_path,
            }

        def apply_integrity_conflict_resolution(self, slug, conflict_key, *, status, favored_claim_key=None, explanation=None):
            return {
                "slug": slug,
                "conflict_key": conflict_key,
                "status": status,
                "favored_claim_key": favored_claim_key,
                "explanation": explanation,
            }

    project = rail.Project("integrity-project", _Backend())
    source_result = project.apply_integrity_source_candidate_promotion("source:demo", source_type="report")
    claim_result = project.apply_integrity_claim_candidate_promotion(
        "claim:demo",
        claim_key="claim-demo",
        status="needs_evidence",
        artifact_path="artifacts/report.md",
    )
    conflict_result = project.apply_integrity_conflict_resolution(
        "claim-conflict:claim-a::claim-b",
        status="resolved",
        favored_claim_key="claim-a",
        explanation="Prefer the stronger evidence chain.",
    )

    assert source_result["slug"] == "integrity-project"
    assert source_result["source_type"] == "report"
    assert claim_result["claim_key"] == "claim-demo"
    assert claim_result["artifact_path"] == "artifacts/report.md"
    assert conflict_result["conflict_key"] == "claim-conflict:claim-a::claim-b"
    assert conflict_result["favored_claim_key"] == "claim-a"
