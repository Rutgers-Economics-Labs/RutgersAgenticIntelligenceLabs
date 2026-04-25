# WO-07: Test And Cleanup Pass

**Status:** ready

## Goal

Clean remaining old-platform assumptions and make the focused test path reliable.

## Context

The codebase currently has incomplete dependency setup in the local environment. Focus on making the planner-first spine testable without requiring the old UI.

## Scope

- Remove stale imports or routes that assume the deleted UI is present.
- Keep optional test dependencies optional when possible.
- Add focused tests for session files, planner harness, and repo-backed planner state.
- Document any dependency gaps instead of hiding them.

## Acceptance Criteria

- Focused planner/session tests can run in a clean supported environment.
- Compile checks pass for touched files.
- The worktree no longer contains old work-order backlogs.
- Remaining legacy code paths are clearly identified or removed.

## Verification

- `python -m py_compile` on touched runtime files.
- Focused `pytest` where dependencies are installed.
