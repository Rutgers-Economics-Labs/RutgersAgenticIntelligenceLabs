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
    # build_launch_preview auto-appends a Meta-synthesis closeout task
    # whenever no preset already produces one, so the two requested presets
    # become three planner rows (feasibility_memo + econometric_model + meta-synthesis).
    assert len(result["tasks"]) == 3
    titles = {task["title"] for task in result["tasks"]}
    assert any("Meta-synthesis closeout" in title for title in titles)
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


def test_persist_control_plane_snapshot_writes_repo_backed_snapshot(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _build_live_command_center(project_arg):
        return {
            "project": {
                "id": project_arg["_id"],
                "name": project_arg["name"],
                "slug": project_arg["slug"],
                "status": project_arg["status"],
                "localRepoPath": project_arg["localRepoPath"],
                "defaultBranch": project_arg["defaultBranch"],
            },
            "currentPlan": {"summary": "Current plan"},
            "missionBrief": {"now": "Now", "next": "Next"},
            "goal": {"objective": "Finish report"},
            "nextAction": "Review pending approvals",
            "taskCounts": {"total": 3, "byStatus": {"ready": 2, "running": 1}},
            "plannerSnapshot": {
                "now": [{"id": "task-1", "title": "Run hydration", "status": "ready", "description": ""}],
                "next": [],
                "later": [],
                "done": [],
                "blocked": [],
            },
            "latestTruth": [
                {
                    "claim": "Forecast error widened in summer peaks.",
                    "confidence": 0.95,
                    "evidenceRefs": ["topics/grid/outputs/error.csv"],
                    "verified": True,
                }
            ],
            "recentArtifacts": [{"path": "artifacts/report.md"}],
            "sourceSummary": {"count": 2},
            "skillSummary": {"count": 1},
            "integritySummary": {"staleArtifactCount": 0},
            "hypothesisTaskLinks": [],
            "ontologyFollowUps": {"questions": []},
            "auditedTruth": {"currentBlocker": None},
            "recentAudits": [],
            "lifecyclePhase": "research_active",
            "closeoutCertificate": {"status": "pending"},
            "currentBlocker": None,
            "blockerSummary": {"blocked": False},
            "repairQueue": {"count": 0, "tasks": []},
            "recommendedRepairTask": None,
            "projectReality": {"hasDrift": False},
            "auditors": {"session": {"status": "ready"}},
            "repoHealth": {"hasLocalRepo": True, "hasRailYaml": True, "hasResearchPlan": True},
            "activeSessions": [],
            "pendingApprovals": [],
            "snapshot": {"loaded": False},
        }

    monkeypatch.setattr(command_center_service, "_build_live_command_center", _build_live_command_center)

    result = asyncio.run(command_center_service.persist_control_plane_snapshot(_project(tmp_path)))

    assert result["path"] == "research_plan/state/control_plane_snapshot.json"
    snapshot_path = tmp_path / "research_plan" / "state" / "control_plane_snapshot.json"
    assert snapshot_path.exists()
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["snapshotVersion"] == command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION
    assert payload["commandCenter"]["goal"]["objective"] == "Finish report"
    assert payload["commandCenter"]["plannerSnapshot"]["now"][0]["title"] == "Run hydration"
    assert payload["commandCenter"]["latestTruth"][0]["verified"] is True
    assert payload["commandCenter"]["projectReality"]["hasDrift"] is False


def test_build_command_center_prefers_repo_snapshot_when_available(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    snapshot_payload = {
        "snapshotVersion": command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION,
        "generatedAt": 1234567890,
        "commandCenter": {
            "currentPlan": {"summary": "Snapshot plan"},
            "missionBrief": {"now": "Snapshot now", "next": "Snapshot next"},
            "goal": {"objective": "Snapshot goal"},
            "nextAction": "Stale snapshot action",
            "taskCounts": {"total": 2, "byStatus": {"ready": 2}},
            "plannerSnapshot": {
                "now": [{"id": "task-1", "title": "Snapshot plan", "status": "ready", "description": ""}],
                "next": [],
                "later": [],
                "done": [],
                "blocked": [],
            },
            "latestTruth": [
                {
                    "claim": "Snapshot truth",
                    "confidence": 0.95,
                    "evidenceRefs": ["topics/analysis/output.csv"],
                    "verified": True,
                }
            ],
            "recentArtifacts": [{"path": "artifacts/snapshot-report.md"}],
            "sourceSummary": {"count": 5},
            "skillSummary": {"count": 4},
            "integritySummary": {"staleArtifactCount": 1},
            "hypothesisTaskLinks": [],
            "ontologyFollowUps": {"questions": []},
            "auditedTruth": {"currentBlocker": "Snapshot blocker"},
            "recentAudits": [],
            "lifecyclePhase": "closeout",
            "closeoutCertificate": {"status": "pending"},
            "currentBlocker": "Snapshot blocker",
            "blockerSummary": {"blocked": True, "headline": "Snapshot blocker"},
            "repairQueue": {"count": 1, "tasks": [{"id": "repair-1", "title": "Repair snapshot"}]},
            "recommendedRepairTask": {"id": "repair-1", "title": "Repair snapshot"},
            "projectReality": {"hasDrift": True},
            "auditors": {"session": {"status": "blocked"}},
            "repoHealth": {"hasLocalRepo": True, "hasRailYaml": True, "hasResearchPlan": True},
        },
    }
    _write(
        tmp_path / "research_plan" / "state" / "control_plane_snapshot.json",
        json.dumps(snapshot_payload, indent=2),
    )

    async def _list_approvals(project_arg):
        return [{"_id": "approval-1", "status": "pending"}]

    async def _list_project_running_agents(project_id: str, active_only: bool = False, limit: int = 20):
        return [{"_id": "sess-1", "status": "running", "role": "coding"}]

    class _PlannerService:
        async def list_approvals(self, project_arg):
            return await _list_approvals(project_arg)

        def project_root_from_record(self, project_arg):
            return Path(str(project_arg["localRepoPath"]))

    class _RunningAgentService:
        async def list_project_running_agents(self, project_id: str, active_only: bool = False, limit: int = 20):
            return await _list_project_running_agents(project_id, active_only=active_only, limit=limit)

    async def _build_live_command_center(project_arg):
        raise AssertionError("live command-center build should not run when snapshot is present")

    monkeypatch.setattr(command_center_service, "_runtime_services", lambda: (_PlannerService(), _RunningAgentService()))
    monkeypatch.setattr(command_center_service, "_build_live_command_center", _build_live_command_center)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["goal"]["objective"] == "Snapshot goal"
    assert center["plannerSnapshot"]["now"][0]["title"] == "Snapshot plan"
    assert center["latestTruth"][0]["claim"] == "Snapshot truth"
    assert center["projectReality"]["hasDrift"] is True
    assert center["activeSessions"][0]["_id"] == "sess-1"
    assert center["pendingApprovals"][0]["_id"] == "approval-1"
    assert center["nextAction"] == "Review pending approvals"
    assert center["snapshot"]["loaded"] is True
    assert center["snapshot"]["path"] == "research_plan/state/control_plane_snapshot.json"


def test_load_control_plane_summary_returns_shared_summary_and_meta(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "research_plan" / "state" / "control_plane_snapshot.json",
        json.dumps(
            {
                "snapshotVersion": command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION,
                "generatedAt": 1234567890,
                "commandCenter": {
                    "lifecyclePhase": "research_active",
                    "currentBlocker": "Snapshot blocker",
                    "projectReality": {"hasDrift": True},
                },
            },
            indent=2,
        ),
    )

    projection = command_center_service.load_control_plane_summary(_project(tmp_path))

    assert projection["summary"]["lifecyclePhase"] == "research_active"
    assert projection["summary"]["currentBlocker"] == "Snapshot blocker"
    assert projection["snapshot"] == {
        "loaded": True,
        "path": "research_plan/state/control_plane_snapshot.json",
        "generatedAt": 1234567890,
        "version": command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION,
    }


def test_build_command_center_surfaces_latest_audit_and_current_blocker(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {}

    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

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
    assert center["recentAudits"][0]["session"]["id"] == "sess-2"
    assert center["recentAudits"][0]["integrity"]["reason"] == "Datasets must record source provenance before promotion."


def test_build_command_center_surfaces_recent_audit_timeline(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {}

    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    _write(
        tmp_path / "research_plan" / "audits" / "sess-1.json",
        json.dumps(
            {
                "generatedAt": "2026-05-17T09:00:00Z",
                "session": {
                    "id": "sess-1",
                    "role": "research",
                    "status": "completed",
                    "reviewStatus": "approved",
                    "verificationStatus": "passed",
                    "publishStatus": "published",
                },
                "planner": {"taskCounts": {"ready": 2, "blocked": 0}},
                "integrity": {"blocked": False, "reasons": []},
                "currentBlocker": None,
            },
            indent=2,
        ),
    )
    _write(
        tmp_path / "research_plan" / "audits" / "sess-2.json",
        json.dumps(
            {
                "generatedAt": "2026-05-17T10:00:00Z",
                "session": {
                    "id": "sess-2",
                    "role": "data",
                    "status": "failed",
                    "reviewStatus": "needs_changes",
                    "verificationStatus": "failed",
                    "publishStatus": "not_started",
                },
                "planner": {"taskCounts": {"ready": 1, "blocked": 1}},
                "integrity": {"blocked": True, "reasons": ["Verification failed."]},
                "currentBlocker": "Verification failed.",
            },
            indent=2,
        ),
    )

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert [row["session"]["id"] for row in center["recentAudits"][:2]] == ["sess-2", "sess-1"]
    assert center["recentAudits"][0]["planner"]["blockedTaskCount"] == 1
    assert center["recentAudits"][1]["integrity"]["blocked"] is False


def test_build_command_center_surfaces_source_admissibility_counts(tmp_path: Path):
    from app.services import command_center_service

    _write(
        tmp_path / "rail.yaml",
        """version: 1
project:
  name: Grid Study
  slug: grid-study
  default_branch: main
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
frontend:
  topic_index_mode: filesystem
  artifact_index_mode: filesystem
""",
    )
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
    assert center["sourceSummary"]["admissibilityCounts"]["estimated"] == 1
    assert center["sourceSummary"]["admissibilityHighlights"] == [
        {
            "id": "estimated-series",
            "name": "Estimated Series",
            "admissibilityStatus": "estimated",
            "freshnessStatus": "fresh",
            "qualityStatus": "validated",
        }
    ]


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
            "runningAgentRoleDriftCount": 1,
            "runningAgentRunnerDriftCount": 1,
            "ontologyArtifactDriftCount": 1,
            "artifactRegistryDriftCount": 2,
            "secretPolicyRoleDriftCount": 1,
            "roleConfigAliasDriftCount": 1,
            "details": {
                "duplicateTaskFiles": ["research_plan/tasks/task-b.md"],
                "taskSessionMismatchTaskIds": ["task-1", "task-2"],
                "staleRuntimeSessionIds": ["sess-1"],
                "staleAuditSessionIds": ["sess-2", "sess-3", "sess-4"],
                "terminalSessionIds": ["sess-1", "sess-2", "sess-3", "sess-4"],
                "activeRuntimeSessionIds": ["sess-1"],
                "runningAgentRoleDrift": {
                    "hasDrift": True,
                    "sessions": [
                        {
                            "sessionId": "sess-role",
                            "role": "developer",
                            "canonicalRole": "coding",
                        }
                    ],
                },
                "runningAgentRunnerDrift": {
                    "hasDrift": True,
                    "sessions": [
                        {
                            "sessionId": "sess-runner",
                            "runner": "CODEX_CLI",
                            "canonicalRunner": "codex_cli",
                        }
                    ],
                },
                "ontologyArtifactDrift": {
                    "hasDrift": True,
                    "activeDuckdbPath": "/tmp/old.duckdb",
                    "expectedDuckdbPath": "/tmp/new.duckdb",
                    "reason": "active_ontology_pointer_out_of_date",
                },
                "artifactRegistryDrift": {
                    "hasDrift": True,
                    "untrackedArtifactPaths": ["artifacts/untracked.md"],
                    "missingArtifactPaths": ["artifacts/missing.md"],
                },
                "secretPolicyRoleDrift": {
                    "hasDrift": True,
                    "policies": [
                        {
                            "policyId": "policy-1",
                            "agentRole": "developer",
                            "canonicalRole": "coding",
                            "allowedSecretNames": ["FRED_API_KEY"],
                        }
                    ],
                },
                "roleConfigAliasDrift": {
                    "hasDrift": True,
                    "configs": [
                        {
                            "configPath": "agents/coding.yaml",
                            "role": "developer",
                            "canonicalRole": "coding",
                        }
                    ],
                },
            },
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": [], "state": None},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(command_center_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["projectReality"]["hasDrift"] is True
    assert center["projectReality"]["taskSessionMismatchCount"] == 2
    assert center["projectReality"]["staleAuditSessionCount"] == 3
    assert center["projectReality"]["runningAgentRoleDriftCount"] == 1
    assert center["projectReality"]["runningAgentRunnerDriftCount"] == 1
    assert center["projectReality"]["ontologyArtifactDriftCount"] == 1
    assert center["projectReality"]["artifactRegistryDriftCount"] == 2
    assert center["projectReality"]["secretPolicyRoleDriftCount"] == 1
    assert center["projectReality"]["roleConfigAliasDriftCount"] == 1
    assert center["projectReality"]["details"]["duplicateTaskFiles"] == ["research_plan/tasks/task-b.md"]


def test_build_command_center_surfaces_auditor_statuses(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) still marked active."]},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["auditors"]["session"]["status"] == "blocked"
    assert center["auditors"]["ontology"]["state"] == "not_hydrated"
    assert center["auditors"]["closeout"]["blockers"] == ["1 non-terminal task(s) remain."]


def test_build_command_center_surfaces_repair_queue(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Repair ontology readiness blockers",
                "status": "ready",
                "agentRole": "data",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "task-2",
                "title": "Resolve closeout blockers",
                "status": "running",
                "agentRole": "health",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "task-3",
                "title": "Synthesize final report",
                "status": "backlog",
                "agentRole": "artifact",
                "dependsOnTaskIds": [],
            },
        ]

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {}

    class _PlannerService:
        async def ensure_main_board(self, project_arg):
            return await _ensure_main_board(project_arg)

        async def list_tasks(self, board_id: str, *, project=None):
            return await _list_tasks(board_id, project=project)

        async def list_approvals(self, project_arg):
            return []

        def project_root_from_record(self, project_arg):
            return Path(str(project_arg["localRepoPath"]))

    class _RunningAgentService:
        async def list_project_running_agents(self, project_id, active_only=False, limit=20):
            return []

    monkeypatch.setattr(command_center_service, "_runtime_services", lambda: (_PlannerService(), _RunningAgentService()))
    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["repairQueue"]["count"] == 2
    assert center["repairQueue"]["readyCount"] == 1
    assert center["repairQueue"]["runningCount"] == 1
    assert center["repairQueue"]["tasks"][0]["title"] == "Repair ontology readiness blockers"
    assert center["repairQueue"]["tasks"][1]["title"] == "Resolve closeout blockers"


def test_build_command_center_recommends_matching_repair_task_for_blocked_auditor(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Repair ontology readiness blockers",
                "status": "backlog",
                "agentRole": "data",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "task-2",
                "title": "Resolve inadmissible sources for trusted outputs",
                "status": "ready",
                "agentRole": "health",
                "dependsOnTaskIds": [],
            },
            {
                "_id": "task-3",
                "title": "Resolve closeout blockers",
                "status": "ready",
                "agentRole": "health",
                "dependsOnTaskIds": [],
            },
        ]

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "blocked", "blockers": ["Inadmissible sources block trusted promotion."]},
            "closeout": {"status": "blocked", "blockers": ["Closeout is blocked until integrity is repaired."]},
        }

    class _PlannerService:
        async def ensure_main_board(self, project_arg):
            return await _ensure_main_board(project_arg)

        async def list_tasks(self, board_id: str, *, project=None):
            return await _list_tasks(board_id, project=project)

        async def list_approvals(self, project_arg):
            return []

        def project_root_from_record(self, project_arg):
            return Path(str(project_arg["localRepoPath"]))

    class _RunningAgentService:
        async def list_project_running_agents(self, project_id, active_only=False, limit=20):
            return []

    monkeypatch.setattr(command_center_service, "_runtime_services", lambda: (_PlannerService(), _RunningAgentService()))
    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["recommendedRepairTask"]["title"] == "Resolve inadmissible sources for trusted outputs"
    assert center["recommendedRepairTask"]["status"] == "ready"
    assert center["recommendedRepairTask"]["auditor"] == "integrity"
    assert center["recommendedRepairTask"]["reason"] == "Repair trusted-output integrity before promotion"


