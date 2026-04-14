"""
Tests for rail.completion_gate — WO-F8.4

Covers:
  - VerificationFailure / VerificationSummary data types
  - ROLE_REQUIRED_HOOKS mapping
  - PlannerCompletionGate.check()
  - RunnerCompletionGate.check()
  - RunnerCompletionGate.resolve_transition()
"""
from __future__ import annotations

import pytest
from pathlib import Path

from rail.completion_gate import (
    VerificationFailure,
    VerificationSummary,
    ROLE_REQUIRED_HOOKS,
    PlannerCompletionGate,
    RunnerCompletionGate,
)
from rail.verification import VerificationResult, CheckResult


# ---------------------------------------------------------------------------
# VerificationFailure
# ---------------------------------------------------------------------------

class TestVerificationFailure:
    def test_as_dict_keys(self):
        vf = VerificationFailure(hook="config_verification", check="field_version", message="missing")
        d = vf.as_dict()
        assert set(d.keys()) == {"hook", "check", "message"}
        assert d["hook"] == "config_verification"
        assert d["check"] == "field_version"
        assert d["message"] == "missing"


# ---------------------------------------------------------------------------
# VerificationSummary
# ---------------------------------------------------------------------------

class TestVerificationSummary:
    def _make_result(self, hook: str, passed: bool, checks: list[CheckResult] | None = None):
        return VerificationResult(hook, passed, checks or [])

    def test_passed_summary_no_failures(self):
        r = self._make_result("h1", True, [CheckResult("ok", True)])
        s = VerificationSummary(role="planner", passed=True, results=[r])
        assert s.failures == []

    def test_failed_summary_has_failures(self):
        r = self._make_result("h1", False, [
            CheckResult("ok", True),
            CheckResult("bad", False, "something wrong"),
        ])
        s = VerificationSummary(role="planner", passed=False, results=[r])
        assert len(s.failures) == 1
        f = s.failures[0]
        assert f.hook == "h1"
        assert f.check == "bad"
        assert f.message == "something wrong"

    def test_as_task_event_payload_structure(self):
        r = self._make_result("h1", True, [CheckResult("ok", True)])
        s = VerificationSummary(role="data", passed=True, results=[r])
        payload = s.as_task_event_payload()
        assert "role" in payload
        assert "passed" in payload
        assert "failures" in payload
        assert "hook_results" in payload
        assert payload["role"] == "data"
        assert payload["passed"] is True
        assert isinstance(payload["failures"], list)
        assert isinstance(payload["hook_results"], list)

    def test_as_task_event_payload_failures_list(self):
        r = self._make_result("hook", False, [
            CheckResult("check_a", False, "bad"),
            CheckResult("check_b", True),
        ])
        s = VerificationSummary(role="research", passed=False, results=[r])
        payload = s.as_task_event_payload()
        assert len(payload["failures"]) == 1
        assert payload["failures"][0]["check"] == "check_a"

    def test_hook_results_in_payload(self):
        r = self._make_result("hook_x", True, [CheckResult("ok", True, "everything fine")])
        s = VerificationSummary(role="coding", passed=True, results=[r])
        payload = s.as_task_event_payload()
        hr = payload["hook_results"][0]
        assert hr["hook"] == "hook_x"
        assert hr["passed"] is True
        assert hr["checks"][0]["name"] == "ok"


# ---------------------------------------------------------------------------
# ROLE_REQUIRED_HOOKS mapping
# ---------------------------------------------------------------------------

class TestRoleRequiredHooks:
    def test_all_expected_roles_present(self):
        expected_roles = {"planner", "research", "data", "coding", "artifact", "health"}
        assert expected_roles.issubset(ROLE_REQUIRED_HOOKS.keys())

    def test_each_role_has_at_least_one_hook(self):
        for role, hooks in ROLE_REQUIRED_HOOKS.items():
            assert len(hooks) >= 1, f"Role {role!r} must have at least one hook"

    def test_hooks_are_hook_instances(self):
        from rail.verification import VerificationHook
        for role, hooks in ROLE_REQUIRED_HOOKS.items():
            for hook in hooks:
                assert isinstance(hook, VerificationHook), (
                    f"Role {role!r} hook {hook!r} is not a VerificationHook"
                )


# ---------------------------------------------------------------------------
# PlannerCompletionGate
# ---------------------------------------------------------------------------

