# Claude Buddy

This file is the parallel-work brief for the Claude Code agent while the main
frontend scaffold is being built.

## Read First

To understand the project, architecture, and product goals, start with these
files in order:

1. [goals/roadmap.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/goals/roadmap.md)
2. [specs/future-architecture.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/specs/future-architecture.md)
3. [specs/future-repo-contract.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/specs/future-repo-contract.md)
4. [specs/future-runners.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/specs/future-runners.md)
5. [specs/frontend-command-center.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/specs/frontend-command-center.md)

Then inspect the backend surfaces the frontend depends on:

6. [packages/api/app/main.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/main.py)
7. [packages/api/app/routers/projects.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/routers/projects.py)
8. [packages/api/app/runners/session_lifecycle.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/runners/session_lifecycle.py)
9. [packages/api/app/services/session_files.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/services/session_files.py)
10. [packages/api/app/services/planner_runtime.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/services/planner_runtime.py)

Look at the project repo we are using for live testing:

11. `/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-sad/rail.yaml`
12. `/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-sad/research_plan/`
13. `/Users/akashdubey/Documents/CodingProjects/RAIL/RAIL-sad/agents/`

## What The Frontend Needs

The new React frontend is being scaffolded in:

- [apps/web](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/apps/web)

While that UI shell is being built, your job is to improve the backend read
models and file-serving surfaces that the UI will need.

The key product requirement is deep agent observability. The user wants to see:

- what every agent is doing
- which runner is active
- which files a worker is editing
- recent commands
- recent messages and planner relays
- verification state
- workspace branch/path
- review blockers

## Your Task

Work on backend/API support only. Do not restructure or replace the frontend
scaffold under `apps/web` unless a small compatibility fix is needed.

### Primary Goal

Create or improve backend endpoints/read models so the frontend can load a
single consolidated session detail object for each agent run.

### Focus Areas

1. Improve runner session detail shape in [packages/api/app/routers/projects.py](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages/api/app/routers/projects.py)

The UI needs richer session detail than it has today.

Please add or improve fields for:

- current focus
- last meaningful event summary
- recent command executions
- recent file changes
- recent planner relays
- recent agent progress messages
- setup/verification/archive status
- changed file count

2. Add a repo/session timeline read model

If needed, add a helper service that turns:

- `session.ndjson`
- `commands.ndjson`
- `state.json`

into a frontend-ready timeline with normalized rows.

3. Add lightweight repo file reading surface if missing

The frontend will soon need to open repo-backed files like:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/sessions/**/summary.md`
- `research_plan/sessions/**/diff.md`
- `research_plan/sessions/**/todos.md`
- `research_plan/sessions/**/verification.md`

If there is no simple repo content endpoint yet, add one.

4. Keep everything additive

Do not break existing routes.
Prefer adding fields and helper endpoints over replacing current response shapes.

## Constraints

- You are not alone in the codebase.
- Do not revert edits made by others.
- Assume the frontend scaffold in `apps/web` may change while you work.
- Do not rewrite the planner/runtime architecture.
- Keep the DB operational-only and repo-backed state durable.

## Good Deliverables

A strong contribution would be:

- one helper service for frontend session detail/timeline shaping
- one or two additive project routes for session detail and repo file content
- tests covering the new read models

## Avoid

- building a separate frontend
- changing the Streamlit app
- introducing a database-first UI contract
- hiding raw repo paths the user may need for inspection

## Definition Of Done

You are done when the frontend can easily load:

- project home summary
- planner board
- runs list
- one rich run detail view

without scraping raw NDJSON or reconstructing state in the browser.
