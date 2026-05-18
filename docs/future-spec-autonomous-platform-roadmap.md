# Future Spec: Autonomous Platform Roadmap

Date: 2026-05-18

## Goal

Make RAIL a genuinely end-to-end autonomous research platform that can:

- accept an open-ended research question
- create and maintain a Git-backed project
- build and expand an ontology-backed graph of knowledge
- discover and vet sources without fabricating evidence
- hydrate real data into the ontology
- generate its own next-best research questions from current ontology coverage
- run coding, analysis, and artifact synthesis safely
- close cleanly only when research, ontology, integrity, and control-plane state agree

This roadmap is deliberately stricter than “more agent automation.” The platform should be trusted to:

- know what it actually knows
- know what it does not know
- avoid made-up sources or fake data
- explain and verify every promotion step

## What “Done” Means For The Platform

RAIL should only be considered “fully autonomous” when it can complete the following loop without a meta-operator:

1. talk to the user and clarify the research brief
2. create a compliant repo with `rail.yaml`, ontology scaffolding, specs, and planning structure
3. discover sources and separate real, attachable, manual, and unusable source candidates
4. build executable source configs, transforms, and pipelines
5. hydrate the ontology and activate the correct artifact
6. verify ontology health
7. run ontology-backed research only on verified data
8. generate papers, dashboards, tables, and figures with provenance
9. audit its own sessions, tasks, integrity state, and closeout state
10. propose follow-up questions grounded in current ontology coverage

Today, RAIL can do much of this with supervision. The gap is autonomous reconciliation and verification.

## Core Principles

### 1. Git is the durable truth

The repo is authoritative for:

- project knowledge
- ontology configuration
- research artifacts
- planning state
- repo-local skills
- project specs

The database should only store operational metadata such as:

- session id
- runner
- API cost
- start/end time
- runtime status
- secret handles

### 2. Every claim must be attributable

The platform must not promote analysis based on:

- uncited claims
- placeholder data
- fabricated sources
- synthetic values disguised as observed data
- stale active ontology pointers

### 3. Worker output is not trusted until audited

An agent run should produce candidate reality. The system should only advance once auditors reconcile candidate reality against:

- repo files
- active ontology artifacts
- integrity records
- actual session liveness
- task acceptance criteria

### 4. The ontology and folder graph are linked, not interchangeable

The ontology is the machine-queryable graph.

The `topics/` tree is the human-readable knowledge graph.

The platform should explicitly maintain links between:

- source note -> source config
- topic note -> claim
- artifact -> scripts
- ontology class -> analysis output
- research question -> ontology coverage state

## Main Problems To Solve

### A. State fragmentation

Current truth is split across:

- repo files
- planner board rows
- task markdown
- session records
- active ontology pointers
- integrity ledgers
- UI projections

This must converge into one authoritative state model with derived projections.

### B. Weak verification loops

Today the platform often verifies too late, too narrowly, or against stale state.

Needed improvement:

- verify after each batch
- verify before every phase transition
- verify before artifact promotion
- verify before project closeout

### C. Fabrication risk in research flows

Research agents can currently over-summarize or infer too confidently unless stronger source-grounding contracts exist.

Needed improvement:

- structured evidence capture
- source admissibility rules
- confidence typing
- claim promotion rules

### D. Hydration and ontology health are still too easy to bypass

The system must treat ontology health as a hard gate.

### E. Closeout is not yet self-healing

Final synthesis should not require manual reconciliation of:

- claims
- source provenance
- lineage
- stale sessions
- board drift

## The Architecture We Need

## 1. Four Planes

### Repo plane

Durable project content:

- `.ontology/`
- `topics/`
- `specs/`
- `research_plan/`
- `skills/`
- `agents/`
- `artifacts/`

### Runtime plane

Ephemeral execution state:

- live sessions
- runner metadata
- costs
- approvals in flight
- secret injection

### Audit plane

The new required layer:

- session reconciliation
- planner reconciliation
- ontology artifact reconciliation
- integrity reconciliation
- closeout certification

### Projection plane

UI views derived from repo + audited runtime state:

- planner board
- ontology health
- artifact explorer
- current blocker
- session timeline
- research coverage map

## 2. Lifecycle Contract

All projects should move through this enforced lifecycle:

1. brief
2. scoped
3. source_discovery
4. config_ready
5. hydration_ready
6. hydrated
7. ontology_healthy
8. research_active
9. synthesis_ready
10. closed

The platform should reject transitions that skip required evidence.

## 3. Audit Agents

These are now mandatory, not optional.

### session_auditor

Checks:

- stale sessions
- zombie PIDs
- completed-but-unreconciled work
- duplicate sessions
- lane occupancy

Outputs:

- reconcile to completed
- cancel duplicate
- clear stale running state

### planner_auditor

Checks:

- task duplication
- truncated task ids
- task acceptance vs repo evidence
- superseded tasks
- blocked vs ready correctness

Outputs:

- mark done
- mark blocked
- supersede
- dedupe

### ontology_auditor

Checks:

- active ontology artifact
- hydrated counts
- empty/non-empty expectations
- class availability
- active artifact pointer correctness

Outputs:

- promote artifact
- mark hydration stale
- mark hydration healthy
- trigger rerun or repair

### integrity_auditor

Checks:

- source provenance
- freshness status
- claim schema validity
- lineage completeness
- verification-run coverage
- artifact promotion state

Outputs:

- normalize legacy records
- mark unsupported claims
- block promotion
- certify promotable artifacts

### closeout_auditor

Checks:

