# Spec: Repo-First Goal Upgrade Migration Plan

## Phase 1

Implement the first repo-backed control-plane projection.

Required work:

- define `control_plane_snapshot.json`
- persist it during reconciliation
- make command-center prefer it when present
- add focused tests for persistence and read preference

Acceptance:

- reconcile writes the snapshot into `research_plan/state`
- command-center can load from that snapshot
- runtime-only overlays remain possible

## Phase 2

Expand reconciliation into the single project-state builder.

Required work:

- centralize control-plane projection logic
- reduce ad hoc command-center recomputation
- ensure project reality and command-center summarize the same reconciled truth

Acceptance:

- overview and integrity surfaces agree on drift and blockers
- repeated page loads no longer recompute the same heavy state paths

## Phase 3

Make autopilot repo-driven.

Required work:

- read next work from repo-backed task and goal state
- write session results into repo-backed truth
- trigger reconcile after state-changing work
- demote runtime flags to telemetry

Acceptance:

- `active` no longer implies progress without worker evidence
- repo truth can reconstruct progress after restart

## Phase 4

Demote non-repo durable state.

Required work:

- remove duplicated durable control-plane truth from external mirrors
- keep external services for notifications and ephemeral presence only
- degrade safely when networked services fail

Acceptance:

- local RAIL remains trustworthy without Convex
- external outages do not corrupt durable project state

## Phase 5

Normalize legacy state once.

Required work:

- migrate old session, verification, and integrity shapes
- stop relying on endless read-time compatibility shims

Acceptance:

- canonical repo state is stable enough for simpler readers
- compatibility code moves out of hot paths
