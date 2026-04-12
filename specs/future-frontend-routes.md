# Future Frontend Routes

This document defines the route map and screen responsibilities for the future RAIL frontend.

## Principles

- the frontend is a greenfield reset
- the project home should present a balanced dashboard summary
- the planner thread should be prominent but not full-screen
- the filesystem remains the primary content contract
- route behavior may progressively enhance common folder conventions without constraining the repository

## Primary Project Routes

Recommended V1 route map:

- `/[project]`
- `/[project]/specs`
- `/[project]/plan`
- `/[project]/ontology`
- `/[project]/topics/[...slug]`
- `/[project]/artifacts/[...slug]`
- `/[project]/sessions`
- `/[project]/settings`

This map may evolve, but it should be treated as the initial contract for implementation and work-order planning.

## Route Responsibilities

### `/[project]`

Primary project home.

This route should render the three-pane shell with:

- left: planner thread and execution control
- center: repo-aware summary and current plan/spec context
- right: recent artifacts, verification state, and recent run timeline

This is the default landing view for a project.

### `/[project]/specs`

Focused spec browsing and editing surface.

Should show:

- files from `specs/`
- planner-authored spec updates
- related approvals when relevant

### `/[project]/plan`

Focused planning surface.

Should show:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/tasks/<task>.md`
- the live DB-backed operational task board
- blockers and approvals relevant to current planning state

The frontend should show both Git-visible planner files and operational DB state.

### `/[project]/ontology`

Ontology and hydration surface.

Should show:

- `.ontology/ontology.yaml`
- source and pipeline inventories
- hydration status
- device-aware hydration availability
- validation state

### `/[project]/topics/[...slug]`

Topic workspace surface.

Should support deep browsing through the flexible topic tree.

The UI may progressively enhance common folder names such as:

- `notes/`
- `scripts/`
- `outputs/`

But this enhancement must not require those folders to exist.

### `/[project]/artifacts/[...slug]`

Artifact browsing and rendering surface.

Should support filesystem-backed artifact navigation and rendering for:

- reports
- PDFs
- charts
- datasets
- dashboard configs
- HTML/CSS/JS dashboards
- bundles

### `/[project]/sessions`

Operational timeline and debug surface.

Should include tabs for:

- planner and worker session timeline
- approvals and blocker questions
- cost breakdown
- normalized runner events
- raw runner payloads behind a debug toggle

### `/[project]/settings`

Operational project settings surface.

Should include:

- repo URL and branch info
- manifest viewer
- runner defaults
- hydration/device status
- restricted secrets management section

Secrets should live in this route, but behind a clearly restricted UI section.

## Home Route Panel Requirements

The project home planner panel should include:

- long-lived planner thread
- current task summary
- approval requests
- blocker questions
- next suggested action

The home route should feel like a calm command center rather than a chat-only screen.

