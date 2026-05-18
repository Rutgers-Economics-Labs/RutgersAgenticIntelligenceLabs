"""Tests for session reconciliation: zombie detection and lane availability."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure rail-py is importable
RAIL_PY_ROOT = Path(__file__).parents[3] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.manifest import parse_manifest_content

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


# ---------------------------------------------------------------------------
# check_lane_availability
# ---------------------------------------------------------------------------

def _import_check_lane_availability():
    from app.services.reconciliation_service import check_lane_availability
    return check_lane_availability


def test_lane_available_when_no_active_sessions():
    check_lane_availability = _import_check_lane_availability()
    manifest = parse_manifest_content(MINIMAL_MANIFEST)

    result = check_lane_availability(manifest, active_session_count=0)

    assert result["available"] is True
    assert result["policy"] == "single_active_worker"
    assert result["activeSessionCount"] == 0
    assert result["reason"] is None


def test_lane_blocked_when_one_active_session():
    check_lane_availability = _import_check_lane_availability()
    manifest = parse_manifest_content(MINIMAL_MANIFEST)

    result = check_lane_availability(manifest, active_session_count=1)

    assert result["available"] is False
    assert result["policy"] == "single_active_worker"
    assert result["activeSessionCount"] == 1
    assert result["reason"] is not None
    assert "1 active session" in result["reason"]


def test_lane_blocked_when_multiple_active_sessions():
    check_lane_availability = _import_check_lane_availability()
    manifest = parse_manifest_content(MINIMAL_MANIFEST)

    result = check_lane_availability(manifest, active_session_count=3)

    assert result["available"] is False
    assert result["activeSessionCount"] == 3
    assert "3 active session" in result["reason"]


# ---------------------------------------------------------------------------
# detect_zombie_sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_zombie_sessions_returns_empty_when_no_project_root():
    from app.services.reconciliation_service import detect_zombie_sessions

    project = {"_id": "proj1", "localRepoPath": None}
    result = await detect_zombie_sessions(project)

    assert result == []


@pytest.mark.asyncio
async def test_detect_zombie_sessions_returns_empty_when_no_active_sessions(tmp_path):
    from app.services.reconciliation_service import detect_zombie_sessions

    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    with patch(
        "app.services.reconciliation_service.running_agent_service.list_project_running_agents",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await detect_zombie_sessions(project)

    assert result == []


@pytest.mark.asyncio
async def test_detect_zombie_sessions_skips_already_terminal_sessions(tmp_path):
    from app.services.reconciliation_service import detect_zombie_sessions
    from app.services import session_files

    session_id = "sess-terminal"
    session_root = tmp_path / "research_plan" / "sessions" / "planner" / session_id
    session_root.mkdir(parents=True)
    session_files.write_state(session_root, {"session_id": session_id, "status": "completed"})
    pid_dir = session_root / ".runner"
    pid_dir.mkdir()
    (pid_dir / "pid.txt").write_text("99999\n")

    session = {"_id": session_id, "sessionPath": str(session_root)}
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}

    with patch(
        "app.services.reconciliation_service.running_agent_service.list_project_running_agents",
        new_callable=AsyncMock,
        return_value=[session],
    ):
        result = await detect_zombie_sessions(project)

    # terminal status → not a zombie regardless of PID state
    assert session_id not in result


@pytest.mark.asyncio
async def test_detect_zombie_sessions_finds_dead_pid_running_session(tmp_path):
    from app.services.reconciliation_service import detect_zombie_sessions
    from app.services import session_files

    session_id = "sess-zombie"
    session_root = tmp_path / "research_plan" / "sessions" / "data" / session_id
    session_root.mkdir(parents=True)
    session_files.write_state(session_root, {"session_id": session_id, "status": "running"})
    pid_dir = session_root / ".runner"
    pid_dir.mkdir()
    (pid_dir / "pid.txt").write_text("99999\n")

    session = {"_id": session_id, "sessionPath": str(session_root)}
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}

    with (
        patch(
            "app.services.reconciliation_service.running_agent_service.list_project_running_agents",
            new_callable=AsyncMock,
            return_value=[session],
        ),
        patch(
            "app.services.reconciliation_service.session_lifecycle._process_is_running",
            return_value=False,
        ),
    ):
        result = await detect_zombie_sessions(project)

    assert session_id in result


@pytest.mark.asyncio
async def test_detect_zombie_sessions_ignores_live_pid(tmp_path):
    from app.services.reconciliation_service import detect_zombie_sessions
    from app.services import session_files

    session_id = "sess-alive"
    session_root = tmp_path / "research_plan" / "sessions" / "data" / session_id
    session_root.mkdir(parents=True)
    session_files.write_state(session_root, {"session_id": session_id, "status": "running"})
    pid_dir = session_root / ".runner"
    pid_dir.mkdir()
    (pid_dir / "pid.txt").write_text("12345\n")

    session = {"_id": session_id, "sessionPath": str(session_root)}
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}

    with (
        patch(
            "app.services.reconciliation_service.running_agent_service.list_project_running_agents",
            new_callable=AsyncMock,
            return_value=[session],
        ),
        patch(
            "app.services.reconciliation_service.session_lifecycle._process_is_running",
            return_value=True,
        ),
    ):
        result = await detect_zombie_sessions(project)

    assert session_id not in result
