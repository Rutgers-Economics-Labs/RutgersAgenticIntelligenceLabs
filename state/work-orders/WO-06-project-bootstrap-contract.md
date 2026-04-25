# WO-06: Project Bootstrap Contract

**Status:** ready

## Goal

Make new projects start with the planner-first repo contract.

## Context

Project bootstrap code lives in `packages/rail-py/rail/bootstrap.py`. The manifest model lives in `packages/rail-py/rail/manifest.py`.

## Scope

- Ensure new projects include `rail.yaml`.
- Ensure new projects include `.ontology/`.
- Ensure new projects include `research_plan/`.
- Ensure new projects include `agents/prompts/planner.md`.
- Ensure new projects include project-local skills.
- Keep `topics/` flexible.

## Acceptance Criteria

- A freshly bootstrapped project has the expected folders.
- The planner prompt is editable in Markdown.
- The ontology hydration contract remains compatible with the Python package.

## Verification

- Run or add a focused bootstrap test if dependencies permit.
- `python -m py_compile packages/rail-py/rail/bootstrap.py packages/rail-py/rail/manifest.py`
