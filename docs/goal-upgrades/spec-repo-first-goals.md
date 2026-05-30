# Spec: Repo-First Goals

## Purpose

RAIL currently mixes project truth, execution truth, and live service truth. This makes goals hard to audit and lets autopilot appear active even when no worker is progressing.

This spec defines goals as repo-backed completion contracts.

## Core Model

There are two different kinds of goal state:

### 1. Project Contract

This is durable project truth.

It answers:

- What is the project trying to complete?
- What evidence counts as success?
- What deliverables are required?
- What constraints must not be violated?

Canonical storage:

- `research_plan/goal.json`
- `.rail/goal/goal.md`
- `.rail/goal/goal_state.json`
- `.rail/goal/goal_lessons.json`
- `.rail/goal/goal_blockers.json`
- `.rail/goal/goal_decisions.json`

`research_plan/goal.json` is the minimal durable contract.

`.rail/goal/*` is the richer runtime projection derived from that contract plus current repo state.

### 2. Execution Goal

This is scoped to a live planner or worker loop.

It answers:

- What is the next bounded objective?
- What evidence should this run produce?
- What exact blocker or gate is it trying to clear?

Execution goals are not the durable source of project truth. They are derived from the project contract plus current repo state.

## Required Goal Properties

Every durable goal contract must include:

- objective
- success criteria
- required evidence
- forbidden shortcuts
- escalation policy
- spend limits
- current phase
- current blocker

## Goal Completion Rules

A goal may be marked complete only when repo-backed evidence supports completion.

Completion must not rely on:

- active autopilot state
- Convex session mirrors
- pending worker intentions
- UI-only counters

Completion must rely on repo-backed evidence such as:

- artifact lineage
- verification runs
- closeout audit state
- trusted deliverables on disk

## Status Separation

The system must keep these concepts separate:

- `substantive_completion`
- `integrity_completion`
- `promotion_completion`
- `runtime_activity`

These should not collapse into a single `done` flag.

## Relationship To Autopilot

Autopilot is not the durable owner of goal truth.

Autopilot should:

- read repo-backed goal state
- choose next bounded work
- write results back into repo truth
- trigger reconciliation

Autopilot should not:

- invent new durable goal truth outside the repo
- declare project completion from runtime activity alone

## Relationship To Command Center

The command center is a projection, not a source of truth.

It should summarize:

- goal state
- blockers
- task counts
- active sessions
- artifact and integrity status

But those summaries must be derived from the repo.