def test_build_command_center_surfaces_blocker_summary(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": True,
            "duplicateTaskFileCount": 1,
            "taskSessionMismatchCount": 2,
            "staleRuntimeSessionCount": 1,
            "runningAgentStatusDriftCount": 1,
            "runningAgentRoleDriftCount": 1,
            "runningAgentRunnerDriftCount": 1,
            "staleAuditSessionCount": 1,
            "terminalSessionCount": 2,
            "activeRuntimeSessionCount": 1,
            "secretPolicyRoleDriftCount": 1,
            "roleConfigAliasDriftCount": 1,
        }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "blocked", "blockers": ["1 stale runtime session(s) still marked active."]},
            "planner": {"status": "blocked", "blockers": ["1 duplicate task file(s) detected."]},
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."], "state": "not_hydrated"},
            "integrity": {"status": "blocked", "blockers": ["Unsupported claims prevent trusted promotion."]},
            "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
        }

    monkeypatch.setattr(command_center_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr(
        command_center_service,
        "read_latest_audit",
        lambda root: {"currentBlocker": "Autopilot is waiting for audited truth."},
    )

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["blockerSummary"]["blocked"] is True
    assert center["blockerSummary"]["headline"] == "Autopilot is waiting for audited truth."
    assert "Ontology hydration state is `not_hydrated`." in center["blockerSummary"]["reasons"]
    assert "Reconcile running-agent session statuses so live runtime state uses canonical lifecycle values." in center["blockerSummary"]["repairs"]
    assert "Reconcile running-agent session roles so live runtime state uses canonical agent roles." in center["blockerSummary"]["repairs"]
    assert "Reconcile running-agent session runners so live runtime state uses canonical runner values." in center["blockerSummary"]["repairs"]
    # Stale runtime sessions ranked above all other gates → operator routes to runs.
    assert center["blockerSummary"]["category"] == "stale_session"
    assert center["blockerSummary"]["categoryLabel"] == "Stale session"
    assert center["blockerSummary"]["severity"] == "critical"
    assert center["blockerSummary"]["fixHref"] == "/projects/grid-study/runs"


def test_blocker_category_classification_routes_through_priority_order():
    from app.services.command_center_service import _classify_blocker_category

    ready_auditors = {
        "session": {"status": "ready"},
        "planner": {"status": "ready"},
        "ontology": {"status": "ready"},
        "integrity": {"status": "ready"},
        "closeout": {"status": "ready"},
    }

    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors=ready_auditors,
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "clear"
    )

    # Pending approvals beat every downstream gate.
    assert (
        _classify_blocker_category(
            pending_approvals=[{"_id": "a1"}],
            reality={"staleRuntimeSessionCount": 1},
            auditors={**ready_auditors, "session": {"status": "blocked"}},
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "approval_required"
    )

    # Stale session beats downstream gates even when ontology is blocked.
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={"staleRuntimeSessionCount": 1},
            auditors={**ready_auditors, "ontology": {"status": "blocked", "stateClassification": "ready"}},
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "stale_session"
    )

    # Planner drift via reality counts (no session drift).
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={"duplicateTaskFileCount": 2},
            auditors=ready_auditors,
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "planner_drift"
    )

    # Hydration failure vs ontology health based on stateClassification.
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors={**ready_auditors, "ontology": {"status": "blocked", "stateClassification": "stale"}},
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "hydration_failure"
    )
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors={**ready_auditors, "ontology": {"status": "blocked", "stateClassification": "ready"}},
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "ontology_health"
    )

    # Integrity gap stays integrity_gap when at least one admitted source exists.
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors={**ready_auditors, "integrity": {"status": "blocked"}},
            integrity_summary={"sourceAdmissibilityCounts": {"admitted": 2, "candidate": 1}},
            source_summary={"count": 3},
        )
        == "integrity_gap"
    )
    # Routes to source_gap when no source has been admitted.
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors={**ready_auditors, "integrity": {"status": "blocked"}},
            integrity_summary={"sourceAdmissibilityCounts": {"admitted": 0, "candidate": 2, "rejected": 1}},
            source_summary={"count": 3},
        )
        == "source_gap"
    )

    # Empty source inventory on an otherwise-clean project still flags source_gap.
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors=ready_auditors,
            integrity_summary={},
            source_summary={"count": 0},
        )
        == "source_gap"
    )

    # Only closeout blocked → closeout_pending (info severity).
    assert (
        _classify_blocker_category(
            pending_approvals=[],
            reality={},
            auditors={**ready_auditors, "closeout": {"status": "blocked"}},
            integrity_summary={},
            source_summary={"count": 3},
        )
        == "closeout_pending"
    )


