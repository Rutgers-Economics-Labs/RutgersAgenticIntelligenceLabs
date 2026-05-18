# Future Spec: UI And Control Plane

Date: 2026-05-18

## Goal

The UI should not just show artifacts and tasks.

It should be the operator console for a living ontology-backed research program.

Users should be able to see:

- what the platform thinks is happening
- what is actually happening
- what is blocked
- what the ontology currently covers
- what research questions are answerable now
- what expansion would unlock the next best question

## Control Plane Layout

The frontend should be organized into explicit planes.

### 1. Planner plane

Shows:

- current objective
- task graph
- current lane owner
- why the current task was chosen
- approvals needed
- proposed next tasks

### 2. Ontology plane

Shows:

- active ontology artifact
- hydration status
- ontology health
- class counts
- measure coverage
- freshness and provenance warnings

### 3. Artifact plane

Shows:

- reports
- dashboards
- tables
- figures
- exported datasets
- lineage and verification status for each artifact

### 4. Session plane

Shows:

- active session
- session history
- runtime costs
- stale or zombie detection
- audit results

### 5. Integrity plane

Shows:

- sources
- claims
- verification runs
- gate results
- promotion blockers

## Most Important Views

### Current blocker view

There should be exactly one prominent view that answers:

- what is the single main blocker right now?
- what category is it?

Categories:

- source gap
- hydration failure
- ontology health failure
- stale session
- planner drift
- integrity gap
- approval required

### Current truth view

Show side by side:

- repo truth
- runtime truth
- audited truth

This is how users regain confidence after drift incidents.

### Ontology coverage explorer

Show:

- classes
- counts
- season coverage
- geography or competition coverage
- known partial areas
- suggested next research questions

### Task evidence view

For each task, show:

- acceptance criteria
- evidence that each criterion is satisfied
- linked artifacts
- linked sessions
- why the task is `done`, `blocked`, `ready`, or `superseded`

## Steering Actions

The UI should provide explicit actions for common interventions:

- reprioritize task
- cancel stale session
- relaunch task
- promote ready task
- mark blocked with reason
- request ontology expansion
- approve or pause agent run
- ask planner to reconsider next step

These should be first-class actions, not chat-only instructions.

## Open-Ended Chat

The chat interface should remain, but its role is:

- capture new questions
- refine scope
- explain planner reasoning
- request direction changes

It should not be the only way to steer the project.

## Data Loading Model

The UI should read from:

- repo-derived projections for durable content
- runtime API for operational metadata
- audited projections for trust-sensitive status

It should not trust raw runner state alone.

## Rendering Model

The app can still use a React/Next.js architecture, but it should treat:

- repo-backed content
- runtime session state
- ontology summaries
- integrity summaries

as distinct data sources with explicit labels.

## What The UI Must Make Obvious

1. whether the ontology is actually active
2. whether current research is ontology-backed or only planned
3. whether a task is blocked by data, by policy, or by stale state
4. whether a report is draft, partially verified, or promotable
5. whether a follow-up question is answerable now or requires expansion

## High-Leverage Future Features

- “Why this task now?” explainer
- “What changed after the last session?” diff summary
- “What would unlock the next best question?” expansion planner
- “Trust level” badges for sources, claims, and artifacts
- “Audit failed because…” panels with actionable fixes

## Minimal First UI Upgrades

If only a few things are built first, prioritize:

1. current blocker view
2. audited truth vs raw truth view
3. ontology coverage explorer
4. task evidence panel
5. stale-session recovery controls