class TestPlannerCompletionGate:
    gate = PlannerCompletionGate()

    def test_passes_when_both_files_exist_and_db_current(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan\n\nSome content")
        (plan_root / "task_board.md").write_text("# Board\n")
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "plan_file_written": True,
            "task_board_written": True,
            "db_task_status_current": True,
        })
        assert summary.passed is True
        assert summary.failures == []

    def test_fails_when_plan_file_missing(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        # no current_plan.md
        (plan_root / "task_board.md").write_text("# Board\n")
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "db_task_status_current": True,
        })
        assert not summary.passed
        failure_checks = [f.check for f in summary.failures]
        assert "plan_file_present" in failure_checks

    def test_fails_when_task_board_missing(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan")
        # no task_board.md
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "db_task_status_current": True,
        })
        assert not summary.passed
        failure_checks = [f.check for f in summary.failures]
        assert "task_board_snapshot_present" in failure_checks

    def test_fails_when_db_not_current(self, tmp_path):
        plan_root = tmp_path / "research_plan"
        plan_root.mkdir()
        (plan_root / "current_plan.md").write_text("# Plan")
        (plan_root / "task_board.md").write_text("# Board")
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_root": "research_plan",
            "plan_file_written": True,
            "task_board_written": True,
            "db_task_status_current": False,
        })
        assert not summary.passed
        failure_checks = [f.check for f in summary.failures]
        assert "db_task_status_current" in failure_checks

    def test_context_overrides_file_check(self, tmp_path):
        """plan_file_written=True in context bypasses the filesystem check."""
        # Don't create research_plan dir at all
        summary = self.gate.check({
            "repo_path": str(tmp_path),
            "plan_file_written": True,
            "task_board_written": True,
            "db_task_status_current": True,
        })
        assert summary.passed

    def test_role_is_planner(self, tmp_path):
        summary = self.gate.check({"repo_path": str(tmp_path), "plan_file_written": True,
                                   "task_board_written": True, "db_task_status_current": True})
        assert summary.role == "planner"


# ---------------------------------------------------------------------------
# RunnerCompletionGate
# ---------------------------------------------------------------------------

class TestRunnerCompletionGate:
    gate = RunnerCompletionGate()

    def test_unknown_role_falls_back_to_path_policy(self):
        """Unknown roles default to PathPolicyVerificationHook."""
        # No modified paths → passes path policy
        summary = self.gate.check("unknown_role", {
            "modified_paths": [],
            "allowed_write_roots": [],
            "denied_paths": [],
        })
        assert summary.role == "unknown_role"
        assert summary.passed is True

    def test_research_role_uses_path_policy(self):
        summary = self.gate.check("research", {
            "modified_paths": ["research_plan/notes.md"],
            "allowed_write_roots": ["research_plan"],
            "denied_paths": [],
        })
        assert summary.passed is True

    def test_research_role_with_disallowed_path_fails(self):
        summary = self.gate.check("research", {
            "modified_paths": ["packages/api/config.py"],
            "allowed_write_roots": ["research_plan"],
            "denied_paths": [],
        })
        assert not summary.passed

    def test_planner_role_uses_config_hook(self, tmp_path):
        import yaml
        config = {
            "version": "1",
            "project": "test",
            "paths": {"data": "data/"},
            "hydration": {},
            "agents": [],
        }
        p = tmp_path / "rail.yaml"
        p.write_text(yaml.dump(config))
        summary = self.gate.check("planner", {
            "file_path": str(p),
            "file_type": "rail.yaml",
        })
        assert summary.role == "planner"

    def test_summary_has_all_results(self, tmp_path):
        # Health role: needs report + cleanup
        report = tmp_path / "report.md"
        report.write_text("# x")
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("done")
        summary = self.gate.check("health", {
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
            "disallowed_write_paths": [],
        })
        assert summary.passed
        assert len(summary.results) >= 1


class TestRunnerCompletionGateResolveTransition:
    gate = RunnerCompletionGate()

    def _summary(self, passed: bool) -> VerificationSummary:
        return VerificationSummary(role="data", passed=passed)

    def test_passed_returns_done_verification_passed(self):
        new_status, event_type = self.gate.resolve_transition(self._summary(passed=True))
        assert new_status == "done"
        assert event_type == "verification_passed"

    def test_failed_returns_blocked_verification_failed(self):
        new_status, event_type = self.gate.resolve_transition(self._summary(passed=False))
        assert new_status == "blocked"
        assert event_type == "verification_failed"

    def test_resolve_transition_return_type(self):
        result = self.gate.resolve_transition(self._summary(passed=True))
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration: gate → resolve_transition pipeline
# ---------------------------------------------------------------------------

class TestGateIntegration:
    """End-to-end: check research role, resolve transition."""

    gate = RunnerCompletionGate()

    def test_passing_research_task_resolves_to_done(self):
        summary = self.gate.check("research", {
            "modified_paths": ["artifacts/report.md"],
            "allowed_write_roots": ["artifacts"],
            "denied_paths": [],
        })
        new_status, event_type = self.gate.resolve_transition(summary)
        assert new_status == "done"
        assert event_type == "verification_passed"

    def test_failing_research_task_resolves_to_blocked(self):
        summary = self.gate.check("research", {
            "modified_paths": ["packages/api/config.py"],  # outside allowed roots
            "allowed_write_roots": ["artifacts"],
            "denied_paths": [],
        })
        assert not summary.passed
        new_status, event_type = self.gate.resolve_transition(summary)
        assert new_status == "blocked"
        assert event_type == "verification_failed"

    def test_payload_is_serializable(self):
        """as_task_event_payload() must produce JSON-serializable output."""
        import json
        summary = self.gate.check("research", {
            "modified_paths": [],
            "allowed_write_roots": ["artifacts"],
            "denied_paths": [],
        })
        payload = summary.as_task_event_payload()
        # Should not raise
        json.dumps(payload)
