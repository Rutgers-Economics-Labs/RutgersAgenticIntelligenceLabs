from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIL_PY_ROOT = Path(__file__).parents[2] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))
API_ROOT = Path(__file__).parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def test_build_auditor_statuses_reports_blockers(tmp_path: Path, monkeypatch):
    from app.services import auditor_service

    project = {
        "_id": "project-id",
        "name": "Grid Study",
        "slug": "grid-study",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "approach": "ontology-first",
    }
    (tmp_path / ".ontology").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rail.yaml").write_text(
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
        encoding="utf-8",
    )

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": True,
            "duplicateTaskFileCount": 1,
            "taskSessionMismatchCount": 2,
            "staleRuntimeSessionCount": 1,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 1,
            "activeRuntimeSessionCount": 1,
        }

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "not_hydrated", "reusableArtifact": {}, "currentDeviceArtifacts": []}

    monkeypatch.setattr(auditor_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(auditor_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(
        auditor_service,
        "evaluate_integrity_gate",
        lambda root, manifest, action: {"blocked": action == "closeout", "reasons": [f"{action} blocked"]},
    )

    result = asyncio.run(
        auditor_service.build_auditor_statuses(
            project,
            tasks=[{"_id": "task-1", "status": "ready"}],
            active_sessions=[{"_id": "sess-1"}],
        )
    )

    assert result["session"]["status"] == "blocked"
    assert result["planner"]["status"] == "blocked"
    assert result["ontology"]["status"] == "blocked"
    assert result["integrity"]["status"] == "ready"
    assert result["closeout"]["status"] == "blocked"
