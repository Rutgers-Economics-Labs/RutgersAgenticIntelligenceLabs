# Future Work Order Queue

This file is the current execution queue for the future-spec rebuild. It exists so the planner, humans, and temporary runner scripts all have a single visible sequence to follow.

## Current Snapshot

### Completed locally

- `WO-F1.1` Manifest schema
- `WO-F1.2` Bootstrap generator
- `WO-F1.3` Starter project templates
- `WO-F2.1` Agent YAML schema
- `WO-F2.2` Prompt and checklist loader
- `WO-F2.3` Role policy resolver
- `WO-F3.1` Convex schema reset
- `WO-F3.2` Projects and planner-thread tables
- `WO-F3.4` Runner events and sessions tables
- `WO-F5.1` Device registry
- `WO-F5.2` Hydration artifact registry
- `WO-F5.3` Hydration reuse and stale detection
- `WO-F6.1` Long-lived planner thread
- `WO-F6.2` Git-mirrored planner files
- `WO-F8.1` `rail.yaml` project loader
- `WO-F8.2` `.ontology` hydration alignment
- `WO-F8.3` Verification hooks
- `WO-F3.3` Task board and approvals tables
- `WO-F3.5` Project secrets and policy tables
- `WO-F4.1` Runner abstraction
- `WO-F4.2` Jules session lifecycle
- `WO-F4.3` Jules approvals and question relay

### In progress locally

_(none)_

### Pending
- `WO-F3.6` Future API surface cleanup
- `WO-F6.3` Planner task board sync
- `WO-F7.1` Route reset and shell scaffold
- `WO-F7.2` Planner plane
- `WO-F7.3` Repo browser plane
- `WO-F7.4` Artifacts and timeline plane
- `WO-F7.5` Settings and sessions surfaces
- `WO-F7.6` Legacy UI quarantine
- `WO-F9.1` Artifact indexing
- `WO-F9.2` Report and PDF rendering
- `WO-F9.3` Dashboard rendering
- `WO-F8.4` Verification enforcement wiring

## Recommended Waves

### Wave A: policy and database completion

- `WO-F3.3`
- `WO-F3.4`
- `WO-F3.5`
- `WO-F3.6`

### Wave B: runner and planner completion

- `WO-F4.1`
- `WO-F4.2`
- `WO-F4.3`
- `WO-F6.3`
- `WO-F8.3`
- `WO-F8.4`

### Wave C: frontend shell and primary views

- `WO-F7.1`
- `WO-F7.2`
- `WO-F7.3`
- `WO-F7.4`
- `WO-F7.5`
- `WO-F7.6`

### Wave D: artifact UX

- `WO-F9.1`
- `WO-F9.2`
- `WO-F9.3`

## Jules Handoff Rule

- Do not send `completed` work orders to Jules.
- Do not send `in_progress` work orders to Jules until the current local implementation has been reviewed and committed.
- Prefer running only the first ready dependency wave at a time rather than the full backlog in one chain.