def test_closeout_certificate_issued_when_closeout_ready_and_phase_closed():
    from app.services.command_center_service import build_closeout_certificate

    ready = {"session": {"status": "ready"}, "planner": {"status": "ready"},
             "ontology": {"status": "ready"}, "integrity": {"status": "ready"},
             "closeout": {"status": "ready"}}
    cert = build_closeout_certificate(auditors=ready, phase="closed")
    assert cert["status"] == "issued"
    assert cert["blockers"] == []


def test_closeout_certificate_pending_when_closeout_blocked():
    from app.services.command_center_service import build_closeout_certificate

    auditors = {"session": {"status": "ready"}, "planner": {"status": "ready"},
                "ontology": {"status": "ready"}, "integrity": {"status": "ready"},
                "closeout": {"status": "blocked", "blockers": ["3 non-terminal task(s) remain."]}}
    cert = build_closeout_certificate(auditors=auditors, phase="synthesis_ready")
    assert cert["status"] == "pending"
    assert cert["blockers"] == ["3 non-terminal task(s) remain."]
    assert "3 non-terminal" in cert["headline"]


def test_closeout_certificate_would_issue_when_upstream_blocks():
    from app.services.command_center_service import build_closeout_certificate

    auditors = {"session": {"status": "ready"}, "planner": {"status": "ready"},
                "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `stale_on_this_device`."]},
                "integrity": {"status": "ready"},
                "closeout": {"status": "ready", "blockers": []}}
    cert = build_closeout_certificate(auditors=auditors, phase="research_active")
    assert cert["status"] == "would_issue_if"
    assert "ontology" in cert["headline"]


