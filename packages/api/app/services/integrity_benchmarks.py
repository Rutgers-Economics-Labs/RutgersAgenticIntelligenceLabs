from __future__ import annotations

from pathlib import Path
from typing import Any

from rail.integrity import ResearchIntegrityRepo
from rail.manifest import load_manifest


def seed_default_integrity_benchmark_corpus(project_root: str | Path) -> dict[str, Any]:
    """
    Seed a small repo-backed benchmark corpus with known source/claim/artifact
    relationships and return ground-truth benchmark cases for the integrity
    evaluation helpers.
    """
    root = Path(project_root)
    repo = ResearchIntegrityRepo(root)

    # Materialize the files this corpus references on disk so the integrity
    # normalizers don't strip the lineage/verification refs that point at them.
    # The artifact-lineage and verification-run normalizers (commit 7ad66b6)
    # drop refs to paths that don't exist; without this scaffolding the corpus
    # produces empty verification-run lookups and the benchmark's "passedCases"
    # count drops from 2 to 1.
    _scaffold_files = {
        "topics/queue-brief.md": "# Interconnection queue brief\nQueue delays caused by transmission congestion.\n",
        "topics/data.csv": "id,value\n1,100\n",
        "topics/analyze.py": "# analysis script placeholder\n",
        "scripts/run-verification.sh": "#!/usr/bin/env bash\nexit 0\n",
        "artifacts/output.md": "# system output\n",
        "artifacts/semantic-output.md": "# semantic output\n",
        "artifacts/stale-report.md": "# stale report\n",
    }
    for rel, content in _scaffold_files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    queue_source = repo.upsert_source(
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
    stale_source = repo.upsert_source(
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
            "provenance": {"text": "Outdated but once valid benchmark source."},
        }
    )
    queue_chunk_key = repo.chunks_for_source(queue_source.source_key)[0].chunk_key

    repo.write_claims(
        [
            {
                "claim_key": "claim-supported",
                "claim_text": "Backlog pressure rises when grid expansion stalls.",
                "status": "supported",
                "source_keys": [queue_source.source_key],
                "evidence_chunk_keys": [queue_chunk_key],
                "evidence_kind": "direct",
            },
            {
                "claim_key": "claim-semantic",
                "claim_text": "Nearby regions may show a similar pattern.",
                "status": "supported",
                "source_keys": [queue_source.source_key],
                "evidence_kind": "semantic_suggestion",
            },
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "scope": "artifact",
                "loop_type": "analysis_reproducibility",
                "status": "passed",
                "artifact_paths": ["artifacts/stale-report.md"],
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
                "claims": ["research_plan/state/claims.json#claim-supported"],
                "sources": ["research_plan/state/sources.json#queue-brief"],
            },
            {
                "artifact_path": "artifacts/semantic-output.md",
                "artifact_type": "report",
                "title": "Semantic Output",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "claims": ["research_plan/state/claims.json#claim-semantic"],
                "sources": ["research_plan/state/sources.json#queue-brief"],
            },
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
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
                "sources": [f"research_plan/state/sources.json#{stale_source.source_key}"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "verification_runs": [],
                "stale_reasons": ["source_changed:sample"],
            },
        ]
    )

    report_path = root / "artifacts" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("stable report\n", encoding="utf-8")

    return {
        "metadata": {
            "sourceKeys": [queue_source.source_key, stale_source.source_key],
            "claimKeys": ["claim-supported", "claim-semantic"],
            "artifactPaths": [
                "artifacts/output.md",
                "artifacts/semantic-output.md",
                "artifacts/missing-lineage.md",
                "artifacts/stale-report.md",
                "artifacts/report.md",
            ],
        },
        "retrievalCases": [
            {
                "question": "Which source directly discusses interconnection queue delays?",
                "query": "source about interconnection queue delays",
                "expectedRecordKeys": ["queue-brief"],
                "expectedRecordTypes": ["source"],
            },
            {
                "question": "Which explicit claim and downstream artifact support queue delays from transmission congestion?",
                "query": "interconnection delays from transmission congestion",
                "expectedRecordKeys": ["claim-supported", "artifacts/output.md"],
                "expectedRecordTypes": ["claim", "artifact"],
            }
        ],
        "claimVerificationCases": [
            {
                "question": "Does the directly evidenced congestion claim pass evidence completeness?",
                "claimKey": "claim-supported",
                "expectedStatus": "supported",
                "expectedEvidenceComplete": True,
            },
            {
                # semantic_suggestion claims seeded as "supported" without an
                # explicit chunk are anti-fabrication-downgraded to
                # needs_evidence by normalize_claim_record_for_write
                # (commit 7ad66b6). The benchmark target reflects that.
                "question": "Does the semantic-only regional similarity claim remain incomplete?",
                "claimKey": "claim-semantic",
                "expectedStatus": "needs_evidence",
                "expectedEvidenceComplete": False,
            },
        ],
        "artifactTrustCases": [
            {
                "question": "Do missing-lineage and stale-source reports remain blocked from promotion?",
                "manifest": load_manifest(root),
                "action": "artifact_generation",
                "expectedBlocked": True,
                "expectedBlockingArtifacts": [
                    "artifacts/missing-lineage.md",
                    "artifacts/stale-report.md",
                ],
            },
            {
                "question": "Does a semantically plausible but unsupported claim still block trusted artifact promotion?",
                "manifest": load_manifest(root),
                "action": "artifact_generation",
                "expectedBlocked": True,
                "expectedBlockingArtifacts": [
                    "artifacts/missing-lineage.md",
                    "artifacts/semantic-output.md",
                    "artifacts/stale-report.md",
                ],
            },
        ],
        "reproducibilityCases": [
            {
                "question": "Does rerunning the deterministic report restore it from stale to partially verified?",
                "outputs": {"artifacts/report.md": "stable report\n"},
                "runId": "rerun-benchmark",
                "expectedStatus": "passed",
                "expectedArtifactStates": {"artifacts/report.md": "partially_verified"},
            }
        ],
    }


__all__ = ["seed_default_integrity_benchmark_corpus"]
