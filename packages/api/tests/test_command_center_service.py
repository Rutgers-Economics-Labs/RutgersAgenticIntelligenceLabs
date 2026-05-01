from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIL_PY_ROOT = Path(__file__).parents[2] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))


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
    assert sources["summary"]["count"] == 2
    assert {row["id"] for row in sources["sources"]} == {"pjm", "noaa"}
    assert artifacts["summary"]["count"] == 1
    assert artifacts["artifacts"][0]["preview"]["content"].startswith("# Summary")
    assert artifacts["artifacts"][0]["promotionState"] == "verified"
    assert artifacts["artifacts"][0]["verificationStatus"] == "passed"
    assert artifacts["artifacts"][0]["assumptions"] == ["research_plan/state/assumptions.json#baseline-window"]
    assert integrity["summary"]["assumptionCount"] == 1
    assert integrity["summary"]["sourceCount"] == 1
    assert integrity["summary"]["claimCount"] == 1
    assert integrity["summary"]["artifactCount"] == 1
    assert integrity["summary"]["verificationRunCount"] == 1
    assert integrity["summary"]["promotionStateCounts"]["verified"] == 1


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
