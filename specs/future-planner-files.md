# Future Planner Files

This document defines the Git-visible planner file contract under `research_plan/`.

## Principles

- planner state must be visible in Git
- planner files should be easy for both humans and the frontend to parse
- operational DB state remains authoritative for live execution
- Git-visible files provide durable project context and history

## Standard Files

The planner should standardize on these files:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/tasks/<task-slug>.md`

Optional future files may include:

- `research_plan/approvals.md`
- `research_plan/blockers.md`

V1 should keep the planner file set minimal.

## `current_plan.md`

Purpose:

- human-readable summary of the current project plan
- top-level project execution context for the frontend

Suggested contents:

- current objective
- active topic or focus area
- current phase
- next planned tasks
- recent changes

## `task_board.md`

Purpose:

- Git-visible snapshot of the planner’s task board

Suggested sections:

- backlog
- ready
- awaiting approval
- running
- blocked
- review
- done

This file is a mirrored summary, not the live operational source of truth.

## `tasks/<task-slug>.md`

Purpose:

- durable task card format that the frontend can parse cleanly

Each task file should use a predictable structure with frontmatter-style metadata.

Suggested fields:

- `title`
- `status`
- `assigned_role`
- `dependencies`
- `acceptance_criteria`
- `related_files`
- `latest_run_summary`

Suggested example:

```md
---
title: Add county labor source
status: ready
assigned_role: data
dependencies:
  - define-county-schema
acceptance_criteria:
  - YAML validates
  - dry run passes
related_files:
  - .ontology/sources/county_labor.yaml
  - .ontology/pipelines/labor_pipeline.yaml
latest_run_summary: "Not started"
---

## Description

Add and validate a new county labor data source for the ontology layer.

## Notes

- use the FRED connector pattern
- keep writes inside `.ontology/`
```

## Frontend Parsing Rules

The frontend should be able to parse planner files to show:

- current plan summary
- task board snapshot
- structured task metadata
- linked files and acceptance criteria

The frontend should not depend only on DB state for planner context.

## Sync Rules

The planner should update these files when:

- a new plan is approved
- the task board changes materially
- a task moves to a meaningful new stage
- a task’s acceptance criteria or related files change

The frontend should display both:

- Git-visible planner files
- live DB-backed operational state