- no active required sessions
- no non-done required tasks
- final integrity gate clean
- final artifact set present
- ontology active and healthy

Outputs:

- closeout certificate
- reopen required lane if anything still fails

## 4. Anti-Fabrication System

This is one of the most important things to build.

The platform needs a formal “evidence admissibility” policy.

### Source tiers

Every source must be explicitly typed as:

- official structured
- official unstructured
- third-party structured
- third-party unstructured
- local manual ingest
- candidate only
- rejected

Only admitted sources should be allowed to support promoted claims.

### Claim statuses

Claims should be typed as:

- draft
- supported
- unsupported
- needs_evidence
- stale
- conflicted
- superseded

No final artifact should cite a `draft` or `needs_evidence` claim without explicit caveat labeling.

### Evidence requirements

Every promoted claim should have:

- evidence path(s)
- source key(s)
- evidence kind
- confidence value
- caveats
- open questions if relevant

### Data provenance rules

Every dataset should record:

- upstream source
- acquisition method
- retrieval time
- transform or script path
- verification run
- promotion state

### Fabrication detectors

Add explicit checks for:

- source keys referenced but not defined
- source URLs that do not resolve or were never fetched
- claims with no evidence paths
- reports that mention metrics not present in the ontology
- tables or figures with no lineage

## 5. Ontology Expansion System

The platform should not only answer a fixed question. It should expand the ontology when new questions require it.

Each new question should be classified as:

- answerable_now
- answerable_after_requery
- answerable_after_expansion
- blocked_by_data

If expansion is required, the planner must generate:

- expansion rationale
- source acquisition task
- schema extension task
- transform task
- hydration task
- ontology health task
- downstream research task

This is the mechanism that lets the platform “find its own next questions” from current ontology coverage.

## 6. Research Question Generation

After every successful hydration or ontology expansion, the platform should generate follow-up questions by inspecting:

- available classes
- measures
- time coverage
- geography or competition coverage
- joinable entity sets
- current research gaps

Each proposed question should be scored by:

- scientific value
- data readiness
- ontology completeness
- expansion cost
- reproducibility risk

The system should not propose questions that require invented data or unsupported inference.

## 7. Artifact Synthesis System

Artifacts should be downstream of verified research, not parallel to it.

Every final artifact should declare:

- which question it answers
- which ontology version it depends on
- which datasets it uses
- which scripts or notebooks produced it
- which verification run certified it

The artifact layer should support:

- markdown reports
- LaTeX papers and PDFs
- HTML dashboards
- figures
- tables
- exported data panels

No final paper should be generated without ontology-backed tables or figures if the task is empirical.

## 8. Session and Runner Strategy

Short term:

- one agent at a time
- strong reconciliation
- no parallel branches unless audited state is already reliable

Medium term:

- multi-branch workers with disjoint ownership
- merge gates
- automated conflict detection
- audited integration step before promotion

Jules or Claude Code cloud workers are compatible with this architecture, but only if session outputs are treated as candidate state until audited.

## What To Build First

## Phase 1: Reliability Foundation

1. Add a strict `rail.yaml` contract
2. Add post-run audit hook before autopilot advances
3. Unify canonical task identity and dedupe rules
4. Add stale-session and zombie-session reconciliation
5. Add active ontology artifact reconciliation

Success criteria:

- no duplicate task drift
- no stuck lane from stale sessions
- no stale active ontology pointers

## Phase 2: Strong Verification Loops

1. Add lifecycle gates
2. Add integrity auditor
3. Add source admissibility policy
4. Add artifact-lineage enforcement
5. Add closeout auditor

Success criteria:

- no final artifact promotion with broken provenance
- no research completion before ontology health
- no manual closeout repair needed

## Phase 3: Ontology Expansion And Follow-Up Questions

1. Add question classification against current ontology
2. Add ontology expansion task generation
3. Add follow-up question scoring and queueing
4. Add coverage explorer in UI

Success criteria:

- user can redirect project midstream
- planner can propose good next questions
- ontology can grow intentionally

## Phase 4: Artifact Excellence

1. Final ontology-backed LaTeX paper pipeline
2. figure-generation pipeline tied to analysis outputs
3. dashboard generator tied to verified datasets
4. artifact reproducibility certificates

Success criteria:

- figures and tables are lineage-backed
- final papers are empirical and reproducible

## Phase 5: Controlled Multi-Agent Parallelism

1. branch-based worker isolation
2. ownership and merge contracts
3. audited integration workers
4. branch conflict visibility in UI

Success criteria:

- more throughput without state chaos

## How Many Example Projects Are Needed

To make this real, RAIL needs more than one successful project but not dozens before the architecture is clear.

Recommended target:

- `3-5` serious projects to expose the dominant failure modes
- `8-12` diverse projects to make the platform robust

The project mix should include:

- ontology-heavy public-data project
- policy/econ series project
- document-heavy research project
- manual-ingest or gated-source project
- project with midstream question changes
- project requiring multiple ontology expansions

## Current Maturity Estimate

Based on the soccer project:

- assisted operator-driven research platform: strong
- ontology-backed research engine: moderately strong
- self-healing autonomous platform: not there yet

Approximate maturity:

- operator-assisted: `70-80%`
- unattended autonomous end-to-end: `35-50%`

The gap is mostly:

- reconciliation
- verification
- anti-fabrication controls
- lifecycle enforcement

not pure model capability.

## Final Recommendation

The most important upgrade is not another worker role.

It is this rule:

> No planner, autopilot, or closeout transition should advance from raw worker output. Everything advances from audited project reality.

Once that is true, the rest of the system becomes much easier to trust, automate, and scale.
