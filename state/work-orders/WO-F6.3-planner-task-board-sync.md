# WO-F6.3 — Planner Task Board Sync

**Status:** complete  
**Spec:** `specs/future-planner-files.md`, `specs/future-database.md`  
**Depends on:** WO-F6.2  
**Blocks:** WO-F7.2, WO-F7.3  

## Goal

Keep the operational task board and Git-mirrored planner files in sync at meaningful planner state transitions.

## Deliverables

- sync rules — `SYNC_TRIGGERS` + `MATERIAL_STATUSES` constants in `rail/planner_sync.py`
- board state update flow — `getBoardSummary` query in `convex/taskBoards.ts` returns board + tasks grouped by status for markdown rendering
- task transition mirror logic — `tasks.transition` mutation (atomic status update + event insert + `shouldSync` signal); `PlannerSync.sync_on_transition()` in Python writes `research_plan/tasks/<slug>.md` and `research_plan/task_board.md`

## Implementation

- `packages/rail-py/rail/planner_sync.py` — `PlannerSync` class, `render_task_md()`, `render_task_board_md()`
- `packages/web/convex/tasks.ts` — `transition` mutation
- `packages/web/convex/taskBoards.ts` — `getBoardSummary` query

