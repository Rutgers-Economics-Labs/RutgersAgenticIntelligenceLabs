# WO-04: Minimal Runtime DB

**Status:** ready

## Goal

Reduce runtime database usage to the smallest useful control plane.

## Context

The database should store projects, currently running agents, and encrypted secrets/policies. Durable project memory should stay in Git.

## Scope

- Keep project registry usage.
- Keep active running-agent handles.
- Keep encrypted secrets and per-role allowlists.
- Avoid durable DB-backed planner messages, tasks, approvals, task events, runner history, or artifact bodies.
- Ensure finished sessions can be removed from the live running-agent surface after repo files are written.

## Acceptance Criteria

- Active workers can be listed and reattached.
- Finished workers no longer appear as active.
- Secrets are not written into repo-backed session or summary files.
- Planner state can be reconstructed from repo files plus active running agents.

## Verification

- `python -m py_compile packages/api/app/services/running_agent_service.py packages/api/app/runners/session_lifecycle.py`
