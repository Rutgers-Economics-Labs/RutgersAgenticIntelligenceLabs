# Future Frontend

This document defines the future dashboard for the RAIL platform.

## Operating Model

The frontend is split evenly across three persistent planes:

- planner chat and execution control
- repository and knowledge views
- artifacts and run timeline

The UI should feel like an agent command center rather than a form-based admin console.

## Primary Layout

### Left Plane: Planner

Responsibilities:

- open-ended chat with the planner
- display approval requests
- show blocker questions from worker sessions
- show current plan summary
- show current task and next proposed task

### Center Plane: Repository

Responsibilities:

- render the repo tree based on `rail.yaml`
- show `specs/`, `research_plan/`, `.ontology/`, `topics/`, `skills/`, and `agents/`
- open files with syntax-aware viewers
- show commit and diff context for current session outputs

### Right Plane: Artifacts and Timeline

Responsibilities:

- render dashboards, charts, and reports from `artifacts/`
- show the sequential timeline of planner and worker runs
- show verification and health status
- show completed task history and costs

## Loading Model

The frontend should render project content primarily from the Git repository and the `rail.yaml` manifest.

The database supplements the repo with operational data:

- agent sessions
- secrets metadata
- task board status
- approvals
- run costs
- live runner events

## Primary Screens

### Project Home

Shows:

- planner chat
- active plan
- top-level repo summary
- latest artifacts
- recent runs

### Spec View

Shows:

- files from `specs/`
- approval history
- planner-authored changes

### Plan View

Shows:

- files from `research_plan/`
- current task board
- dependencies and blockers

The frontend should render both:

- the live operational board from the database
- the Git-visible planner snapshot in `research_plan/`

### Ontology View

Shows:

- `.ontology/ontology.yaml`
- source and pipeline inventories
- hydration status
- validation results

### Topic Workspace View

Shows:

- navigable topic tree
- notes, scripts, and outputs inside `topics/`
- topic-local graphs of files and outputs when available

### Artifact View

Shows:

- reports
- PDFs
- chart bundles
- dashboard JSON rendered into interactive components

## Task Board UX

The planner-owned task system should be visible in the UI as a simple Kanban-style board with a timeline companion.

Columns:

- backlog
- ready
- awaiting approval
- running
- blocked
- review
- done

The task board is operational state from the database, but each task should deep-link to relevant repo files and session events.
The UI should also surface the planner-authored Git snapshot so users can inspect planned work as durable project context.

## Project Setup UX

The platform should support a simple setup flow that:

- creates a repo using the required folder contract
- writes `rail.yaml`
- installs starter project skills
- initializes starter `agents/` files
- creates an initial `research_plan/` document

The setup flow should be available from the dashboard.

## Database Surfaces Needed By Frontend

Minimum operational surfaces:

- `projects`
- `project_secrets`
- `agent_sessions`
- `task_boards`
- `tasks`
- `task_events`
- `approvals`
- `runner_events`

## Design Direction

The redesign should preserve a calm, structured research-tool feel.

Preferred characteristics:

- split-pane layout with strong information hierarchy
- repo-aware navigation
- visible execution state without log overload
- artifact-first presentation for final outputs
- clean approval and blocker UX
