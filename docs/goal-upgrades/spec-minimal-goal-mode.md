# Spec: Minimal Goal Mode Delta

## Purpose

RAIL already has planners, tasks, autopilot, auditors, and a repo-first control plane.

The smallest useful change to make it behave more like true Goal Mode is:

- add a durable repo-backed project goal contract
- make planner and autopilot read that contract first
- keep the existing `.rail/goal/*` runtime as a richer projection instead of replacing it

This avoids a full rewrite while giving the system one explicit source of intent.

## Minimal Architectural Change

Canonical goal intent moves to:

- `research_plan/goal.json`

Runtime goal state remains in:

- `.rail/goal/goal.md`
- `.rail/goal/goal_state.json`
- `.rail/goal/goal_lessons.json`
- `.rail/goal/goal_blockers.json`
- `.rail/goal/goal_decisions.json`

Rule:

- `research_plan/goal.json` is the durable project contract
- `.rail/goal/*` is the runtime projection built from that contract plus current repo state

## Goal Contract Schema

Minimum required fields:

- `schemaVersion`
- `goalId`
- `objective`
- `successCriteria`
- `requiredEvidence`
- `forbiddenShortcuts`
- `escalationPolicy`
- `allowedSpend`
- `createdAt`
- `updatedAt`
- `mode`

Example:

```json
{
  "schemaVersion": 1,
  "goalId": "goal-abc123",
  "objective": "Complete the weather shock research project.",
  "successCriteria": [
    "admissible sources are registered and classified",
    "required data or ontology artifacts are hydrated and available",
    "final artifacts contain provenance-backed claims",
    "verification and closeout gates pass"
  ],
  "requiredEvidence": [
    "source registry entries",
    "hydration or dataset artifact path",
    "claims or artifact lineage proving provenance",
    "passing closeout or verification evidence"
  ],
  "forbiddenShortcuts": [
    "do not mark complete from task activity alone"
  ],
  "escalationPolicy": [
    "pause only for scope decisions"
  ],
  "allowedSpend": {
    "timeMinutes": 180,
    "tokens": null,
    "apiCostUsd": null,
    "retries": 3
  },
  "createdAt": 0,
  "updatedAt": 0,
  "mode": "goal"
}
```

## Runtime Projection

The richer goal runtime should continue to track:

- phase
- current blocker
- current subgoal
- retry usage
- lessons
- blockers
- decisions
- success-criteria satisfaction
- autonomy confidence

This runtime is allowed to evolve independently as long as it remains derived from:

- `research_plan/goal.json`
- repo truth
- auditor state
- active session telemetry

## Planner And Autopilot Delta

No large redesign is required for the first pass.

Minimal behavior change:

1. load `research_plan/goal.json`
2. project it into `.rail/goal/*`
3. derive the current subgoal from unmet success criteria or preflight blockers
4. expose that subgoal in planner/control-plane surfaces

This means autopilot can remain task-driven underneath, but it now has a durable goal contract and a visible current subgoal to follow.

## Current Subgoal Rules

Current subgoal should be derived in this priority order:

1. first failing preflight check
2. first unmet success criterion
3. active blocker repair action
4. `null` if the goal is complete

This is intentionally simple.

The first pass does not require a full hierarchical subgoal planner.

## UI Delta

Existing Goal Mode UI can remain in place.

Additions:

- surface `currentSubgoal`
- surface `goalJson` in repo-backed file metadata

This keeps the user-visible Goal Mode honest without redesigning the planner UI.

## Acceptance

The minimal Goal Mode delta is complete when:

- creating a goal writes `research_plan/goal.json`
- loading a goal works even if only `research_plan/goal.json` exists
- `.rail/goal/*` stays in sync as runtime projection
- planner/control-plane summaries expose `currentSubgoal`
- real projects can persist and reload the goal contract from repo state
