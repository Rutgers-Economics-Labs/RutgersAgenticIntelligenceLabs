"""Tests for WorkOrder generation shim (Phase 2 of runner-protocol spec).

Covers _derive_work_order_from_task_payload, _write_work_order, and
_load_work_order_for_session as unit-level tests without requiring a live
project or database.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.runners.base import TaskPayload
from app.runners.contracts import Capability, TaskType, WorkOrder
from app.runners.session_lifecycle import (
    _ROLE_TO_CAPABILITIES,
    _ROLE_TO_TASK_TYPE,
    _derive_work_order_from_task_payload,
    _load_work_order_for_session,
    _write_work_order,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(role: str = "research", allowed_paths: list[str] | None = None) -> TaskPayload:
    return TaskPayload(
        project_slug="test-project",
        role=role,
        task_id="task_001",
        repo_url="https://github.com/test/repo",
        branch="main",
        local_repo_path="/tmp/workspace",
        task_description="Test task description",
        allowed_paths=allowed_paths or ["research_plan", "artifacts"],
        allowed_secrets={},
        acceptance_criteria=[],
        project_context="",
        session_root="/tmp/session",
    )


# ---------------------------------------------------------------------------
# _derive_work_order_from_task_payload
# ---------------------------------------------------------------------------

def test_derive_maps_known_roles_to_task_types():
    """Every role in the mapping table must produce a valid, routable TaskType."""
    for role, expected_type in _ROLE_TO_TASK_TYPE.items():
        payload = _make_payload(role=role)
        wo = _derive_work_order_from_task_payload(payload, session_id="sess_001", runner_name="codex_cli")
        assert wo.task_type == expected_type, f"Role {role!r} produced wrong task_type"


def test_derive_unknown_role_falls_back_to_analysis():
    payload = _make_payload(role="unknown_custom_role")
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_002", runner_name="codex_cli")
    assert wo.task_type == TaskType.ANALYSIS


def test_derive_capabilities_non_empty_for_all_known_roles():
    for role in _ROLE_TO_CAPABILITIES:
        payload = _make_payload(role=role)
        wo = _derive_work_order_from_task_payload(payload, session_id="sess_003", runner_name="codex_cli")
        assert wo.capabilities_required, f"Role {role!r} produced empty capabilities"


def test_derive_preserves_safe_allowed_paths():
    payload = _make_payload(allowed_paths=["topics/data/", "research_plan/state/"])
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_004", runner_name="codex_cli")
    assert "topics/data/" in wo.allowed_paths
    assert "research_plan/state/" in wo.allowed_paths


def test_derive_strips_absolute_paths():
    """Absolute paths must be stripped so WorkOrder validator doesn't reject them."""
    payload = _make_payload(allowed_paths=["/etc/passwd", "research_plan"])
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_005", runner_name="codex_cli")
    # /etc/passwd → stripped → empty; only research_plan survives
    assert "research_plan" in wo.allowed_paths
    assert not any(p.startswith("/") for p in wo.allowed_paths)


def test_derive_strips_dotdot_paths():
    payload = _make_payload(allowed_paths=["../escape", "topics"])
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_006", runner_name="codex_cli")
    assert not any(".." in p for p in wo.allowed_paths)


def test_derive_falls_back_to_default_paths_when_all_paths_invalid():
    payload = _make_payload(allowed_paths=["/absolute", "../escape"])
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_007", runner_name="codex_cli")
    assert wo.allowed_paths  # must not be empty


def test_derive_sets_session_result_json_as_required_output():
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_008", runner_name="codex_cli")
    assert "session_result_json" in wo.outputs_required


def test_derive_work_order_id_includes_session_id():
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="my_session_123", runner_name="codex_cli")
    assert "my_session_123" in wo.work_order_id


def test_derive_validates_as_work_order():
    """The derived object must be a valid WorkOrder (schema holds)."""
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_009", runner_name="codex_cli")
    assert isinstance(wo, WorkOrder)


# ---------------------------------------------------------------------------
# _write_work_order / _load_work_order_for_session
# ---------------------------------------------------------------------------

def test_write_then_load_round_trips(tmp_path: Path):
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_rt_001", runner_name="codex_cli")
    _write_work_order(tmp_path, wo)

    loaded = _load_work_order_for_session(tmp_path, "sess_rt_001")
    assert loaded is not None
    assert loaded.work_order_id == wo.work_order_id
    assert loaded.task_type == wo.task_type
    assert loaded.project_slug == wo.project_slug


def test_write_creates_intermediate_dirs(tmp_path: Path):
    deep_root = tmp_path / "a" / "b" / "c"
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_deep", runner_name="codex_cli")
    _write_work_order(deep_root, wo)  # should not raise even though dir doesn't exist yet
    assert (deep_root / "research_plan" / "work_orders" / f"{wo.work_order_id}.json").is_file()


def test_load_returns_none_when_missing(tmp_path: Path):
    result = _load_work_order_for_session(tmp_path, "nonexistent_session")
    assert result is None


def test_load_returns_none_on_invalid_json(tmp_path: Path):
    wo_dir = tmp_path / "research_plan" / "work_orders"
    wo_dir.mkdir(parents=True)
    (wo_dir / "wo_bad_sess.json").write_text("{not valid json", encoding="utf-8")
    result = _load_work_order_for_session(tmp_path, "bad_sess")
    assert result is None


def test_write_silently_succeeds_on_read_only_path(tmp_path: Path):
    """_write_work_order must not raise even when the directory is unwritable."""
    import os
    ro_dir = tmp_path / "readonly"
    ro_dir.mkdir()
    os.chmod(ro_dir, 0o444)
    payload = _make_payload()
    wo = _derive_work_order_from_task_payload(payload, session_id="sess_ro", runner_name="codex_cli")
    # Should NOT raise
    try:
        _write_work_order(ro_dir, wo)
    finally:
        os.chmod(ro_dir, 0o755)
