"""Tests for Milestone 3: Planner/Task Truth — supersession and audit gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Ensure rail-py is importable
RAIL_PY_ROOT = Path(__file__).parents[3] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))


MINIMAL_MANIFEST = """\
version: 1
project:
  name: "Test"
  slug: "test"
  default_branch: "main"
paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"
hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"
agents:
  roles_dir: "agents"
  default_runner: "codex_cli"
  sequential_execution: true
  planner_thread_mode: "project"
  default_planner_role: "planner"
frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
"""


def _write_task(task_root: Path, task_id: str, *, status: str, agent_role: str = "research") -> Path:
    task_root.mkdir(parents=True, exist_ok=True)
    path = task_root / f"{task_id}.md"
    meta = {
        "task_id": task_id,
        "title": f"Task {task_id}",
        "status": status,
        "assigned_role": agent_role,
        "dependencies": [],
        "acceptance_criteria": [],
        "related_files": [],
        "latest_run_summary": "Not started",
    }
    path.write_text(f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n\n## Description\n\nNo description.\n", encoding="utf-8")
    return path


def _write_audit(audit_root: Path, task_id: str, *, review_status: str = "review", session_status: str = "completed", blocked: bool = False) -> None:
    audit_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "session": {
            "taskId": task_id,
            "reviewStatus": review_status,
            "status": session_status,
        },
        "integrity": {"blocked": blocked},
        "currentBlocker": "",
    }
    (audit_root / f"{task_id}-audit.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# superseded status is a recognised task status
# ---------------------------------------------------------------------------

def test_superseded_is_valid_task_status():
    from app.services.planner_service import TASK_STATUSES, _normalize_task_status
    assert "superseded" in TASK_STATUSES
    assert _normalize_task_status("superseded", strict=True) == "superseded"


def test_superseded_clears_approval_state_on_read(tmp_path):
    from app.services.planner_service import _task_to_runtime

    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True)
    path = task_dir / "task-sup.md"
    meta = {
        "task_id": "task-sup",
        "title": "Superseded Task",
        "status": "superseded",
        "assigned_role": "research",
        "approval_state": "pending",
        "blocker_category": "data",
        "superseded_by": "task-new",
        "dependencies": [],
        "acceptance_criteria": [],
        "related_files": [],
        "latest_run_summary": "Not started",
    }
    path.write_text(f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n\n## Description\n\nOld work.\n", encoding="utf-8")

    task = _task_to_runtime(path)

    assert task["status"] == "superseded"
    assert task["approvalState"] is None
    assert task["blockerCategory"] is None
    assert task["supersededBy"] == "task-new"


# ---------------------------------------------------------------------------
# supersede_task()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supersede_task_marks_status_and_records_successor(tmp_path):
    from app.services.planner_service import supersede_task

    task_dir = tmp_path / "research_plan" / "tasks"
    _write_task(task_dir, "task-old", status="running", agent_role="research")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    result = await supersede_task("task-old", superseded_by_id="task-new", project=project)

    assert result is not None
    assert result["status"] == "superseded"
    assert result["supersededBy"] == "task-new"


@pytest.mark.asyncio
async def test_supersede_task_persists_to_disk(tmp_path):
    from app.services.planner_service import supersede_task, _task_to_runtime

    task_dir = tmp_path / "research_plan" / "tasks"
    _write_task(task_dir, "task-old", status="ready")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    await supersede_task("task-old", superseded_by_id="task-replacement", project=project)

    reloaded = _task_to_runtime(task_dir / "task-old.md")
    assert reloaded["status"] == "superseded"
    assert reloaded["supersededBy"] == "task-replacement"


@pytest.mark.asyncio
async def test_supersede_task_returns_none_when_task_missing(tmp_path):
    from app.services.planner_service import supersede_task

    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    result = await supersede_task("nonexistent", superseded_by_id="task-new", project=project)

    assert result is None


# ---------------------------------------------------------------------------
# require_audit_before_advance manifest flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_task_to_done_bypasses_audit_gate_when_flag_disabled(tmp_path):
    from app.services.planner_service import update_task

    task_dir = tmp_path / "research_plan" / "tasks"
    _write_task(task_dir, "task-worker", status="review", agent_role="research")
    manifest_yaml = MINIMAL_MANIFEST + "\nplanner:\n  task_root: research_plan/tasks\n  require_audit_before_advance: false\n"
    (tmp_path / "rail.yaml").write_text(manifest_yaml, encoding="utf-8")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path), "slug": "test"}
    with patch("app.services.autopilot_service.trigger_wake"):
        result = await update_task("task-worker", project=project, status="done")

    assert result is not None
    assert result["status"] == "done"


@pytest.mark.asyncio
async def test_update_task_to_done_requires_audit_when_flag_enabled(tmp_path):
    from app.services.planner_service import update_task

    task_dir = tmp_path / "research_plan" / "tasks"
    _write_task(task_dir, "task-worker", status="review", agent_role="research")
    manifest_yaml = MINIMAL_MANIFEST + "\nplanner:\n  task_root: research_plan/tasks\n  require_audit_before_advance: true\n"
    (tmp_path / "rail.yaml").write_text(manifest_yaml, encoding="utf-8")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path), "slug": "test"}
    with patch("app.services.autopilot_service.trigger_wake"):
        with pytest.raises(ValueError, match="audit"):
            await update_task("task-worker", project=project, status="done")


@pytest.mark.asyncio
async def test_update_task_to_done_passes_when_audit_present(tmp_path):
    from app.services.planner_service import update_task

    task_dir = tmp_path / "research_plan" / "tasks"
    _write_task(task_dir, "task-worker", status="review", agent_role="research")
    _write_audit(tmp_path / "research_plan" / "audits", "task-worker")
    manifest_yaml = MINIMAL_MANIFEST + "\nplanner:\n  task_root: research_plan/tasks\n  require_audit_before_advance: true\n"
    (tmp_path / "rail.yaml").write_text(manifest_yaml, encoding="utf-8")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path), "slug": "test"}
    with patch("app.services.autopilot_service.trigger_wake"):
        result = await update_task("task-worker", project=project, status="done")

    assert result is not None
    assert result["status"] == "done"