def test_build_command_center_surfaces_ontology_follow_up_classifications(tmp_path: Path, monkeypatch):
    from app.services import command_center_service

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "task-1",
                "title": "Expand ontology coverage for: 2. Which question requires expansion?",
                "status": "ready",
                "dependsOnTaskIds": [],
            }
        ]

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {}

    class _PlannerService:
        async def ensure_main_board(self, project_arg):
            return await _ensure_main_board(project_arg)

        async def list_tasks(self, board_id: str, *, project=None):
            return await _list_tasks(board_id, project=project)

        async def list_approvals(self, project_arg):
            return []

        def project_root_from_record(self, project_arg):
            return Path(str(project_arg["localRepoPath"]))

    class _RunningAgentService:
        async def list_project_running_agents(self, project_id, active_only=False, limit=20):
            return []

    monkeypatch.setattr(command_center_service, "_runtime_services", lambda: (_PlannerService(), _RunningAgentService()))
    monkeypatch.setattr(command_center_service, "build_auditor_statuses", _build_auditor_statuses)

    _write(
        tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md",
        """# Ontology-Answerable Follow-Up Questions

### 1. Which question is answerable now?

- Classification: `current_ontology`
- Why answerable now:
  - hydrated table exists

### 2. Which question requires expansion?

- Classification: `requires_expansion`
- Why expansion is needed:
  - missing domestic scope
""",
    )

    center = asyncio.run(command_center_service.build_command_center(_project(tmp_path)))

    assert center["ontologyFollowUps"]["path"] == "research_plan/ontology_answerable_follow_up_questions.md"
    assert center["ontologyFollowUps"]["classificationCounts"]["current_ontology"] == 1
    assert center["ontologyFollowUps"]["classificationCounts"]["requires_expansion"] == 1
    assert center["ontologyFollowUps"]["questions"][0]["title"] == "1. Which question is answerable now?"
    assert center["ontologyFollowUps"]["questions"][1]["expectedTaskTitle"] == "Expand ontology coverage for: 2. Which question requires expansion?"
    assert center["ontologyFollowUps"]["questions"][1]["taskPresent"] is True
    assert center["ontologyFollowUps"]["questions"][1]["taskStatus"] == "ready"


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

    # build_launch_preview appends a Meta-synthesis closeout task with
    # agentRole=artifact, so the dict-by-role would collapse the
    # technical_report (also artifact) onto the meta-synthesis row. Look up
    # the artifact-role row that matches the requested technical_report
    # preset by title instead.
    tasks = {item["agentRole"]: item for item in preview["agentWorkBreakdown"]}
    technical_report_task = next(
        item for item in preview["agentWorkBreakdown"]
        if item["agentRole"] == "artifact" and "Meta-synthesis" not in item["title"]
    )
    assert "Facts, interpretations, and open questions are separated explicitly." in tasks["research"]["acceptanceCriteria"]
    assert "Datasets preserve provenance and freshness metadata before handoff." in tasks["data"]["acceptanceCriteria"]
    assert "Analysis outputs declare inputs, scripts, and verification commands." in tasks["coding"]["acceptanceCriteria"]
    assert "Artifacts preserve evidence links and avoid unsupported trusted narratives." in technical_report_task["acceptanceCriteria"]
    assert "Missing evidence, stale sources, and reproducibility gaps are reported explicitly." in tasks["health"]["acceptanceCriteria"]
