"""Phase 0 contract tests.

Three groups:
  1. WorkOrder schema accepts good payloads, rejects malformed ones.
  2. SessionResult schema accepts good payloads, rejects malformed ones.
  3. RunnerProfile schema accepts good payloads, rejects malformed ones.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.runners.contracts import (
    AdapterType,
    Capability,
    CapabilityState,
    CertificationStatus,
    ExecutionCapabilities,
    RunnerProfile,
    SessionResult,
    SessionStatus,
    SteeringMode,
    TaskType,
    TrustPolicy,
    WorkOrder,
)


# ---------------------------------------------------------------------------
# WorkOrder
# ---------------------------------------------------------------------------

def _minimal_work_order() -> dict:
    return {
        "work_order_id": "wo_test_001",
        "project_slug": "nj-housing",
        "task_type": "data_ingestion",
        "capabilities_required": ["edit_files", "fetch_remote_data"],
        "allowed_paths": [".ontology/", "research_plan/state/", "topics/data/"],
        "created_by": "planner",
    }


def test_work_order_accepts_minimal_payload():
    wo = WorkOrder.model_validate(_minimal_work_order())
    assert wo.work_order_id == "wo_test_001"
    assert wo.task_type == TaskType.DATA_INGESTION
    assert wo.questions_allowed is True
    assert isinstance(wo.trust_policy, TrustPolicy)
    assert wo.trust_policy.output_trust_state == "candidate"


def test_work_order_accepts_full_payload():
    payload = _minimal_work_order() | {
        "phase": "source_discovery",
        "runner_preferred": "claude_code",
        "runner_allowed": ["claude_code", "codex_cli"],
        "inputs": {"brief": "topics/brief.md"},
        "outputs_required": ["claims", "session_result_json"],
        "trust_policy": {
            "output_trust_state": "draft",
            "promotion_requires": ["source_admissibility", "reproducibility_pass"],
        },
        "cost_budget_usd": 5.0,
        "wall_time_budget_minutes": 30,
        "questions_allowed": False,
        "depends_on": ["wo_test_000"],
    }
    wo = WorkOrder.model_validate(payload)
    assert wo.runner_preferred == "claude_code"
    assert wo.trust_policy.output_trust_state == "draft"
    assert wo.cost_budget_usd == 5.0
    assert "wo_test_000" in wo.depends_on


def test_work_order_rejects_absolute_allowed_path():
    bad = _minimal_work_order() | {"allowed_paths": ["/etc/passwd"]}
    with pytest.raises(ValidationError, match="must be a relative path"):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_dotdot_in_allowed_path():
    bad = _minimal_work_order() | {"allowed_paths": ["../escape"]}
    with pytest.raises(ValidationError, match="must be a relative path"):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_empty_capabilities():
    bad = _minimal_work_order() | {"capabilities_required": []}
    with pytest.raises(ValidationError, match="at least one capability"):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_empty_runner_allowed():
    bad = _minimal_work_order() | {"runner_allowed": []}
    with pytest.raises(ValidationError, match="non-empty list"):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_unknown_task_type():
    bad = _minimal_work_order() | {"task_type": "not_a_real_task_type"}
    with pytest.raises(ValidationError):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_unknown_capability():
    bad = _minimal_work_order() | {"capabilities_required": ["fly_to_the_moon"]}
    with pytest.raises(ValidationError):
        WorkOrder.model_validate(bad)


def test_work_order_rejects_extra_fields():
    """extra='forbid' catches schema drift — agents adding fields RAIL
    doesn't know about should fail loudly, not silently lose data."""
    bad = _minimal_work_order() | {"surprise_field": "value"}
    with pytest.raises(ValidationError):
        WorkOrder.model_validate(bad)


# ---------------------------------------------------------------------------
# SessionResult
# ---------------------------------------------------------------------------

def _minimal_session_result() -> dict:
    return {
        "session_id": "sess_test_001",
        "status": "completed",
        "summary": "Hydrated EIA-923 generator panel.",
        "task_type": "data_ingestion",
        "runner_name": "claude_code",
    }


def test_session_result_accepts_minimal_payload():
    result = SessionResult.model_validate(_minimal_session_result())
    assert result.status == SessionStatus.COMPLETED
    assert result.task_type == TaskType.DATA_INGESTION
    assert result.claims == []
    assert result.sources == []
    assert result.datasets == []
    assert result.blockers == []


