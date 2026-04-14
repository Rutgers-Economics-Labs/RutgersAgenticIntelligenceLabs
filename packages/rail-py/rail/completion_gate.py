"""
completion_gate.py — Verification enforcement wiring for planner and runner completion.

This module provides two gates:

  PlannerCompletionGate  — enforced before the planner marks a task done.
                           Checks planner-role completion requirements:
                           plan file updated, task board snapshot written, DB task state current.

  RunnerCompletionGate   — enforced when a worker runner reports completion.
                           Runs role-appropriate deterministic hooks before the
                           task is allowed to transition to `done` in the DB.

Both gates return a VerificationSummary that Convex callers can use to decide
whether to call tasks.transition(..., newStatus="done") or block and surface failures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rail.verification import (
    ArtifactVerificationHook,
    ConfigVerificationHook,
    ExecutionVerificationHook,
    HealthVerificationHook,
    HydrationVerificationHook,
    PathPolicyVerificationHook,
    VerificationHook,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Normalized failure surface
# ---------------------------------------------------------------------------

@dataclass
class VerificationFailure:
    """Normalized representation of a single verification check failure."""

    hook: str
    check: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"hook": self.hook, "check": self.check, "message": self.message}


@dataclass
class VerificationSummary:
    """Aggregated result across all hooks run for a completion gate."""

    role: str
    passed: bool
    results: list[VerificationResult] = field(default_factory=list)

    @property
    def failures(self) -> list[VerificationFailure]:
        out: list[VerificationFailure] = []
        for r in self.results:
            for c in r.failures:
                out.append(VerificationFailure(hook=r.hook, check=c.name, message=c.message))
        return out

    def as_task_event_payload(self) -> dict[str, Any]:
        """Return a dict suitable for appending as a taskEvents record payload."""
        return {
            "role": self.role,
            "passed": self.passed,
            "failures": [f.as_dict() for f in self.failures],
            "hook_results": [
                {
                    "hook": r.hook,
                    "passed": r.passed,
                    "checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in r.checks],
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Role → required hooks mapping
# ---------------------------------------------------------------------------

# Maps agent role name to the ordered list of hooks that must pass before the
# task can be marked done.  Based on the Role Completion Matrix in future-verification.md.
ROLE_REQUIRED_HOOKS: dict[str, list[VerificationHook]] = {
    "planner": [
        ConfigVerificationHook(),
    ],
    "research": [
        PathPolicyVerificationHook(),
    ],
    "data": [
        ConfigVerificationHook(),
        PathPolicyVerificationHook(),
        HydrationVerificationHook(),
    ],
    "coding": [
        PathPolicyVerificationHook(),
        ExecutionVerificationHook(),
    ],
    "artifact": [
        PathPolicyVerificationHook(),
        ArtifactVerificationHook(),
    ],
    "health": [
        PathPolicyVerificationHook(),
        HealthVerificationHook(),
    ],
}


# ---------------------------------------------------------------------------
# Planner completion gate
# ---------------------------------------------------------------------------

class PlannerCompletionGate:
    """
    Enforce planner-role completion requirements before a task moves to done.

    Planner completion requires:
      1. The plan file (research_plan/current_plan.md) is present and non-empty.
      2. The task board snapshot (research_plan/task_board.md) is present and non-empty.
      3. The DB task status matches what the planner intends to write (checked by caller).

    Call check() before calling tasks.transition(newStatus="done") for planner tasks.
    """

    def check(self, context: dict[str, Any]) -> VerificationSummary:
        """
        context keys:
          - repo_path: str — absolute path to the project repo
          - plan_root: str — relative path to research_plan/ (default: "research_plan")
          - task_board_written: bool — True if mirror_board() was called this cycle
          - plan_file_written: bool — True if current_plan.md was updated this cycle
        """
        results: list[VerificationResult] = []
        repo_path = Path(context.get("repo_path", "."))
        plan_root = context.get("plan_root", "research_plan")

        # Check 1: current_plan.md exists and is non-empty
        plan_file = repo_path / plan_root / "current_plan.md"
        plan_exists = plan_file.exists() and plan_file.stat().st_size > 0
        plan_written = context.get("plan_file_written", plan_exists)

        from rail.verification import VerificationResult, CheckResult
        plan_checks = [
            CheckResult(
                "plan_file_present",
                bool(plan_written),
                "" if plan_written else f"research_plan/current_plan.md missing or empty at {plan_file}",
            )
        ]
        results.append(VerificationResult("planner_plan_file", bool(plan_written), plan_checks))

        # Check 2: task_board.md exists and is non-empty
        board_file = repo_path / plan_root / "task_board.md"
        board_exists = board_file.exists() and board_file.stat().st_size > 0
        board_written = context.get("task_board_written", board_exists)

        board_checks = [
            CheckResult(
                "task_board_snapshot_present",
                bool(board_written),
                "" if board_written else f"research_plan/task_board.md missing or empty at {board_file}",
            )
        ]
        results.append(VerificationResult("planner_task_board", bool(board_written), board_checks))

        # Check 3: DB task state — caller signals via context["db_task_status_current"]
        db_current = context.get("db_task_status_current", True)
        db_checks = [
            CheckResult(
                "db_task_status_current",
                bool(db_current),
                "" if db_current else "DB task status was not updated before planner completion",
            )
        ]
        results.append(VerificationResult("planner_db_state", bool(db_current), db_checks))

        passed = all(r.passed for r in results)
        return VerificationSummary(role="planner", passed=passed, results=results)


# ---------------------------------------------------------------------------
# Runner completion gate
# ---------------------------------------------------------------------------

class RunnerCompletionGate:
    """
    Enforce role-appropriate verification before a runner's task moves to done.

    Usage:
        gate = RunnerCompletionGate()
        summary = gate.check(role="data", context={...})
        if summary.passed:
            # call tasks.transition(taskId, newStatus="done", eventType="verification_passed",
            #                       eventPayload=summary.as_task_event_payload())
        else:
            # call tasks.transition(taskId, newStatus="blocked", eventType="verification_failed",
            #                       eventPayload=summary.as_task_event_payload())
    """

    def check(self, role: str, context: dict[str, Any]) -> VerificationSummary:
        """
        Run the hooks required for *role* against *context*.

        context should contain all keys needed by the hooks for this role.
        See individual hook docstrings for required context keys.
        """
        hooks = ROLE_REQUIRED_HOOKS.get(role, [PathPolicyVerificationHook()])
        results: list[VerificationResult] = []
        for hook in hooks:
            results.append(hook.run(context))

        passed = all(r.passed for r in results)
        return VerificationSummary(role=role, passed=passed, results=results)

    def resolve_transition(self, summary: VerificationSummary) -> tuple[str, str]:
        """
        Return (newStatus, eventType) for tasks.transition() based on gate outcome.

        Callers use this to pick the correct DB transition:
          - ("done", "verification_passed")  → task completes successfully
          - ("blocked", "verification_failed") → task is held for planner review
        """
        if summary.passed:
            return ("done", "verification_passed")
        return ("blocked", "verification_failed")
