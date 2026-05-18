# Future Spec: Implementation Milestones

Date: 2026-05-18

## Goal

Translate the future-spec docs into a realistic implementation sequence across:

- `packages/api`
- `packages/rail-py`
- `packages/engine`
- `apps/web`

## Milestone 1: Manifest And Repo Contract

### Deliverables

- initial `rail.yaml` schema
- repo-contract validation
- default pipeline declaration
- planner roots declaration

### Package focus

#### `packages/rail-py`

- manifest loader updates
- local-mode project contract validation

#### `packages/api`

- API-side manifest validation
- project bootstrap endpoints honor new fields

#### `apps/web`

- project summary page shows manifest-derived basics

## Milestone 2: Session Reconciliation

### Deliverables

- stale-session detection
- zombie process detection
- file-backed completed-session reconciliation
- execution-lane availability logic

### Package focus

#### `packages/api`

- runner lifecycle
- CLI runner reconciliation
- cancellation and finalize paths

#### `packages/rail-py`

- session-state normalization helpers

## Milestone 3: Planner/Task Truth

### Deliverables

- canonical task identity rules
- duplicate task-file prevention
- supersession rules
- audited task completion

### Package focus

#### `packages/api`

- planner service
- task-state reconciliation
- board projection rules

#### `apps/web`

- evidence-backed task view
- stale/duplicate indicators

## Milestone 4: Ontology Audit Plane

### Deliverables

- active artifact audit
- hydration state classification
- ontology health checks
- promotion of verified local reusable artifacts

### Package focus

#### `packages/api`

- hydration registry
- ontology endpoints
- autopilot phase gating

#### `packages/rail-py`

- local hydrate alignment
- ontology-health helper commands

#### `apps/web`

- ontology coverage explorer
- artifact active/stale indicators

## Milestone 5: Integrity Audit Plane

### Deliverables

- source admissibility policy
- legacy schema normalization
- artifact-lineage enforcement
- closeout gate stabilization

### Package focus

#### `packages/rail-py`

- integrity model migrations
- claim/source/lineage validation

#### `packages/api`

- integrity gate surfaces
- API audit endpoints

#### `apps/web`

- integrity plane UI
- per-artifact provenance and verification view

## Milestone 6: Post-Run Auditors

### Deliverables

- `session_auditor`
- `planner_auditor`
- `ontology_auditor`
- `integrity_auditor`
- `closeout_auditor`

### Package focus

#### `packages/api`

- orchestration hooks
- audit job execution
- audit result storage

#### `packages/rail-py`

- reusable audit logic

#### `apps/web`

- audit timeline
- “why blocked” panels

## Milestone 7: Question Expansion Logic

### Deliverables

- classify new questions by ontology readiness
- create expansion tasks automatically
- generate follow-up questions from ontology coverage

### Package focus

#### `packages/api`

- planner runtime and autopilot logic

#### `packages/rail-py`

- ontology coverage utilities

#### `apps/web`

- question intake
- expansion proposal UI

## Milestone 8: Artifact Excellence

### Deliverables

- final LaTeX paper pipeline
- figure-generation pipeline
- dashboard lineage and reproducibility
- artifact verification certificate

### Package focus

#### `packages/api`

- artifact synthesis orchestration

#### `packages/engine`

- deterministic data export and figure helpers

#### `apps/web`

- artifact gallery with trust levels

## Milestone 9: Controlled Multi-Agent Parallelism

### Deliverables

- branch-isolated workers
- ownership declarations
- audited merge step
- conflict-aware UI

### Package focus

#### `packages/api`

- workspace creation and merge orchestration

#### `apps/web`

- branch/session visibility
- merge decision UI

## Testing Expectations

Every milestone should ship with:

- unit tests
- integration tests
- at least one real example project rerun
- explicit regression tests for previously observed failure modes

## Required Example Projects

Use these project archetypes as milestone validation:

1. ontology-heavy public-data project
2. time-series policy/econ project
3. document-heavy literature project
4. manual-ingest project
5. midstream-direction-change project
6. multi-expansion ontology project

## Success Threshold

Do not call the platform autonomous until it can complete at least several varied projects with:

- no meta-operator reconciliation
- no fabricated source or claim promotions
- clean closeout audits
- stable planner/board/runtime convergence
