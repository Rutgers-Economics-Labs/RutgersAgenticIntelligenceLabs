# Future Spec: Auditor Agents

Date: 2026-05-18

## Purpose

Auditor agents are the missing layer between agent output and trusted project state.

Workers generate candidate reality.

Auditors certify actual reality.

Autopilot and planner should advance only from audited reality.

## Required Auditor Roles

### 1. `session_auditor`

Responsibilities:

- detect stale running sessions
- detect zombie runner processes
- reconcile file-backed completed sessions
- close duplicate or superseded sessions
- certify execution-lane availability

Inputs:

- runtime session rows
- session summaries
- session workspaces
- runner PIDs and heartbeats

Outputs:

- session finalization decision
- duplicate cancellation decision
- liveness classification
- reconciled session status

### 2. `planner_auditor`

Responsibilities:

- compare board state to repo task state
- detect duplicate/truncated task files
- mark tasks done when acceptance is already satisfied by repo evidence
- supersede obsolete tasks
- classify unresolved blockers accurately

Inputs:

- planner board
- `research_plan/tasks/*.md`
- approvals
- current repo artifacts

Outputs:

- task reconciliations
- task supersession updates
- blocker classifications

### 3. `ontology_auditor`

Responsibilities:

- verify active ontology artifact path
- verify hydration actually produced non-empty expected classes
- distinguish between:
  - no ontology
  - hydrated but empty
  - hydrated but stale
  - hydrated and healthy
- promote valid local reusable artifacts when appropriate

Inputs:

- hydration registry
- active artifact pointers
- `.ontology/.rail_hydration.json`
- ontology class counts

Outputs:

- ontology health state
- active artifact decision
- hydration rerun recommendation

### 4. `integrity_auditor`

Responsibilities:

- validate sources
- validate claims
- validate artifact lineage
- validate verification-run coverage
- normalize legacy schema records
- decide whether artifacts are promotable

Inputs:

- `research_plan/state/sources.json`
- `research_plan/state/claims.json`
- `research_plan/state/artifact_lineage.json`
- `research_plan/state/verification_runs.json`

Outputs:

- integrity gate result
- migration or repair suggestions
- artifact promotion classification

### 5. `closeout_auditor`

Responsibilities:

- verify there are no active required workers
- verify required tasks are all done
- verify final artifact set exists
- verify integrity gate is clean
- verify the project can be closed without hidden drift

Inputs:

- board state
- active agent state
- integrity gate
- final artifact checklist

Outputs:

- closeout certificate
- reopen recommendation if any requirement fails

## Audit Timing

Auditors should run:

- after every completed worker session
- after every failed worker session
- before autopilot launches the next task
- before any final artifact promotion
- before project closeout

Recommended batch order:

1. session audit
2. planner audit
3. ontology audit
4. integrity audit
5. closeout audit when relevant

## Audit Contract

Each auditor should emit a structured result:

```json
{
  "auditor": "ontology",
  "status": "passed",
  "findings": [],
  "actions_taken": [],
  "actions_recommended": [],
  "blocks_advance": false
}
```

If `blocks_advance` is true, autopilot must not continue.

## Deterministic vs Agentic Behavior

Auditors should be mostly deterministic.

Use agents only for classification where needed, but keep these operations rule-driven:

- file existence
- session liveness
- class counts
- gate pass/fail
- task duplication
- missing provenance

Auditors should not invent resolutions. They should:

- inspect
- compare
- classify
- repair when a safe deterministic fix exists
- escalate when not safe

## Safe Auto-Repairs

Auditors may auto-repair:

- stale active session rows when the session is clearly terminal
- duplicate task files with canonical winner rules
- legacy integrity schema migrations
- active ontology pointer promotion when the target artifact is verified
- repo/runtime projection mismatches

Auditors should not auto-repair:

- missing empirical evidence
- ambiguous source provenance
- conflicting research claims
- data-quality problems requiring human interpretation

## Storage

Audit outputs should be written to:

- `research_plan/audits/`
- `research_plan/decisions/`
- runtime metadata rows

Suggested naming:

- `research_plan/audits/session/{session_id}.md`
- `research_plan/audits/ontology/{timestamp}.md`
- `research_plan/audits/closeout/{timestamp}.md`

## Why This Matters

The soccer project showed that most wasted time came from un-audited drift:

- repo truth vs board truth
- session truth vs runtime truth
- ontology truth vs active pointer truth
- integrity truth vs closeout truth

Auditor agents are the system component that turns those from manual rescue tasks into built-in platform behavior.
