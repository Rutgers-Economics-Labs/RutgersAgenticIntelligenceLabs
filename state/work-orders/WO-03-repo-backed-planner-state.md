# WO-03: Repo-Backed Planner State

**Status:** ready

## Goal

Finish moving planner state to repo-backed Markdown files.

## Context

Planner state should live under `research_plan/`, not in durable database tables.

## Scope

- Keep task cards in `research_plan/tasks/*.md`.
- Keep approvals in `research_plan/approvals/*.md` and the index in `research_plan/approvals.md`.
- Keep blockers in `research_plan/blockers.md`.
- Keep the current plan in `research_plan/current_plan.md`.
- Remove or quarantine assumptions that tasks, approvals, planner messages, or historical sessions are durable DB state.

## Acceptance Criteria

- Planner tools can list/create/update tasks from files.
- Planner tools can request/resolve approvals from files.
- Syncing planner files is deterministic.
- No code path requires old task/approval tables for normal planner operation.

## Verification

- `python -m py_compile packages/api/app/services/planner_service.py packages/api/app/services/planner_runtime.py`
