# WO-F3.6 — Future API Surface Cleanup

**Status:** complete  
**Spec:** `specs/future-database.md`, `specs/future-architecture.md`  
**Depends on:** WO-F3.2, WO-F6.3  
**Blocks:** WO-F7.2, WO-F7.5  

## Goal

Clean up the backend API surface so future planner, settings, and runner flows use a coherent project/planner contract instead of a mix of legacy and future-only endpoints.

## Deliverables

- future-oriented project API inventory — `specs/future-api-surface.md` documents the clean contract (project slug as canonical ID, `/projects/{slug}/planner/` prefix, `getBySlug` as the authoritative lookup)
- deprecated legacy surface list — `specs/future-api-surface.md` §Legacy Surfaces enumerates endpoints that must not be extended
- planner/settings API cleanup pass — `planner_service.py` now delegates to `PlannerSync` for markdown rendering, uses `tasks:transition` for atomic status changes with correct event types, and drops the `defaultdict` import; `projects.py` router uses `projects:getBySlug` consistently

## Implementation

- `packages/api/app/services/planner_service.py` — replaced inline `_task_file_markdown` / `_task_board_markdown` with `PlannerSync`, switched status updates to `tasks:transition`, added `_STATUS_EVENT_MAP`, removed `defaultdict`
- `packages/api/app/routers/projects.py` — `projects:get` → `projects:getBySlug`
- `specs/future-api-surface.md` — full API inventory and deprecation list

## Tests (128 passing)

- `packages/api/tests/test_planner_sync.py` — 44 tests covering `SYNC_TRIGGERS`, `MATERIAL_STATUSES`, `render_task_md`, `render_task_board_md`, `PlannerSync` (should_sync, mirror_task, mirror_board, sync_on_transition)
- `packages/api/tests/test_verification.py` — 53 tests covering all 6 verification hooks + helpers
- `packages/api/tests/test_completion_gate.py` — 31 tests covering `VerificationFailure`, `VerificationSummary`, `ROLE_REQUIRED_HOOKS`, `PlannerCompletionGate`, `RunnerCompletionGate`, end-to-end integration
