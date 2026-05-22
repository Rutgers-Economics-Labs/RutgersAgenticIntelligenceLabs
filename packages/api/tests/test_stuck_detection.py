"""Tests for stuck detection / anti-stall mechanics in autopilot_service.

Tests _compute_task_action_hash, _write_stuck_report, and
_detect_and_handle_stuck_tasks without requiring a full project or running
autopilot loop.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.autopilot_service import (
    STUCK_RUN_BUDGET,
    _compute_task_action_hash,
    _detect_and_handle_stuck_tasks,
    _task_stuck_counters,
    _write_stuck_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocked_task(task_id: str = "task_001", blocker: str = "verification_failure") -> dict:
    return {
        "_id": task_id,
        "title": f"Task {task_id}",
        "status": "blocked",
        "agentRole": "research",
        "blockerCategory": blocker,
        "latestRunSummary": "Something failed.",
    }


def _ready_task(task_id: str = "task_002") -> dict:
    return {
        "_id": task_id,
        "title": f"Ready task {task_id}",
        "status": "ready",
        "agentRole": "research",
        "blockerCategory": None,
        "latestRunSummary": "",
    }


# ---------------------------------------------------------------------------
# _compute_task_action_hash
# ---------------------------------------------------------------------------

def test_action_hash_is_stable():
    task = _blocked_task("t1", "audit_failure")
    assert _compute_task_action_hash(task) == _compute_task_action_hash(task)


def test_action_hash_differs_on_status_change():
    task_blocked = _blocked_task("t1", "audit_failure")
    task_done = dict(task_blocked, status="done")
    assert _compute_task_action_hash(task_blocked) != _compute_task_action_hash(task_done)


def test_action_hash_differs_on_blocker_change():
    t1 = _blocked_task("t1", "audit_failure")
    t2 = dict(t1, blockerCategory="publish_failure")
    assert _compute_task_action_hash(t1) != _compute_task_action_hash(t2)


def test_action_hash_same_even_if_run_summary_differs():
    """latestRunSummary varies every run; hash must ignore it."""
    t1 = _blocked_task("t1", "audit_failure")
    t2 = dict(t1, latestRunSummary="completely different message")
    assert _compute_task_action_hash(t1) == _compute_task_action_hash(t2)


# ---------------------------------------------------------------------------
# _write_stuck_report
# ---------------------------------------------------------------------------

def test_write_stuck_report_creates_json(tmp_path: Path):
    task = _blocked_task("task_abc", "verification_failure")
    _write_stuck_report(tmp_path, task, consecutive_count=4)
    report_path = tmp_path / "research_plan" / "stuck_reports" / "task_abc.json"
    assert report_path.is_file()
    data = json.loads(report_path.read_text())
    assert data["task_id"] == "task_abc"
    assert data["consecutive_blocked_runs"] == 4
    assert "recommended_actions" in data


def test_write_stuck_report_does_not_raise_on_bad_path():
    """Must never raise even when the project root doesn't exist."""
    task = _blocked_task("t999")
    _write_stuck_report(Path("/nonexistent/path"), task, consecutive_count=5)


# ---------------------------------------------------------------------------
# _detect_and_handle_stuck_tasks
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_stuck_counters():
    """Each test starts with a clean counter state."""
    _task_stuck_counters.clear()
    yield
    _task_stuck_counters.clear()


def _make_project(tmp_path: Path) -> dict:
    return {"localRepoPath": str(tmp_path), "_id": "proj_test", "slug": "test-project"}


@pytest.mark.asyncio
async def test_no_stuck_tasks_returns_false(tmp_path):
    project = _make_project(tmp_path)
    tasks = [_ready_task("t1"), _ready_task("t2")]
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        result = await _detect_and_handle_stuck_tasks(project, tasks)
    assert result is False
    mock_ps.update_task.assert_not_called()


@pytest.mark.asyncio
async def test_blocked_task_not_flagged_below_budget(tmp_path):
    project = _make_project(tmp_path)
    task = _blocked_task("t1")
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        for _ in range(STUCK_RUN_BUDGET - 1):
            result = await _detect_and_handle_stuck_tasks(project, [task])
    assert result is False
    mock_ps.update_task.assert_not_called()


@pytest.mark.asyncio
async def test_blocked_task_flagged_at_budget(tmp_path):
    project = _make_project(tmp_path)
    task = _blocked_task("t1")
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        for _ in range(STUCK_RUN_BUDGET):
            result = await _detect_and_handle_stuck_tasks(project, [task])
    # On the Nth iteration it should be flagged
    assert result is True
    mock_ps.update_task.assert_called_once()
    call_kwargs = mock_ps.update_task.call_args.kwargs
    assert call_kwargs["blockerCategory"] == "stuck_loop"


@pytest.mark.asyncio
async def test_stuck_report_written_when_task_flagged(tmp_path):
    project = _make_project(tmp_path)
    task = _blocked_task("t_stuck")
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        for _ in range(STUCK_RUN_BUDGET):
            await _detect_and_handle_stuck_tasks(project, [task])
    report_path = tmp_path / "research_plan" / "stuck_reports" / "t_stuck.json"
    assert report_path.is_file()
    data = json.loads(report_path.read_text())
    assert data["blocker_category"] == "verification_failure"


@pytest.mark.asyncio
async def test_counter_resets_after_task_advances(tmp_path):
    """If a task changes status, the counter resets and it is not re-flagged."""
    project = _make_project(tmp_path)
    task = _blocked_task("t2")
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        # Run up to budget - 1
        for _ in range(STUCK_RUN_BUDGET - 1):
            await _detect_and_handle_stuck_tasks(project, [task])
        # Now the task advances to done
        task_done = dict(task, status="done")
        await _detect_and_handle_stuck_tasks(project, [task_done])
        # Then it goes blocked again — counter should restart
        for _ in range(STUCK_RUN_BUDGET - 1):
            await _detect_and_handle_stuck_tasks(project, [task])
        result = await _detect_and_handle_stuck_tasks(project, [task])
    # The task should only be flagged once (on the fresh cycle completing budget)
    assert mock_ps.update_task.call_count == 1


@pytest.mark.asyncio
async def test_different_tasks_tracked_independently(tmp_path):
    project = _make_project(tmp_path)
    task_a = _blocked_task("ta", "audit_failure")
    task_b = _blocked_task("tb", "publish_failure")
    with patch("app.services.autopilot_service.planner_service") as mock_ps:
        mock_ps.update_task = AsyncMock()
        # Run exactly budget times for both
        for _ in range(STUCK_RUN_BUDGET):
            await _detect_and_handle_stuck_tasks(project, [task_a, task_b])
    # Both should be flagged
    assert mock_ps.update_task.call_count == 2
