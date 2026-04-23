# WO-05: Jules End-To-End Runner

## Goal

Make Jules the first real worker runner behind the planner-owned runtime model.

## Context

The Jules adapter is in `packages/api/app/runners/jules.py`. The runner lifecycle bridge is in `packages/api/app/runners/session_lifecycle.py`.

## Scope

- Confirm Jules session creation works from a work order.
- Mirror Jules events into file-backed session files.
- Relay Jules questions into planner-visible files/messages.
- Relay approvals from repo-backed approval files or session commands.
- Keep one active worker per project.

## Acceptance Criteria

- A Jules session can be started from a task payload.
- The session path is recorded in the live running-agent record.
- Jules activity events are normalized into session files.
- Questions and approvals are visible to the planner.

## Verification

- Start one Jules session against a small safe task.
- Confirm `research_plan/sessions/<role>/<session-id>/summary.md` updates.

