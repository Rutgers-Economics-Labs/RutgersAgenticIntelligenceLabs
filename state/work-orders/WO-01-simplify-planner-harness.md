# WO-01: Simplify Planner Harness

## Goal

Make the native planner harness the simple front door for the agent system.

## Context

The current harness exists in `packages/api/app/services/planner_harness.py`, but the surrounding runtime is still spread across several services. The goal is not to add more framework code. The goal is to make the planner loop easy to understand and safe to call from a future UI or CLI.

## Scope

- Keep `PlannerHarness.ask(...)` as the primary interface.
- Ensure planner messages are mirrored to `research_plan/sessions/planner/planner/`.
- Keep the planner prompt loaded from `agents/prompts/planner.md`.
- Make local-repo mode work without requiring a project DB row.
- Add a short docstring or module comment that explains the stack in plain language.

## Acceptance Criteria

- A developer can understand how to call the planner from one file.
- The harness writes user and assistant messages to the planner session files.
- The harness does not require the old UI or old task tables.
- Relevant compile checks pass.

## Verification

- `python -m py_compile packages/api/app/services/planner_harness.py`
- If dependencies are available, run the focused planner harness tests.

