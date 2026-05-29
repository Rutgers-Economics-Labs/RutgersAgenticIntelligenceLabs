"""Phase 2 — Structured I/O tests.

Covers:
  1. WorkOrder generation from legacy planner dispatch parameters.
  2. WorkOrder persistence to disk (workspace + audit trail).
  3. SessionResult enforcer: find + validate session_result.json.
  4. Prompt includes work order + session result instructions.
  5. TaskPayload carries the new Phase 2 fields.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.runners.base import TaskPayload
from app.runners.contracts import (
    Capability,
    SessionStatus,
    TaskType,
    WorkOrder,
)
from app.runners.session_result_enforcer import enforce_session_result
from app.runners.work_order_generator import generate_work_order, write_work_order


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_session_result(session_id: str = "sess_001", wo_id: str = "wo_abc") -> dict:
    return {
        "session_id": session_id,
        "work_order_id": wo_id,
        "status": "completed",
        "summary": "Fetched NJ unemployment data.",
        "task_type": "data_ingestion",
        "runner_name": "claude_code",
    }


def _write_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. WorkOrder generation
# ---------------------------------------------------------------------------

class TestWorkOrderGeneration:
    def test_generates_valid_work_order_for_research_role(self):
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            task=None,
            allowed_paths=["research_plan/", "topics/data/"],
            runner_name="claude_code",
        )
        assert isinstance(wo, WorkOrder)
        assert wo.project_slug == "nj-housing"
        assert wo.task_type == TaskType.ANALYSIS
        assert wo.runner_preferred == "claude_code"
        assert Capability.EXECUTE_PYTHON in wo.capabilities_required

    def test_generates_valid_work_order_for_data_role(self):
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["topics/data/"],
            runner_name=None,
        )
        assert wo.task_type == TaskType.DATA_INGESTION
        assert Capability.FETCH_REMOTE_DATA in wo.capabilities_required

    def test_generates_valid_work_order_for_artifact_role(self):
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="artifact",
            task_id=None,
            task=None,
            allowed_paths=["artifacts/"],
            runner_name=None,
        )
        assert wo.task_type == TaskType.ARTIFACT_WRITING
        assert Capability.WRITE_LONG_ARTIFACTS in wo.capabilities_required

    def test_task_metadata_overrides_role_default(self):
        """Explicit taskType on the task record overrides role-based default."""
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            task={"taskType": "source_discovery"},
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        assert wo.task_type == TaskType.SOURCE_DISCOVERY

    def test_work_order_id_is_stable_across_calls(self):
        """Same project + task_id → same work_order_id (deterministic hash)."""
        kwargs = dict(
            session_id="sess_xyz",
            project_slug="nj-housing",
            role="data",
            task_id="task_99",
            task=None,
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        wo1 = generate_work_order(**kwargs)
        wo2 = generate_work_order(**kwargs)
        assert wo1.work_order_id == wo2.work_order_id

    def test_sanitises_absolute_allowed_paths(self):
        """Absolute paths are stripped so WorkOrder validator doesn't reject them."""
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["/absolute/path", "valid/relative/"],
            runner_name=None,
        )
        for path in wo.allowed_paths:
            assert not path.startswith("/"), f"absolute path leaked: {path}"

    def test_falls_back_to_research_plan_when_no_safe_paths(self):
        """If all allowed_paths are absolute, fall back to research_plan/."""
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["/etc/passwd"],
            runner_name=None,
        )
        assert wo.allowed_paths == ["research_plan/"]

    def test_unknown_role_gets_data_ingestion_default(self):
        wo = generate_work_order(
            session_id="sess_abc",
            project_slug="nj-housing",
            role="mystery_role",
            task_id=None,
            task=None,
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        assert wo.task_type == TaskType.DATA_INGESTION


# ---------------------------------------------------------------------------
# 2. WorkOrder persistence
# ---------------------------------------------------------------------------

class TestWorkOrderPersistence:
    def test_writes_work_order_to_workspace(self, tmp_path: Path):
        wo = generate_work_order(
            session_id="sess_001",
            project_slug="test-proj",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        wo_path = write_work_order(wo, workspace_root=tmp_path)

        assert wo_path.is_file()
        raw = json.loads(wo_path.read_text(encoding="utf-8"))
        assert raw["work_order_id"] == wo.work_order_id
        assert raw["project_slug"] == "test-proj"

    def test_writes_audit_copy_to_project_root(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        project = tmp_path / "project"
        workspace.mkdir()
        project.mkdir()

        wo = generate_work_order(
            session_id="sess_001",
            project_slug="test-proj",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        write_work_order(wo, workspace_root=workspace, project_root=project)

        workspace_copy = workspace / "research_plan" / "work_orders" / f"{wo.work_order_id}.json"
        project_copy = project / "research_plan" / "work_orders" / f"{wo.work_order_id}.json"

        assert workspace_copy.is_file()
        assert project_copy.is_file()
        # Both copies identical
        assert workspace_copy.read_text() == project_copy.read_text()

    def test_skips_audit_copy_when_roots_are_same(self, tmp_path: Path):
        wo = generate_work_order(
            session_id="sess_001",
            project_slug="test-proj",
            role="data",
            task_id=None,
            task=None,
            allowed_paths=["research_plan/"],
            runner_name=None,
        )
        # Same root for workspace and project: no error, just one copy
        write_work_order(wo, workspace_root=tmp_path, project_root=tmp_path)
        wo_dir = tmp_path / "research_plan" / "work_orders"
        files = list(wo_dir.iterdir())
        assert len(files) == 1


# ---------------------------------------------------------------------------
# 3. SessionResult enforcer
# ---------------------------------------------------------------------------

class TestSessionResultEnforcer:
    def test_returns_valid_when_session_result_present(self, tmp_path: Path):
        session_id = "sess_test_001"
        role = "research"
        result_path = tmp_path / "research_plan" / "sessions" / role / session_id / "session_result.json"
        _write_result(result_path, _minimal_session_result(session_id))

        outcome = enforce_session_result(tmp_path, role=role, session_id=session_id)

        assert outcome.found
        assert outcome.valid
        assert outcome.result is not None
        assert outcome.result.status == SessionStatus.COMPLETED
        assert not outcome.issues

    def test_accepts_legacy_session_result_payload(self, tmp_path: Path):
        session_id = "sess_legacy_001"
        role = "health"
        result_path = tmp_path / "research_plan" / "sessions" / role / session_id / "session_result.json"
        _write_result(
            result_path,
            {
                "work_order_id": f"wo_{session_id}",
                "agent_session_id": session_id,
                "status": "completed",
                "produced_domain_progress": False,
                "summary": "Reconciled stale control-plane state.",
                "artifacts_updated": ["research_plan/state/verification_runs.json"],
                "blockers": [],
                "generated_at": "2026-05-24T23:59:00Z",
            },
        )

        outcome = enforce_session_result(tmp_path, role=role, session_id=session_id)

        assert outcome.found
        assert outcome.valid
        assert outcome.result is not None
        assert outcome.result.session_id == session_id
        assert outcome.result.task_type == TaskType.HEALTH_REPAIR
        assert "research_plan/state/verification_runs.json" in outcome.result.files_changed

    def test_returns_not_found_when_file_missing(self, tmp_path: Path):
        outcome = enforce_session_result(tmp_path, role="research", session_id="sess_missing")

        assert not outcome.found
        assert not outcome.valid
        assert any("not found" in issue for issue in outcome.issues)

    def test_returns_invalid_on_bad_json(self, tmp_path: Path):
        session_id = "sess_bad_json"
        role = "artifact"
        result_path = tmp_path / "research_plan" / "sessions" / role / session_id / "session_result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text("{not json", encoding="utf-8")

        outcome = enforce_session_result(tmp_path, role=role, session_id=session_id)

        assert outcome.found
        assert not outcome.valid
        assert any("not valid JSON" in issue for issue in outcome.issues)

    def test_returns_invalid_on_schema_violation(self, tmp_path: Path):
        session_id = "sess_bad_schema"
        role = "data"
        result_path = tmp_path / "research_plan" / "sessions" / role / session_id / "session_result.json"
        _write_result(result_path, {"session_id": session_id})  # missing required fields

        outcome = enforce_session_result(tmp_path, role=role, session_id=session_id)

        assert outcome.found
        assert not outcome.valid
        assert len(outcome.issues) >= 1  # at least status/summary/task_type missing

    def test_finds_roleless_fallback_path(self, tmp_path: Path):
        """Runners that write to the role-less path are still found."""
        session_id = "sess_roleless"
        result_path = tmp_path / "research_plan" / "sessions" / session_id / "session_result.json"
        _write_result(result_path, _minimal_session_result(session_id))

        outcome = enforce_session_result(tmp_path, role="research", session_id=session_id)

        assert outcome.found
        assert outcome.valid

    def test_finds_root_level_fallback(self, tmp_path: Path):
        """Legacy runners that write session_result.json at workspace root."""
        session_id = "sess_root"
        result_path = tmp_path / "session_result.json"
        _write_result(result_path, _minimal_session_result(session_id))

        outcome = enforce_session_result(tmp_path, role="research", session_id=session_id)

        assert outcome.found
        assert outcome.valid


# ---------------------------------------------------------------------------
# 4. Prompt includes Phase 2 instructions
# ---------------------------------------------------------------------------

class TestPhase2PromptInstructions:
    def _make_payload(self, **kwargs) -> TaskPayload:
        defaults = dict(
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            repo_url="",
            branch="main",
            task_description="Analyse unemployment trends.",
        )
        defaults.update(kwargs)
        return TaskPayload(**defaults)

    def test_prompt_includes_work_order_id_when_set(self):
        from app.runners.cli_base import LocalCLIRunner

        class _DummyCLI(LocalCLIRunner):
            runner_name = "dummy"
            command = "dummy_cmd"

        runner = _DummyCLI()
        payload = self._make_payload(
            work_order_id="wo_abc123",
            work_order_path="research_plan/work_orders/wo_abc123.json",
            session_result_path="research_plan/sessions/research/task_001/session_result.json",
        )
        prompt = runner._build_prompt(payload)
        assert "wo_abc123" in prompt
        assert "research_plan/work_orders/wo_abc123.json" in prompt
        assert "session_result.json" in prompt
        assert "RAIL Protocol" in prompt

    def test_prompt_does_not_include_protocol_section_without_work_order(self):
        from app.runners.cli_base import LocalCLIRunner

        class _DummyCLI(LocalCLIRunner):
            runner_name = "dummy"
            command = "dummy_cmd"

        runner = _DummyCLI()
        payload = self._make_payload()  # no work_order_id
        prompt = runner._build_prompt(payload)
        assert "RAIL Protocol" not in prompt


# ---------------------------------------------------------------------------
# 5. TaskPayload carries Phase 2 fields
# ---------------------------------------------------------------------------

class TestTaskPayloadPhase2Fields:
    def test_task_payload_accepts_work_order_fields(self):
        tp = TaskPayload(
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            repo_url="",
            branch="main",
            task_description="...",
            work_order_id="wo_abc",
            work_order_path="/workspace/research_plan/work_orders/wo_abc.json",
            session_result_path="/workspace/research_plan/sessions/research/task_001/session_result.json",
        )
        assert tp.work_order_id == "wo_abc"
        assert tp.work_order_path is not None
        assert tp.session_result_path is not None

    def test_task_payload_defaults_work_order_fields_to_none(self):
        tp = TaskPayload(
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            repo_url="",
            branch="main",
            task_description="...",
        )
        assert tp.work_order_id is None
        assert tp.work_order_path is None
        assert tp.session_result_path is None

    def test_to_dict_includes_work_order_id(self):
        tp = TaskPayload(
            project_slug="nj-housing",
            role="research",
            task_id="task_001",
            repo_url="",
            branch="main",
            task_description="...",
            work_order_id="wo_abc",
        )
        d = tp.to_dict()
        assert d["work_order_id"] == "wo_abc"
