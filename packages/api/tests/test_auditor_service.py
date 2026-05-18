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
            "runningAgentStatusDriftCount": 1,
            "runningAgentRoleDriftCount": 1,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 1,
            "activeRuntimeSessionCount": 1,
            "roleConfigAliasDriftCount": 1,
            "details": {
                "ontologyArtifactDrift": {"hasDrift": False},
                "artifactRegistryDrift": {"hasDrift": False, "untrackedArtifactPaths": [], "missingArtifactPaths": []},
            },
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
    assert "1 running-agent session status alias row(s) detected." in result["session"]["blockers"]
    assert "1 running-agent session role alias row(s) detected." in result["session"]["blockers"]
    assert result["planner"]["status"] == "blocked"
    assert "1 role config alias declaration(s) detected." in result["planner"]["blockers"]
    assert result["ontology"]["status"] == "blocked"
    assert result["integrity"]["status"] == "ready"
    assert result["closeout"]["status"] == "blocked"


def test_build_auditor_statuses_blocks_closeout_when_follow_up_expansion_tasks_are_missing(tmp_path: Path, monkeypatch):
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
    (tmp_path / "research_plan").mkdir(parents=True, exist_ok=True)
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
    (tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md").write_text(
        """# Ontology-Answerable Follow-Up Questions

### 1. Which external data source would unlock wage-bill analysis?

- Classification: `blocked_by_data`

### 2. How do findings change after expanding to additional regional leagues?

- Classification: `requires_expansion`
""",
        encoding="utf-8",
    )

    async def _project_reality_status(project_arg, *, tasks=None, active_sessions=None):
        return {
            "hasDrift": False,
            "duplicateTaskFileCount": 0,
            "taskSessionMismatchCount": 0,
            "staleRuntimeSessionCount": 0,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 0,
            "activeRuntimeSessionCount": 0,
            "details": {
                "ontologyArtifactDrift": {"hasDrift": False},
                "artifactRegistryDrift": {"hasDrift": False, "untrackedArtifactPaths": [], "missingArtifactPaths": []},
            },
        }

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "hydrated_on_this_device", "reusableArtifact": {"duckdbArtifactPath": None}, "currentDeviceArtifacts": []}

    monkeypatch.setattr(auditor_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(auditor_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(auditor_service, "_duckdb_has_populated_rows", lambda path: True)
    monkeypatch.setattr(
        auditor_service,
        "evaluate_integrity_gate",
        lambda root, manifest, action: {"blocked": False, "reasons": []},
    )

    result = asyncio.run(
        auditor_service.build_auditor_statuses(
            project,
            tasks=[{"_id": "task-1", "title": "Existing Task", "status": "done"}],
            active_sessions=[],
        )
    )

    assert result["closeout"]["status"] == "blocked"
    assert "Missing data-blocker task for follow-up question: 1. Which external data source would unlock wage-bill analysis?" in result["closeout"]["blockers"]
    assert "Missing ontology expansion task for follow-up question: 2. How do findings change after expanding to additional regional leagues?" in result["closeout"]["blockers"]


def test_build_auditor_statuses_blocks_closeout_when_artifacts_are_missing_or_untracked(tmp_path: Path, monkeypatch):
    from app.services import auditor_service
    from rail.integrity import ResearchIntegrityRepo

    project = {
        "_id": "project-id",
        "name": "Grid Study",
        "slug": "grid-study",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "approach": "ontology-first",
    }
    (tmp_path / ".ontology").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research_plan").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
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
            "hasDrift": False,
            "duplicateTaskFileCount": 0,
            "taskSessionMismatchCount": 0,
            "staleRuntimeSessionCount": 0,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 0,
            "activeRuntimeSessionCount": 0,
            "details": {
                "ontologyArtifactDrift": {"hasDrift": False},
                "artifactRegistryDrift": {"hasDrift": False, "untrackedArtifactPaths": [], "missingArtifactPaths": []},
            },
        }

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "hydrated_on_this_device", "reusableArtifact": {"duckdbArtifactPath": None}, "currentDeviceArtifacts": []}

    monkeypatch.setattr(auditor_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(auditor_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(auditor_service, "_duckdb_has_populated_rows", lambda path: True)

    result_without_artifacts = asyncio.run(
        auditor_service.build_auditor_statuses(
            project,
            tasks=[{"_id": "task-1", "title": "Existing Task", "status": "done"}],
            active_sessions=[],
        )
    )

    assert result_without_artifacts["closeout"]["status"] == "blocked"
    assert "No final artifacts are present under the configured artifacts root." in result_without_artifacts["closeout"]["blockers"]

    (tmp_path / "artifacts" / "report.md").write_text("# Report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(tmp_path)
    repo.ensure_files_exist()

    result_with_untracked_artifact = asyncio.run(
        auditor_service.build_auditor_statuses(
            project,
            tasks=[{"_id": "task-1", "title": "Existing Task", "status": "done"}],
            active_sessions=[],
        )
    )

    assert result_with_untracked_artifact["closeout"]["status"] == "blocked"
    assert any(
        blocker.startswith("Final artifacts exist on disk without lineage records:")
        for blocker in result_with_untracked_artifact["closeout"]["blockers"]
    )


def test_build_auditor_statuses_blocks_ontology_and_integrity_on_project_reality_drift(tmp_path: Path, monkeypatch):
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
            "duplicateTaskFileCount": 0,
            "taskSessionMismatchCount": 0,
            "staleRuntimeSessionCount": 0,
            "runningAgentStatusDriftCount": 1,
            "runningAgentRoleDriftCount": 1,
            "staleAuditSessionCount": 0,
            "terminalSessionCount": 0,
            "activeRuntimeSessionCount": 0,
            "secretPolicyRoleDriftCount": 1,
            "roleConfigAliasDriftCount": 1,
            "details": {
                "ontologyArtifactDrift": {
                    "hasDrift": True,
                    "reason": "active_ontology_pointer_out_of_date",
                },
                "artifactRegistryDrift": {
                    "hasDrift": True,
                    "untrackedArtifactPaths": ["artifacts/untracked.md"],
                    "missingArtifactPaths": ["artifacts/missing.md"],
                },
            },
        }

    async def _get_hydration_status(*, project, pipeline_slug=None, hydration_mode="full"):
        return {"state": "hydrated_on_this_device", "reusableArtifact": {"duckdbArtifactPath": None}, "currentDeviceArtifacts": []}

    monkeypatch.setattr(auditor_service, "project_reality_status", _project_reality_status)
    monkeypatch.setattr(auditor_service, "get_hydration_status", _get_hydration_status)
    monkeypatch.setattr(auditor_service, "_duckdb_has_populated_rows", lambda path: True)
    monkeypatch.setattr(
        auditor_service,
        "evaluate_integrity_gate",
        lambda root, manifest, action: {"blocked": False, "reasons": []},
    )

    result = asyncio.run(
        auditor_service.build_auditor_statuses(
            project,
            tasks=[{"_id": "task-1", "title": "Existing Task", "status": "done"}],
            active_sessions=[],
        )
    )

    assert result["session"]["status"] == "blocked"
    assert "1 running-agent session status alias row(s) detected." in result["session"]["blockers"]
    assert "1 running-agent session role alias row(s) detected." in result["session"]["blockers"]
    assert result["ontology"]["status"] == "blocked"
    assert "Active ontology artifact pointer drift detected: active_ontology_pointer_out_of_date." in result["ontology"]["blockers"]
    assert result["planner"]["status"] == "blocked"
    assert "1 agent secret policy role alias row(s) detected." in result["planner"]["blockers"]
    assert "1 role config alias declaration(s) detected." in result["planner"]["blockers"]
    assert result["integrity"]["status"] == "blocked"
    assert "Artifacts exist on disk without lineage records: artifacts/untracked.md." in result["integrity"]["blockers"]
    assert "Artifact lineage points to missing files: artifacts/missing.md." in result["integrity"]["blockers"]
