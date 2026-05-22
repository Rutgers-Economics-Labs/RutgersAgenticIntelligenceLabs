"""Tests for _certify_session_result_if_present in session_lifecycle.

Exercises the promotion-gating logic:
- Absent session_result.json is non-blocking for candidate research roles
- Absent session_result.json blocks promotion (artifact) roles
- Valid session_result.json is certified OK and records session_result_certified=True
- Invalid session_result.json blocks promotion roles only
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.runners.session_lifecycle import _certify_session_result_if_present
from app.services import session_files as _sf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session(role: str = "research") -> dict:
    return {"role": role, "_id": "sess_cert_001"}


def _good_result_payload(session_id: str = "sess_cert_001") -> dict:
    return {
        "session_id": session_id,
        "status": "completed",
        "summary": "All done.",
        "task_type": "analysis",
        "runner_name": "codex_cli",
        "files_changed": ["topics/analysis.md"],
        "duration_seconds": 42.0,
    }


def _setup_session_root(tmp_path: Path, session_id: str) -> Path:
    """Create a minimal session root with empty state.json."""
    session_root = tmp_path / "sessions" / session_id
    session_root.mkdir(parents=True)
    (session_root / "state.json").write_text("{}", encoding="utf-8")
    return session_root


# ---------------------------------------------------------------------------
# Absent session_result.json
# ---------------------------------------------------------------------------

def test_absent_result_non_blocking_for_research_role(tmp_path):
    session_root = _setup_session_root(tmp_path, "s1")
    session = _session(role="research")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id="s1",
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    # No blockers should be added and review_status unchanged
    assert not summary.get("blockers")
    state = _sf.read_state(session_root)
    assert state.get("review_status") != "needs_changes"


def test_absent_result_adds_blocker_for_artifact_role(tmp_path):
    session_root = _setup_session_root(tmp_path, "s2")
    session = _session(role="artifact")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id="s2",
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    assert state.get("review_status") == "needs_changes"
    blockers = summary.get("blockers") or []
    assert any("session_result.json" in b for b in blockers)


def test_absent_result_no_blocker_for_artifact_if_failed(tmp_path):
    """Artifact session that failed shouldn't be penalised for missing session_result."""
    session_root = _setup_session_root(tmp_path, "s3")
    session = _session(role="artifact")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id="s3",
        session=session,
        terminal_status="failed",
        review_status="needs_changes",
        summary=summary,
        resolved_task_id=None,
    )

    # failed sessions: promotion blocker for absent file is not added
    assert not any("session_result.json" in b for b in (summary.get("blockers") or []))


# ---------------------------------------------------------------------------
# Valid session_result.json present
# ---------------------------------------------------------------------------

def test_valid_result_is_certified_ok(tmp_path):
    session_id = "s4"
    session_root = _setup_session_root(tmp_path, session_id)
    result_path = session_root / "session_result.json"
    result_path.write_text(json.dumps(_good_result_payload(session_id)), encoding="utf-8")

    session = _session(role="research")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id=session_id,
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    assert state.get("session_result_certified") is True
    assert not summary.get("blockers")


def test_valid_result_in_workspace_subdir_is_found(tmp_path):
    """Runner may write session_result.json inside workspace/research_plan/sessions/<id>/."""
    session_id = "s5"
    session_root = _setup_session_root(tmp_path, session_id)
    workspace_root = tmp_path / "workspace"
    nested_dir = workspace_root / "research_plan" / "sessions" / session_id
    nested_dir.mkdir(parents=True)
    (nested_dir / "session_result.json").write_text(
        json.dumps(_good_result_payload(session_id)), encoding="utf-8"
    )

    session = _session(role="research")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=workspace_root,
        session_root=session_root,
        convex_session_id=session_id,
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    assert state.get("session_result_certified") is True


# ---------------------------------------------------------------------------
# Invalid session_result.json present
# ---------------------------------------------------------------------------

def test_invalid_result_blocks_artifact_role(tmp_path):
    session_id = "s6"
    session_root = _setup_session_root(tmp_path, session_id)
    result_path = session_root / "session_result.json"
    # Missing required fields — will fail schema validation
    result_path.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")

    session = _session(role="artifact")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id=session_id,
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    assert state.get("session_result_certified") is False
    assert state.get("review_status") == "needs_changes"
    blockers = summary.get("blockers") or []
    assert any("certification" in b for b in blockers)


def test_invalid_result_does_not_block_research_role(tmp_path):
    session_id = "s7"
    session_root = _setup_session_root(tmp_path, session_id)
    result_path = session_root / "session_result.json"
    result_path.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")

    session = _session(role="research")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id=session_id,
        session=session,
        terminal_status="completed",
        review_status="review",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    assert state.get("session_result_certified") is False
    # research role: issues recorded but review_status NOT downgraded
    assert state.get("review_status") != "needs_changes"


def test_certify_not_run_for_non_terminal_status(tmp_path):
    session_id = "s8"
    session_root = _setup_session_root(tmp_path, session_id)
    result_path = session_root / "session_result.json"
    result_path.write_text(json.dumps(_good_result_payload(session_id)), encoding="utf-8")

    session = _session(role="research")
    summary: dict = {}

    _certify_session_result_if_present(
        project_root=tmp_path,
        workspace_root=None,
        session_root=session_root,
        convex_session_id=session_id,
        session=session,
        terminal_status="running",  # not terminal
        review_status="pending",
        summary=summary,
        resolved_task_id=None,
    )

    state = _sf.read_state(session_root)
    # Should not touch state
    assert "session_result_certified" not in state
