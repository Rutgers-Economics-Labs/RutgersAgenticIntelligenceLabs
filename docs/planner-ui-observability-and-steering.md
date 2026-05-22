# Planner UI: Observability And Steering Recommendations

## Goal

Make it obvious:

1. what the planner thinks is happening
2. what worker is actually running
3. what artifact or gate is blocking progress
4. how a user can redirect the project without editing repo state by hand

This document is based on a full end-to-end run of the soccer project, including hydration, ontology promotion, cross-competition expansion, research delivery, and repeated planner/control-plane recovery.

## Core Product Problem

Today the UI shows fragments of truth:

- planner board state
- active runner sessions
- repo-backed task files
- hydration state
- approvals
- artifacts

But it does not show which of those is authoritative when they disagree.

That caused repeated confusion during the soccer run:

- task board said one thing while task markdown said another
- a session was still shown as running after the work was already durably done
- the ontology was hydrated on disk before the active project pointers were promoted
- stale truncated task files reintroduced ghost rows after the real task was complete
- autopilot launched planner work that was lower priority than the real blocked data lane

## What The UI Should Add

### 1. Single “Project Reality” Header

At the top of the project page, show one compact execution header with:

- `project phase`: pre-hydration / hydrated / research / closeout
- `active ontology artifact`: path or session source
- `active worker`: session id, role, runner, task id
- `current blocking gate`: approval / hydration / workflow contract / publish / no blocker
- `next planned action`: what autopilot will do next

This should be the first thing visible on the page.

## 2. Authority Badges

Every stateful surface should declare its authority:

- `DB authoritative`
- `repo mirror`
- `workspace-only`
- `historical session state`

Example:

- `task_board.md` should visibly say it is a mirrored snapshot
- planner API task rows should visibly say they are the authoritative live task state
- session summaries should indicate whether they are runtime-backed or file-backed recovery state

Without this, users assume every surface is equally current.

## 3. Task Detail Page With Four Panes

Every task should open into a detailed view with:

- `Definition`
  - task id
  - canonical slug
  - acceptance criteria
  - dependencies
  - approval state
- `Execution`
  - active or last session
  - runner
  - workspace path
  - last event
  - cancel / retry / replace actions
- `Evidence`
  - files created
  - latest artifact links
  - ontology counts or query evidence if relevant
- `State Integrity`
  - duplicate slug detected?
  - task file mismatch?
  - stale running session?
  - workflow contract unmet?

This would have made almost every soccer-project recovery faster.

## 4. Canonical Task Identity UI

The UI should visibly distinguish:

- canonical task id
- filename
- truncated or legacy alias

It should surface warnings like:

- `duplicate repo task file detected`
- `canonical task id has more than one mirrored file`
- `truncated task mirror is shadowing canonical state`

This is not cosmetic. Ghost task files repeatedly created stale board rows.

## 5. Planner Thought Trace

Add a collapsible “why the planner chose this” panel with:

- triggering event
- planner decision
- evidence used
- tasks promoted, blocked, or superseded

Example:

- `Autopilot promoted final synthesis because ontology is hydrated, domestic research is done, cross-competition research is done, and no higher-priority blocker tasks remain.`

Right now the user has to infer that from session logs and board drift.

## 6. Better Manual Steering Controls

The user needs structured redirection, not only freeform chat.

Add controls to:

- `pause this lane`
- `replace this task with a narrower one`
- `change project direction`
- `prioritize more data over final reporting`
- `approve and launch this task now`
- `mark this task done from durable evidence`

Each action should require a short rationale that is written into planner history.

## 7. “Change Direction” Wizard

When the user wants to pivot, the UI should ask:

- is this a new question answerable by current ontology?
- does this require ontology expansion?
- should existing final-report work be paused?
- should follow-up questions be generated now?

Then it should create the correct planner tasks automatically.

This is better than expecting the planner to infer the exact project-management change from chat alone.

## 8. Live Blocker Classification

The UI should have a dedicated blocker card that classifies the current blocker as one of:

- source availability
- hydration failure
- ontology promotion failure
- workflow contract failure
- stale session / control-plane bug
- approval needed
- repo state mismatch

The card should include:

- exact failing step
- exact file or session
- recommended next intervention

During the soccer run, this would have prevented many wasted loops.

## 9. Session Lifecycle Controls

For every running session, expose:

- `nudge`
- `cancel`
- `replace with narrower brief`
- `mark stale and reconcile`
- `open workspace diff`

The UI should also detect likely stale sessions automatically, for example:

- no meaningful file changes for N minutes
- still “setting up workspace” after N minutes
- task outputs already exist but session remains running

## 10. Final Closeout Checklist

When a project reaches the end, the UI should switch to a closeout checklist:

- ontology hydrated and active
- research tasks completed
- final report task completed
- duplicate task mirrors absent
- no active stale sessions
- artifact lineage present
- verification state acceptable

This should gate any “project complete” badge.

## Recommended UI Layout

## Left Rail

- phase
- blocker
- active worker
- approvals pending
- hydration status

## Main Column

- board
- task detail
- evidence pane

## Right Rail

- planner rationale
- user steering actions
- recent interventions

## Minimal High-Value Features To Build First

If implementation bandwidth is limited, the highest-leverage additions are:

1. Project Reality Header
2. Authority Badges
3. Task Detail Page with Execution + Evidence panes
4. Duplicate Task / Stale Session warnings
5. Manual steering controls for cancel, replace, approve, and redirect

Those five would have reduced most of the friction in this run.
