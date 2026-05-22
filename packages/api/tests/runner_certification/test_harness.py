"""Stub-runner certification tests.

A "stub runner" here just writes a session_result.json file the way a real
runner eventually will. The certification harness reads it and reports
pass/fail. In Phase 1+, the same harness is invoked against real CLI
runners.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.runners.contracts import (
    Capability,
    SessionStatus,
    TaskType,
    WorkOrder,
)
from tests.runner_certification.harness import certify_session_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _good_work_order() -> WorkOrder:
    return WorkOrder.model_validate(
        {
            "work_order_id": "wo_stub_001",
            "project_slug": "nj-housing",
            "task_type": "data_ingestion",
            "capabilities_required": ["edit_files", "fetch_remote_data"],
            "allowed_paths": ["topics/data/", "research_plan/state/"],
            "outputs_required": ["sources", "datasets", "session_result_json"],
            "created_by": "planner",
        }
    )


def _good_session_result_for(work_order: WorkOrder) -> dict:
    return {
        "session_id": "sess_stub_001",
        "work_order_id": work_order.work_order_id,
        "status": "completed",
        "summary": "Fetched and shaped FRED unemployment series.",
        "task_type": work_order.task_type.value,
        "runner_name": "stub_runner",
        "files_changed": [
            "topics/data/nj_unemployment.csv",
            "research_plan/state/sources.json",
        ],
        "sources": [
            {
                "source_id": "fred_unrate_nj",
                "name": "FRED — Unemployment Rate in New Jersey",
                "provider": "Federal Reserve Bank of St. Louis",
                "access_url": "https://fred.stlouisfed.org/series/NJUR",
                "access_method": "fetched",
                "admissibility": "admissible",
                "materialized_path": "topics/data/raw/fred_njur.csv",
            }
        ],
        "datasets": [
            {
                "dataset_id": "ds_nj_unemployment",
                "file_path": "topics/data/nj_unemployment.csv",
                "source_ids": ["fred_unrate_nj"],
                "row_count": 168,
                "schema_summary": "date (monthly), unemployment_rate_pct",
            }
        ],
        "duration_seconds": 12.3,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_harness_passes_a_well_formed_session_result(tmp_path: Path):
    wo = _good_work_order()
    result_path = tmp_path / "session_result.json"
    result_path.write_text(json.dumps(_good_session_result_for(wo)), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    assert outcome.passed, f"expected pass, got issues: {outcome.issues}"
    assert outcome.parsed is not None
    assert outcome.parsed.task_type == TaskType.DATA_INGESTION
    assert outcome.parsed.status == SessionStatus.COMPLETED


def test_harness_passes_without_work_order_consistency_check(tmp_path: Path):
    """work_order is optional — schema validation alone is still useful."""
    result_path = tmp_path / "session_result.json"
    payload = _good_session_result_for(_good_work_order())
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = certify_session_result(result_path)  # no work_order

    assert outcome.passed
    assert outcome.parsed is not None


# ---------------------------------------------------------------------------
# Failure modes — file presence, JSON shape, schema validity
# ---------------------------------------------------------------------------

def test_harness_fails_when_file_missing(tmp_path: Path):
    outcome = certify_session_result(tmp_path / "does_not_exist.json")
    assert not outcome.passed
    assert any("not found" in issue for issue in outcome.issues)


def test_harness_fails_on_invalid_json(tmp_path: Path):
    result_path = tmp_path / "session_result.json"
    result_path.write_text("{this is not json", encoding="utf-8")

    outcome = certify_session_result(result_path)

    assert not outcome.passed
    assert any("not valid JSON" in issue for issue in outcome.issues)


def test_harness_fails_on_schema_violations_and_surfaces_all_of_them(tmp_path: Path):
    """We want every issue reported in one pass so authors aren't stuck in
    fix-test-fix cycles."""
    result_path = tmp_path / "session_result.json"
    bad = {
        "session_id": "sess_bad",
        # missing: status, summary, task_type, runner_name
        "extra_unknown_field": "shouldn't be here",
    }
    result_path.write_text(json.dumps(bad), encoding="utf-8")

    outcome = certify_session_result(result_path)

    assert not outcome.passed
    # Multiple distinct issues surfaced
    assert len(outcome.issues) >= 3


# ---------------------------------------------------------------------------
# Failure modes — work order consistency
# ---------------------------------------------------------------------------

def test_harness_fails_when_work_order_id_missing(tmp_path: Path):
    wo = _good_work_order()
    result_path = tmp_path / "session_result.json"
    payload = _good_session_result_for(wo)
    del payload["work_order_id"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    assert not outcome.passed
    assert any("work_order_id is missing" in issue for issue in outcome.issues)


def test_harness_fails_when_work_order_id_mismatch(tmp_path: Path):
    wo = _good_work_order()
    result_path = tmp_path / "session_result.json"
    payload = _good_session_result_for(wo)
    payload["work_order_id"] = "wo_completely_different"
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    assert not outcome.passed
    assert any("work_order_id mismatch" in issue for issue in outcome.issues)


def test_harness_fails_when_task_type_mismatch(tmp_path: Path):
    wo = _good_work_order()
    result_path = tmp_path / "session_result.json"
    payload = _good_session_result_for(wo)
    payload["task_type"] = "analysis"  # WO requested data_ingestion
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    assert not outcome.passed
    assert any("task_type mismatch" in issue for issue in outcome.issues)


def test_harness_fails_when_required_output_absent(tmp_path: Path):
    """Work order requires 'sources' output; session result has none."""
    wo = WorkOrder.model_validate(
        {
            "work_order_id": "wo_stub_002",
            "project_slug": "nj-housing",
            "task_type": "source_discovery",
            "capabilities_required": ["browse_web"],
            "allowed_paths": ["research_plan/state/"],
            "outputs_required": ["sources"],
            "created_by": "planner",
        }
    )
    result_path = tmp_path / "session_result.json"
    payload = {
        "session_id": "sess_stub_002",
        "work_order_id": wo.work_order_id,
        "status": "completed",
        "summary": "Tried to find sources, came back empty.",
        "task_type": wo.task_type.value,
        "runner_name": "stub_runner",
        "sources": [],  # required output not populated
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    assert not outcome.passed
    assert any("requires output 'sources'" in issue for issue in outcome.issues)


def test_harness_tolerates_unknown_output_type_for_forward_compat(tmp_path: Path):
    """If a work order declares an outputs_required value the harness doesn't
    yet know about, that's not a failure — the vocabulary will grow."""
    wo = WorkOrder.model_validate(
        {
            "work_order_id": "wo_stub_003",
            "project_slug": "nj-housing",
            "task_type": "data_ingestion",
            "capabilities_required": ["edit_files"],
            "allowed_paths": ["topics/data/"],
            "outputs_required": ["some_future_output_type"],
            "created_by": "planner",
        }
    )
    result_path = tmp_path / "session_result.json"
    result_path.write_text(json.dumps(_good_session_result_for(wo)), encoding="utf-8")

    outcome = certify_session_result(result_path, work_order=wo)

    # Unknown output types are skipped, not failed.
    assert outcome.passed, f"unexpected issues: {outcome.issues}"