def test_session_result_accepts_full_payload():
    payload = _minimal_session_result() | {
        "work_order_id": "wo_test_001",
        "files_changed": [
            "topics/data/eia_923_panel.csv",
            "research_plan/state/sources.json",
        ],
        "claims": [
            {
                "claim_id": "claim_001",
                "text": "ISO-NE prices spiked during the Feb 2021 cold snap.",
                "evidence_refs": ["dataset:nyiso_lmp", "source:noaa_temperature"],
                "confidence": 0.75,
            }
        ],
        "sources": [
            {
                "source_id": "eia_923",
                "name": "EIA Form 923",
                "provider": "US Energy Information Administration",
                "access_url": "https://www.eia.gov/electricity/data/eia923/",
                "access_method": "fetched",
                "admissibility": "admissible",
                "materialized_path": "topics/data/raw/eia_923_2024.csv",
            }
        ],
        "datasets": [
            {
                "dataset_id": "ds_eia_panel",
                "file_path": "topics/data/eia_923_panel.csv",
                "source_ids": ["eia_923"],
                "row_count": 12480,
                "schema_summary": "plant_id, fuel_type, year, month, net_generation_mwh",
            }
        ],
        "blockers": [],
        "questions_asked": ["q_2026_001"],
        "verification": {
            "command": "scripts/run-verification.sh",
            "expected_outputs": ["topics/data/eia_923_panel.csv"],
            "claims_to_verify": ["claim_001"],
        },
        "next_recommended_tasks": [
            {
                "task_type": "analysis",
                "reason": "Panel ready; next is regression on price spikes.",
                "capabilities_hint": ["query_duckdb", "execute_python"],
            }
        ],
        "cost_recorded_usd": 0.42,
        "duration_seconds": 187.5,
    }
    result = SessionResult.model_validate(payload)
    assert result.work_order_id == "wo_test_001"
    assert len(result.claims) == 1
    assert result.claims[0].claim_id == "claim_001"
    assert result.verification is not None
    assert result.verification.claims_to_verify == ["claim_001"]


def test_session_result_rejects_unknown_status():
    bad = _minimal_session_result() | {"status": "kinda_done"}
    with pytest.raises(ValidationError):
        SessionResult.model_validate(bad)


def test_session_result_rejects_missing_required_field():
    bad = {k: v for k, v in _minimal_session_result().items() if k != "summary"}
    with pytest.raises(ValidationError):
        SessionResult.model_validate(bad)


def test_session_result_rejects_extra_fields_on_claim():
    bad = _minimal_session_result() | {
        "claims": [
            {
                "claim_id": "claim_001",
                "text": "Test",
                "secret_field": "leaked",
            }
        ]
    }
    with pytest.raises(ValidationError):
        SessionResult.model_validate(bad)


# ---------------------------------------------------------------------------
# RunnerProfile
# ---------------------------------------------------------------------------

def test_runner_profile_accepts_full_payload():
    profile = RunnerProfile.model_validate(
        {
            "name": "claude_code",
            "adapter": "local_cli",
            "default_command": "claude",
            "status": "certified",
            "execution": {
                "mode": "local_cli",
                "supports_streaming": "yes",
                "supports_resume": "configurable",
                "supports_midrun_messages": True,
                "supports_native_approval": False,
                "supports_cancel": True,
                "supports_mcp": "yes",
                "supports_native_questions": "yes",
                "steering_mode": "native_or_relaunch",
            },
            "capabilities": {
                "edit_files": "yes",
                "run_shell": "yes",
                "use_mcp_tools": "yes",
                "execute_python": "yes",
                "handle_large_context": "yes",
                "write_structured_output": "yes",
                "browse_web": "configurable",
                "extract_pdf_tables": "unknown",
            },
            "task_affinity": {
                "data_ingestion": 0.8,
                "analysis": 0.75,
                "artifact_writing": 0.9,
                "health_repair": 0.7,
            },
            "notes": "Best long-context runner; MCP first-class.",
        }
    )
    assert profile.status == CertificationStatus.CERTIFIED
    assert profile.execution.mode == AdapterType.LOCAL_CLI
    assert profile.execution.steering_mode == SteeringMode.NATIVE_OR_RELAUNCH
    assert profile.capabilities[Capability.EDIT_FILES] == CapabilityState.YES
    assert profile.capabilities[Capability.BROWSE_WEB] == CapabilityState.CONFIGURABLE
    assert profile.task_affinity[TaskType.ARTIFACT_WRITING] == 0.9


def test_runner_profile_rejects_out_of_range_task_affinity():
    with pytest.raises(ValidationError, match="out of \\[0, 1\\]"):
        RunnerProfile.model_validate(
            {
                "name": "test_runner",
                "adapter": "local_cli",
                "execution": {"mode": "local_cli", "supports_streaming": True},
                "capabilities": {"edit_files": "yes"},
                "task_affinity": {"analysis": 1.5},
            }
        )


def test_runner_profile_rejects_empty_capabilities():
    with pytest.raises(ValidationError, match="at least one capability state"):
        RunnerProfile.model_validate(
            {
                "name": "test_runner",
                "adapter": "local_cli",
                "execution": {"mode": "local_cli", "supports_streaming": "yes"},
                "capabilities": {},
            }
        )


def test_runner_profile_status_defaults_to_experimental():
    profile = RunnerProfile.model_validate(
        {
            "name": "new_runner",
            "adapter": "local_cli",
            "execution": {"mode": "local_cli", "supports_streaming": "no"},
            "capabilities": {"edit_files": "yes"},
        }
    )
    assert profile.status == CertificationStatus.EXPERIMENTAL


def test_runner_profile_advisory_only_is_a_valid_status():
    profile = RunnerProfile.model_validate(
        {
            "name": "copilot_cli",
            "adapter": "local_cli",
            "default_command": "gh copilot suggest",
            "status": "advisory_only",
            "execution": {
                "mode": "local_cli",
                "supports_streaming": "no",
                "supports_mcp": "no",
                "steering_mode": "unsupported",
            },
            "capabilities": {
                "edit_files": "no",
                "run_shell": "no",
                "write_structured_output": "no",
            },
            "notes": "Suggestion CLI only. Not an autonomous executor.",
        }
    )
    assert profile.status == CertificationStatus.ADVISORY_ONLY
    assert profile.execution.steering_mode == SteeringMode.UNSUPPORTED
