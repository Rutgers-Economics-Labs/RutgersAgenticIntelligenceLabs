# WO-02: File-Backed Session Supervisor

**Status:** ready

## Goal

Make file-backed sessions the normal control surface for live planner and worker sessions.

## Context

Session files are managed by `packages/api/app/services/session_files.py`. Worker lifecycle code is in `packages/api/app/runners/session_lifecycle.py`.

## Scope

- Keep the session directory layout stable:
  - `session.ndjson`
  - `commands.ndjson`
  - `state.json`
  - `summary.md`
- Make command append and command processing idempotent.
- Keep normalized event types simple and documented in code.
- Make session summaries useful for humans without making Markdown the machine protocol.

## Acceptance Criteria

- Events append to `session.ndjson`.
- Commands append to `commands.ndjson`.
- Processed commands are marked exactly once.
- `summary.md` refreshes from recent events.
- Malformed NDJSON lines do not crash reads.

## Verification

- `python -m py_compile packages/api/app/services/session_files.py packages/api/app/runners/session_lifecycle.py`
- Run focused session file tests if the local test environment supports it.
