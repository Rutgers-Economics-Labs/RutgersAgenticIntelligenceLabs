from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

RAIL_PY_ROOT = Path(__file__).parents[2] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))
API_ROOT = Path(__file__).parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(root: Path) -> dict:
    return {
        "_id": "project-id",
        "name": "Grid Study",
        "slug": "grid-study",
        "status": "ready",
        "localRepoPath": str(root),
        "defaultBranch": "main",
    }


def test_skills_sources_and_artifacts_read_repo_files(tmp_path: Path):
    from app.services import command_center_service

    _write(tmp_path / "agents" / "research.yaml", "role: research\nskills:\n  allow_use: true\n")
    _write(tmp_path / "skills" / "web-research.md", "# Web Research\n\nFind primary sources.\n")
    _write(
        tmp_path / "research_plan" / "graph" / "sources.yaml",
        """
sources:
  - slug: pjm
    name: PJM Data Miner
    provider: PJM
    readiness: ready
    reason: Historical load and LMP data.
""",
    )
    _write(tmp_path / ".ontology" / "sources" / "noaa.yaml", "name: NOAA CDO\ntype: api\n")
    _write(tmp_path / "artifacts" / "summary.md", "# Summary\n\nResult.\n")
    _write(
        tmp_path / "research_plan" / "state" / "assumptions.json",
        """[
  {
    "assumption_key": "baseline-window",
    "title": "Baseline window",
    "value": "2010-2024",
    "status": "active",
    "source_path": "research_plan/state/assumptions.json",
    "affected_paths": ["artifacts/summary.md"]
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "sources.json",
        """[
  {
    "source_key": "pjm-hourly-load",
    "source_type": "dataset",
    "title": "PJM hourly load",
    "url_or_path": "https://example.com/pjm.csv",
    "freshness_status": "fresh",
    "quality_status": "validated",
    "source_path": "research_plan/state/sources.json"
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "claims.json",
        """[
  {
    "claim_key": "claim-001",
    "claim_text": "Grid costs increased during peak summer intervals.",
    "artifact_path": "artifacts/summary.md",
    "evidence_paths": ["topics/grid/outputs/peak_costs.csv"],
    "status": "supported",
    "source_path": "research_plan/state/claims.json",
    "caveats": []
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "artifact_lineage.json",
        """[
  {
    "artifact_path": "artifacts/summary.md",
    "artifact_type": "report",
    "title": "Summary",
    "promotion_state": "verified",
    "inputs": ["topics/grid/outputs/peak_costs.csv"],
    "scripts": ["topics/grid/scripts/analyze.py"],
    "sources": ["research_plan/state/sources.json#pjm-hourly-load"],
    "assumptions": ["research_plan/state/assumptions.json#baseline-window"],
    "claims": ["research_plan/state/claims.json#claim-001"],
    "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
    "stale_reasons": []
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "verification_runs.json",
        """[
  {
    "run_id": "run-001",
    "status": "passed",
    "checks": [],
    "artifact_paths": ["artifacts/summary.md"],
    "blockers": [],
    "source_path": "research_plan/state/verification_runs.json"
  }
]
""",
    )
    project = _project(tmp_path)

    skills = command_center_service.list_project_skills(project)
    sources = command_center_service.list_project_sources(project)
    artifacts = command_center_service.list_project_artifacts(project)
    integrity = command_center_service.list_project_integrity(project)

    assert skills["summary"]["count"] == 1
    assert skills["skills"][0]["usedBy"] == ["research"]
    assert sources["summary"]["count"] == 3
    assert {row["id"] for row in sources["sources"]} == {"pjm", "noaa", "pjm-hourly-load"}
    repo_source = next(row for row in sources["sources"] if row["id"] == "pjm-hourly-load")
    assert repo_source["sourceState"]["isFresh"] is True
    assert sources["summary"]["freshnessCounts"]["fresh"] == 1
    assert artifacts["summary"]["count"] == 1
    assert artifacts["artifacts"][0]["preview"]["content"].startswith("# Summary")
    assert artifacts["artifacts"][0]["promotionState"] == "verified"
    assert artifacts["artifacts"][0]["verificationStatus"] == "passed"
    assert artifacts["artifacts"][0]["trustState"]["isTrusted"] is True
    assert artifacts["artifacts"][0]["trustState"]["isBlocked"] is False
    assert artifacts["artifacts"][0]["trustState"]["isStale"] is False
    assert artifacts["artifacts"][0]["trustState"]["recommendedNextAction"] == "Trust state is current."
    assert artifacts["artifacts"][0]["assumptions"] == ["research_plan/state/assumptions.json#baseline-window"]
    assert artifacts["summary"]["trustedCount"] == 1
    assert artifacts["summary"]["blockedCount"] == 0
    assert integrity["summary"]["assumptionCount"] == 1
    assert integrity["summary"]["sourceCount"] == 1
    assert integrity["summary"]["sourceFreshnessCounts"]["fresh"] == 1
    assert integrity["summary"]["claimCount"] == 1
    assert integrity["summary"]["artifactCount"] == 1
    assert integrity["summary"]["verificationRunCount"] == 1
    assert integrity["summary"]["promotionStateCounts"]["verified"] == 1
    assert integrity["indexes"]["sources"][0]["sourceState"]["isFresh"] is True
    assert integrity["indexes"]["artifact_lineage"][0]["verificationStatus"] == "passed"
    assert integrity["indexes"]["artifact_lineage"][0]["trustState"]["isTrusted"] is True
    assert integrity["indexes"]["artifact_lineage"][0]["trustState"]["recommendedNextAction"] == "Trust state is current."
    assert integrity["agentWorkflow"]["research"]["requirements"]
    assert integrity["agentWorkflow"]["health"]["status"] == "ready"


def test_launch_preview_and_approval_create_repo_tasks(tmp_path: Path):
    from app.services import command_center_service

    project = _project(tmp_path)
    payload = {
        "researchQuestion": "How do data centers affect grid costs?",
        "workflowPresets": ["feasibility_memo", "econometric_model"],
        "approvalBeforeWrites": True,
    }

    preview = command_center_service.build_launch_preview(project, payload)
    result = asyncio.run(command_center_service.approve_launch_preview(project, payload))

    assert preview["skillsToUse"]
    assert len(result["tasks"]) == 2
    assert (tmp_path / "research_plan" / "tasks").is_dir()
    assert (tmp_path / "research_plan" / "approvals").is_dir()


def test_integrity_summary_surfaces_role_specific_blockers(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "state" / "sources.json",
        """[
  {
    "source_key": "stale-source",
    "source_type": "dataset",
    "title": "Stale Source",
    "url_or_path": "https://example.com/stale.csv",
    "freshness_status": "stale",
    "quality_status": "validated",
    "provenance": {"text": "Old extract."},
    "source_path": "research_plan/state/sources.json"
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "claims.json",
        """[
  {
    "claim_key": "claim-001",
    "claim_text": "A claim without evidence.",
    "artifact_path": "artifacts/report.md",
    "status": "needs_evidence",
    "source_path": "research_plan/state/claims.json",
    "caveats": []
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "artifact_lineage.json",
        """[
  {
    "artifact_path": "topics/analysis.csv",
    "artifact_type": "dataset",
    "title": "Analysis Dataset",
    "promotion_state": "draft",
    "sources": [],
    "stale_reasons": []
  },
  {
    "artifact_path": "artifacts/report.md",
    "artifact_type": "report",
    "title": "Report",
    "promotion_state": "draft",
    "claims": ["research_plan/state/claims.json#claim-001"],
    "inputs": [],
    "scripts": [],
    "verification_runs": [],
    "stale_reasons": []
  }
]
""",
    )
    _write(
        tmp_path / "research_plan" / "state" / "verification_runs.json",
        """[
  {
    "run_id": "run-001",
    "status": "failed",
    "checks": [],
    "artifact_paths": ["artifacts/report.md"],
    "blockers": [],
    "source_path": "research_plan/state/verification_runs.json"
  }
]
""",
    )

    integrity = command_center_service.list_project_integrity(_project(tmp_path))

    assert integrity["agentWorkflow"]["data"]["status"] == "blocked"
    assert "topics/analysis.csv" in integrity["agentWorkflow"]["data"]["datasetsMissingProvenance"]
    assert "topics/analysis.csv" in integrity["agentWorkflow"]["data"]["datasetsMissingFreshness"]
    assert integrity["agentWorkflow"]["coding"]["status"] == "blocked"
    assert "artifacts/report.md" in integrity["agentWorkflow"]["coding"]["artifactsMissingLineage"]
    assert integrity["agentWorkflow"]["artifact"]["status"] == "blocked"
    assert "artifacts/report.md" in integrity["agentWorkflow"]["artifact"]["artifactsWithUnsupportedClaims"]
    assert integrity["agentWorkflow"]["health"]["status"] == "blocked"
    assert "claim-001" in integrity["agentWorkflow"]["health"]["missingEvidenceClaims"]
    assert "stale-source" in integrity["agentWorkflow"]["health"]["staleSources"]
    assert "run-001" in integrity["agentWorkflow"]["health"]["failedVerificationRuns"]


def test_build_command_center_surfaces_latest_audit_and_current_blocker(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "audits" / "sess-2.json",
        json.dumps(
            {
                "generatedAt": "2026-05-17T10:00:00Z",
                "session": {
                    "id": "sess-2",
                    "role": "data",
                    "status": "completed",
                    "reviewStatus": "needs_changes",
                    "verificationStatus": "passed",
                    "publishStatus": "published",
                },
                "planner": {"taskCounts": {"blocked": 1}, "readyTasks": [], "blockedTasks": ["Repair source config"], "activeTasks": []},
                "integrity": {"action": "artifact_generation", "blocked": True, "reasons": ["Datasets must record source provenance before promotion."]},
                "currentBlocker": "Datasets must record source provenance before promotion.",
            },
            indent=2,
        ),
    )

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["currentBlocker"] == "Datasets must record source provenance before promotion."
    assert center["auditedTruth"]["session"]["id"] == "sess-2"
    assert center["auditedTruth"]["path"] == "research_plan/audits/sess-2.json"


def test_build_command_center_surfaces_source_admissibility_counts(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "state" / "sources.json",
        """[
  {
    "source_key": "observed-series",
    "source_type": "dataset",
    "title": "Observed Series",
    "url_or_path": "https://example.com/observed.csv",
    "freshness_status": "fresh",
    "quality_status": "validated",
    "admissibility_status": "observed",
    "source_path": "research_plan/state/sources.json"
  },
  {
    "source_key": "estimated-series",
    "source_type": "dataset",
    "title": "Estimated Series",
    "url_or_path": "https://example.com/estimated.csv",
    "freshness_status": "fresh",
    "quality_status": "validated",
    "admissibility_status": "estimated",
    "source_path": "research_plan/state/sources.json"
  }
]
""",
    )

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["integritySummary"]["sourceAdmissibilityCounts"]["observed"] == 1
    assert center["integritySummary"]["sourceAdmissibilityCounts"]["estimated"] == 1


def test_build_command_center_surfaces_project_reality_summary(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": True,
            "duplicateTaskFileCount": 1,
            "taskSessionMismatchCount": 2,
            "staleRuntimeSessionCount": 1,
            "staleAuditSessionCount": 3,
            "terminalSessionCount": 4,
            "activeRuntimeSessionCount": 1,
        }

    monkeypatch.setattr(command_center_service, "project_reality_status", _project_reality_status)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["projectReality"]["hasDrift"] is True
    assert center["projectReality"]["taskSessionMismatchCount"] == 2
    assert center["projectReality"]["staleAuditSessionCount"] == 3


def test_source_listing_surfaces_repo_backed_freshness_state(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "state" / "sources.json",
        """[
  {
    "source_key": "stale-source",
    "source_type": "dataset",
    "title": "Stale Source",
    "url_or_path": "https://example.com/stale.csv",
    "freshness_status": "stale",
    "quality_status": "validated",
    "source_path": "research_plan/state/sources.json"
  }
]
""",
    )

    sources = command_center_service.list_project_sources(_project(tmp_path))
    row = next(item for item in sources["sources"] if item["id"] == "stale-source")

    assert row["freshnessStatus"] == "stale"
    assert row["sourceState"]["isStale"] is True
    assert sources["summary"]["freshnessCounts"]["stale"] == 1


def test_source_listing_summarizes_admissibility_state(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "state" / "sources.json",
        """[
  {
    "source_key": "estimated-series",
    "source_type": "dataset",
    "title": "Estimated Series",
    "url_or_path": "https://example.com/estimated.csv",
    "freshness_status": "fresh",
    "quality_status": "validated",
    "admissibility_status": "estimated",
    "source_path": "research_plan/state/sources.json"
  }
]
""",
    )

    sources = command_center_service.list_project_sources(_project(tmp_path))
    row = next(item for item in sources["sources"] if item["id"] == "estimated-series")

    assert row["sourceState"]["admissibilityStatus"] == "estimated"
    assert row["sourceState"]["isAdmissible"] is False
    assert sources["summary"]["admissibilityCounts"]["estimated"] == 1


def test_artifact_listing_surfaces_blocked_and_stale_trust_states(tmp_path: Path):
    from app.services import command_center_service

    _write(tmp_path / "artifacts" / "blocked.md", "# Blocked\n")
    _write(tmp_path / "artifacts" / "stale.md", "# Stale\n")
    _write(
        tmp_path / "research_plan" / "state" / "artifact_lineage.json",
        """[
  {
    "artifact_path": "artifacts/blocked.md",
    "artifact_type": "report",
    "title": "Blocked",
    "promotion_state": "needs_evidence",
    "stale_reasons": ["claim_needs_evidence:claim-001"]
  },
  {
    "artifact_path": "artifacts/stale.md",
    "artifact_type": "report",
    "title": "Stale",
    "promotion_state": "stale",
    "stale_reasons": ["source_changed:sample"]
  }
]
""",
    )

    artifacts = command_center_service.list_project_artifacts(_project(tmp_path))
    by_path = {item["path"]: item for item in artifacts["artifacts"]}

    assert by_path["artifacts/blocked.md"]["trustState"]["isBlocked"] is True
    assert by_path["artifacts/blocked.md"]["trustState"]["isTrusted"] is False
    assert by_path["artifacts/stale.md"]["trustState"]["isStale"] is True
    assert artifacts["summary"]["blockedCount"] == 1


def test_build_launch_preview_adds_role_specific_acceptance_contracts(tmp_path: Path):
    from app.services import command_center_service

    project = _project(tmp_path)
    preview = command_center_service.build_launch_preview(
        project,
        {
            "researchQuestion": "What changed in regional grid costs?",
            "workflowPresets": ["feasibility_memo", "data_pipeline", "econometric_model", "technical_report", "integrity_review"],
            "approvalBeforeWrites": False,
        },
    )

    tasks = {item["agentRole"]: item for item in preview["agentWorkBreakdown"]}
    assert "Facts, interpretations, and open questions are separated explicitly." in tasks["research"]["acceptanceCriteria"]
    assert "Datasets preserve provenance and freshness metadata before handoff." in tasks["data"]["acceptanceCriteria"]
    assert "Analysis outputs declare inputs, scripts, and verification commands." in tasks["coding"]["acceptanceCriteria"]
    assert "Artifacts preserve evidence links and avoid unsupported trusted narratives." in tasks["artifact"]["acceptanceCriteria"]
    assert "Missing evidence, stale sources, and reproducibility gaps are reported explicitly." in tasks["health"]["acceptanceCriteria"]
