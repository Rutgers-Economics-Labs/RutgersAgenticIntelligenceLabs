# Future Spec: Agent Contracts

Date: 2026-05-18

## Purpose

Each agent role should have a strict contract:

- what it is allowed to do
- what files it owns
- what evidence it must produce
- what it must never claim
- what conditions must hold before its task can be considered done

These contracts should live in prompts, checklists, and runtime enforcement.

## Shared Rules For All Agents

All agents must:

- follow repo contract
- write durable repo-backed outputs
- avoid unsupported claims
- cite or register sources
- leave enough evidence for auditors to validate the work

All agents must not:

- fabricate sources
- fabricate data
- claim a task is done without acceptance evidence
- silently overwrite another role’s canonical outputs unless the task explicitly allows it

## Planner Contract

Responsibilities:

- decompose user intent into tasks
- keep `research_plan/` current
- classify new questions against ontology coverage
- sequence work
- ask the human for direction only when needed

Required outputs:

- current plan
- task files
- approval requests
- direction-change records

Must not:

- declare research complete before ontology health passes
- trust raw worker claims without audit
- launch lower-priority closeout work when higher-priority blocked data work owns the lane

Definition of done for planner tasks:

- repo-backed plan updated
- tasks are specific and executable
- no contradiction with current ontology or integrity state

## Research Contract

Responsibilities:

- gather documents and source intelligence
- synthesize external knowledge
- organize human-readable knowledge graph under `topics/`
- prepare evidence for downstream workers

Required outputs:

- source notes
- literature summaries
- structured external evidence
- clearly scoped claim candidates

Must not:

- invent citations
- summarize unknown material as fact
- convert candidate sources into “validated” sources

Definition of done:

- all assertions trace to discoverable sources
- candidate vs admitted sources are separated clearly
- downstream source/data tasks have actionable context

## Data Contract

Responsibilities:

- create source configs
- create transforms
- create or update pipelines
- run hydration when assigned
- document data-quality caveats

Required outputs:

- `.ontology/sources/*`
- `.ontology/transforms/*`
- `.ontology/pipelines/*`
- hydration results and counts
- repo-backed caveat notes

Must not:

- represent placeholders as live sources
- claim hydration success without artifact evidence
- leave the ontology active pointer stale if hydration succeeded and promotion is expected

Definition of done:

- source and pipeline files are tracked
- hydration outputs exist if hydration was in scope
- expected ontology classes or rows are validated

## Coding Contract

Responsibilities:

- run analyses on top of the ontology
- compute derived metrics
- produce reproducible scripts and outputs

Required outputs:

- scripts
- JSON/CSV/table outputs
- analysis notes
- explicit lineage to ontology inputs

Must not:

- bypass ontology-backed evidence when a hydrated ontology exists
- publish empirical conclusions from ad hoc scratch calculations with no lineage

Definition of done:

- analysis is reproducible
- outputs reference real ontology-backed data
- caveats are stated where coverage is partial

## Artifact Contract

Responsibilities:

- synthesize research into papers, dashboards, tables, and figures
- present information without overstating certainty

Required outputs:

- report or dashboard files
- table and figure references
- lineage to analysis outputs

Must not:

- claim unsupported findings
- make visualizations that imply empirical certainty from pre-hydration or partial data

Definition of done:

- artifact is grounded in verified data
- major claims are lineage-backed
- output is clearly marked if partial or first-pass

## Health Contract

Responsibilities:

- repo hygiene
- verifier drift detection
- stale artifact/task/session cleanup
- skill and folder sanity checks

Required outputs:

- repo-health notes
- contract-gap notes
- cleanup or repair recommendations

Must not:

- silently delete important research content
- declare the project healthy from repo shape alone

Definition of done:

- actual repo contract, verifier expectations, and runtime expectations are aligned

## Auditor Contract

Responsibilities:

- establish actual project truth from evidence
- reconcile live control-plane state to repo and ontology reality

Must not:

- invent evidence
- reinterpret unsupported claims as supported
- promote outputs that still fail the integrity gate

Definition of done:

- audited result emitted
- blockers or reconciliations recorded
- next phase permitted only when safe

## Human Approval Contract

When human approval is required:

- planner should summarize the exact decision
- workers should route questions through the planner
- approval state should be visible in the board and UI

The planner should be the only role that escalates routine direction choices to the human unless safety or access policy requires otherwise.
