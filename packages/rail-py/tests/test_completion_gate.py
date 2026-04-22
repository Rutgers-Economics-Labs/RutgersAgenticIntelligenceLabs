"""
Tests for WO-F8.4 — Verification enforcement wiring (completion gates).

Covers:
  - VerificationFailure.as_dict()
  - VerificationSummary.failures and as_task_event_payload()
  - PlannerCompletionGate.check() — all three sub-checks
  - RunnerCompletionGate.check() — all defined roles
  - RunnerCompletionGate.resolve_transition()
  - ROLE_REQUIRED_HOOKS covers expected roles
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rail.completion_gate import (
    ROLE_REQUIRED_HOOKS,
    PlannerCompletionGate,
    RunnerCompletionGate,
    VerificationFailure,
    VerificationSummary,
)
from rail.verification import CheckResult, VerificationResult


# ---------------------------------------------------------------------------
# VerificationFailure
# ---------------------------------------------------------------------------

class TestVerificationFailure:
    def test_as_dict(self):
        vf = VerificationFailure(hook="config_verification", check="parse_succeeds", message="bad YAML")
        d = vf.as_dict()
        assert d == {"hook": "config_verification", "check": "parse_succeeds", "message": "bad YAML"}


# ---------------------------------------------------------------------------
# VerificationSummary
# ---------------------------------------------------------------------------

class TestVerificationSummary:
    def _make_summary(self, passed: bool) -> VerificationSummary:
        checks = [
            CheckResult("field_version", True),
            CheckResult("field_project", False, "missing"),
        ]
        result = VerificationResult("config_verification", passed, checks)
        return VerificationSummary(role="planner", passed=passed, results=[result])

    def test_failures_empty_when_all_pass(self):
        checks = [CheckResult("a", True), CheckResult("b", True)]
        result = VerificationResult("hook", True, checks)
        summary = VerificationSummary(role="planner", passed=True, results=[result])
        assert summary.failures == []

    def test_failures_populated_when_some_fail(self):
        summary = self._make_summary(False)
        assert len(summary.failures) == 1
        assert summary.failures[0].hook == "config_verification"
        assert summary.failures[0].check == "field_project"
        assert summary.failures[0].message == "missing"

    def test_as_task_event_payload_structure(self):
        summary = self._make_summary(False)
        payload = summary.as_task_event_payload()
        assert payload["role"] == "planner"
        assert payload["passed"] is False
        assert len(payload["failures"]) == 1
        assert isinstance(payload["hook_results"], list)
        assert payload["hook_results"][0]["hook"] == "config_verification"

    def test_as_task_event_payload_passed(self):
        summary = VerificationSummary(role="research", passed=True)
        payload = summary.as_task_event_payload()
        assert payload["passed"] is True
        assert payload["failures"] == []
        assert payload["hook_results"] == []

    def test_payload_failures_are_dicts(self):
        summary = self._make_summary(False)
        payload = summary.as_task_event_payload()
        for f in payload["failures"]:
            assert "hook" in f and "check" in f and "message" in f


# ---------------------------------------------------------------------------
# PlannerCompletionGate
# ---------------------------------------------------------------------------

class TestPlannerCompletionGate:
    gate = PlannerCompletionGate()

    def test_all_pass_when_files_present(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan\nContent here.")
        (plan_root / "task_board.md").write_text("# Board\nRows here.")

        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "db_task_status_current": True,
        })
        assert summary.passed, summary.failures
        assert summary.role == "planner"

    def test_fails_when_plan_file_missing(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "task_board.md").write_text("# Board")

        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
        })
        assert not summary.passed
        assert any(r.hook == "planner_plan_file" and not r.passed for r in summary.results)

    def test_fails_when_task_board_missing(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan")

        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
        })
        assert not summary.passed
        assert any(r.hook == "planner_task_board" and not r.passed for r in summary.results)

    def test_fails_when_plan_file_empty(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_bytes(b"")
        (plan_root / "task_board.md").write_text("# Board")

        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
        })
        assert not summary.passed

    def test_fails_when_db_status_not_current(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan")
        (plan_root / "task_board.md").write_text("# Board")

        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "db_task_status_current": False,
        })
        assert not summary.passed
        assert any(r.hook == "planner_db_state" and not r.passed for r in summary.results)

    def test_context_overrides_take_priority(self, tmp_path):
        # Even without files on disk, explicit True context keys pass
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        # No files written
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "plan_file_written": True,
            "task_board_written": True,
            "db_task_status_current": True,
        })
        assert summary.passed, summary.failures

    def test_default_plan_root(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("content")
        (plan_root / "task_board.md").write_text("content")
        summary = self.gate.check({"repo_path": str(tmp_path)})
        # result depends on file presence; no KeyError
        assert isinstance(summary.passed, bool)

    def test_always_returns_three_results(self, tmp_path):
        summary = self.gate.check({"repo_path": str(tmp_path)})
        assert len(summary.results) == 3

    def test_payload_role_is_planner(self, tmp_path):
        summary = self.gate.check({"repo_path": str(tmp_path)})
        payload = summary.as_task_event_payload()
        assert payload["role"] == "planner"


# ---------------------------------------------------------------------------
# RunnerCompletionGate
# ---------------------------------------------------------------------------

class TestRunnerCompletionGate:
    gate = RunnerCompletionGate()

    # --- resolve_transition ---

    def test_resolve_transition_passed(self):
        summary = VerificationSummary(role="research", passed=True)
        status, event = self.gate.resolve_transition(summary)
        assert status == "done"
        assert event == "verification_passed"

    def test_resolve_transition_failed(self):
        summary = VerificationSummary(role="research", passed=False)
        status, event = self.gate.resolve_transition(summary)
        assert status == "blocked"
        assert event == "verification_failed"

    # --- role: research ---

    def test_research_role_passes_with_valid_paths(self):
        summary = self.gate.check("research", {
            "modified_paths": ["research_plan/notes.md"],
            "allowed_write_roots": ["research_plan"],
        })
        assert summary.passed, summary.failures
        assert summary.role == "research"

    def test_research_role_fails_with_bad_paths(self):
        summary = self.gate.check("research", {
            "modified_paths": ["src/core.py"],
            "allowed_write_roots": ["research_plan"],
        })
        assert not summary.passed

    # --- role: data ---

    def test_data_role_runs_three_hooks(self):
        summary = self.gate.check("data", {
            "yaml_valid": True,
            "dry_run_passed": True,
            "modified_paths": [],
        })
        assert len(summary.results) == 3

    def test_data_role_fails_when_dry_run_fails(self):
        summary = self.gate.check("data", {
            "yaml_valid": True,
            "dry_run_passed": False,
            "modified_paths": [],
        })
        assert not summary.passed

    # --- role: coding ---

    def test_coding_role_requires_outputs(self, tmp_path):
        output = tmp_path / "result.csv"
        output.write_bytes(b"data")
        summary = self.gate.check("coding", {
            "execution_succeeded": True,
            "expected_output_paths": [str(output)],
            "modified_paths": [],
            "allowed_write_roots": [],
        })
        assert summary.passed, summary.failures

    def test_coding_role_fails_without_outputs(self):
        summary = self.gate.check("coding", {
            "execution_succeeded": True,
            "modified_paths": [],
        })
        assert not summary.passed

    # --- role: artifact ---

    def test_artifact_role_passes(self, tmp_path):
        artifact = tmp_path / "report.md"
        artifact.write_text("content")
        summary = self.gate.check("artifact", {
            "artifact_paths": [str(artifact)],
            "manifest_updated": True,
            "modified_paths": [],
        })
        assert summary.passed, summary.failures

    # --- role: health ---

    def test_health_role_passes(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("x")
        log = tmp_path / "cleanup.log"
        log.write_text("x")
        summary = self.gate.check("health", {
            "verification_report_path": str(report),
            "cleanup_log_path": str(log),
            "skill_review_recorded": True,
            "modified_paths": [],
        })
        assert summary.passed, summary.failures

    # --- role: planner ---

    def test_planner_role_runs_config_hook(self, tmp_path):
        import textwrap
        yaml_file = tmp_path / "rail.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            version: 1
            project: {name: X, slug: x}
            paths: {ontology_root: .ontology, topics_root: topics}
            hydration: {ontology_file: .ontology/o.yaml, sources_dir: .ontology/sources, pipelines_dir: .ontology/pipelines}
            agents: {roles_dir: agents}
        """))
        summary = self.gate.check("planner", {
            "file_path": str(yaml_file),
            "file_type": "rail.yaml",
        })
        assert summary.passed, summary.failures

    # --- unknown role falls back to PathPolicyVerificationHook ---

    def test_unknown_role_falls_back_to_path_policy(self):
        summary = self.gate.check("unknown_role", {
            "modified_paths": [],
            "allowed_write_roots": ["artifacts"],
        })
        assert summary.passed
        assert len(summary.results) == 1


# ---------------------------------------------------------------------------
# ROLE_REQUIRED_HOOKS coverage
# ---------------------------------------------------------------------------

class TestRoleRequiredHooksMapping:
    def test_all_expected_roles_defined(self):
        expected = {"planner", "research", "data", "coding", "artifact", "health"}
        assert expected == set(ROLE_REQUIRED_HOOKS.keys())

    def test_each_role_has_at_least_one_hook(self):
        for role, hooks in ROLE_REQUIRED_HOOKS.items():
            assert len(hooks) >= 1, f"role {role!r} has no hooks"
