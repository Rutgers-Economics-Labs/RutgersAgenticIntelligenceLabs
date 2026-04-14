# WO-F8.4 — Verification Enforcement Wiring

**Status:** complete  
**Spec:** `specs/future-verification.md`, `specs/future-agent-files.md`  
**Depends on:** WO-F8.3, WO-F4.3, WO-F6.3  
**Blocks:** WO-F9.2, WO-F9.3  

## Goal

Wire verification hooks into planner and runner completion paths so verification is enforced operationally instead of living only as helper utilities.

## Deliverables

- planner verification enforcement flow — `PlannerCompletionGate.check()` in `rail/completion_gate.py` validates plan file present, task board snapshot written, DB task state current before allowing a `done` transition
- runner completion verification gate — `RunnerCompletionGate.check(role, context)` + `resolve_transition()` runs role-appropriate hooks (`ROLE_REQUIRED_HOOKS`) and returns the correct `(newStatus, eventType)` for `tasks.transition()`
- normalized verification failure surface — `VerificationFailure` + `VerificationSummary.as_task_event_payload()` in Python; `taskEvents.recordVerification` mutation in Convex automatically moves failed tasks to `blocked`

## Implementation

- `packages/rail-py/rail/verification.py` — six deterministic hooks (config, path policy, hydration, execution, artifact, health)
- `packages/rail-py/rail/completion_gate.py` — `PlannerCompletionGate`, `RunnerCompletionGate`, `VerificationSummary`, `VerificationFailure`
- `packages/web/convex/taskEvents.ts` — `recordVerification` mutation (normalized failure surface, auto-blocks task on failure)
