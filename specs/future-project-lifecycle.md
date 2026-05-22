# Future Project Lifecycle

This document defines the end-to-end lifecycle for completing a research project in future RAIL.

Its purpose is to make one boundary explicit:

- agents are allowed to explore, test methods, and draft interpretations
- trusted project state only advances when exploratory work is promoted into structured records and passes the truth loops

This lifecycle sits on top of the stable ontology and hydration kernel.

## Core Principle

RAIL should not force every exploratory note, hypothesis, or script directly into the ontology as if it were already trusted fact.

Instead, the system should distinguish between:

- `exploration`
- `structured registration`
- `trusted promotion`

This allows the project to remain creative without letting unstructured or unsupported work silently become canonical.

## Two Zones

### 1. Flexible Exploration Zone

This is where agents can try new things.

Typical locations:

- `topics/`
- worker-local notes
- draft scripts
- draft markdown
- candidate charts
- semantic retrieval results
- source leads

Typical properties:

- useful but not yet trusted
- may contain incomplete synthesis
- may include semantic leads that still need explicit evidence
- may be revised or discarded without affecting trusted project state

### 2. Structured Truth Zone

This is where research becomes durable and promotable.

Typical locations:

- `.ontology/ontology.yaml`
- `.ontology/sources/*.yaml`
- `.ontology/pipelines/*.yaml`
- `research_plan/state/sources.json`
- `research_plan/state/claims.json`
- `research_plan/state/assumptions.json`
- `research_plan/state/artifact_lineage.json`
- `research_plan/state/verification_runs.json`
- `research_plan/state/evidence_chunks.json`
- `research_plan/state/integrity_edges.json`

Typical properties:

- versioned
- explicit
- traversable
- reviewable
- eligible for verification
- used by the planner, health agent, and integrity surfaces

## Canonical State Machine

The project lifecycle should be modeled as a promotion graph rather than a single linear checklist.

```text
idea
  -> source_candidate
  -> structured_source
  -> hydrated_dataset
  -> claim_candidate
  -> supported_claim
  -> draft_artifact
  -> needs_evidence | partially_verified | verified
  -> stale
  -> rerun_or_revalidate
  -> partially_verified | verified | blocked
```

This graph exists at multiple levels:

- source level
- dataset level
- claim level
- artifact level

The planner's job is to keep each important research object moving forward through the graph or explicitly record why it is blocked.

## Research Object States

### Source Lifecycle

1. `source_candidate`
   - discovered in search, papers, docs, or prior notes
   - may exist only in `topics/` or planner notes

2. `structured_source`
   - recorded in `.ontology/sources/*.yaml` when intended for hydration
   - or recorded in `research_plan/state/sources.json` when it is a manual/documentary source

3. `current_source`
   - provenance is present
   - freshness and quality status are recorded

4. `stale_source`
   - freshness window expired or upstream changed materially

5. `blocked_source`
   - source is invalid, conflicting, unavailable, or policy-disallowed

### Dataset Lifecycle

1. `planned_dataset`
   - expected output from hydration or analysis

2. `hydrated_dataset`
   - file exists and generation completed

3. `lineaged_dataset`
   - sources and generation method are recorded in `artifact_lineage.json`

4. `verified_dataset`
   - provenance and verification gates pass

5. `stale_dataset`
   - upstream source, script, or assumption changed

### Claim Lifecycle

1. `claim_candidate`
   - drafted by research or coding work
   - may emerge from literature review, analysis, or interpretation

2. `registered_claim`
   - claim is written into `research_plan/state/claims.json`
   - has a stable `claim_key`

3. `supported_claim`
   - explicit evidence is attached
   - not merely semantic suggestion

4. `conflicted_claim`
   - contradicted by other explicit support or conflicting source state

5. `stale_claim`
   - upstream source became stale or the supporting analysis changed

### Artifact Lifecycle

1. `exploratory_artifact`
   - useful draft output
   - not trusted by default

2. `lineaged_artifact`
   - listed in `artifact_lineage.json`
   - inputs, sources, claims, assumptions, and scripts are declared as applicable

3. `needs_evidence`
   - narrative exists but important claims are not sufficiently backed

4. `partially_verified`
   - some checks passed, but trust is still conditional

5. `verified`
   - evidence, provenance, and reproducibility gates pass

6. `stale`
   - dependencies changed after generation

7. `blocked`
   - unresolved integrity or policy blocker prevents promotion

## Promotion Boundaries

The system should require explicit promotion across four boundaries.

### Boundary 1: Lead -> Source

A discovered lead becomes a project source only when the agent records:

- source identity
- origin
- acquisition method
- timestamp or access time
- freshness status or explicit unknown state

If it should drive hydration, it must also be formalized in `.ontology/sources/*.yaml`.

### Boundary 2: Note -> Claim

A note or interpretation becomes a project claim only when the agent records:

- `claim_key`
- `claim_text`
- linked sources and/or evidence chunks
- evidence kind
- caveats or open questions when needed

This is the key boundary between prose and research state.

### Boundary 3: Output -> Artifact

A chart, memo, report, or dataset becomes a tracked artifact only when the agent records:

- artifact path
- artifact type
- inputs
- scripts or methods
- sources
- claims
- assumptions

This is the key boundary between file creation and durable lineage.

### Boundary 4: Artifact -> Trusted Artifact

A tracked artifact becomes trusted only when:

- important claims are evidence-backed
- upstream sources are current enough for policy
- reproducibility requirements are satisfied or explicitly waived
- verification runs are recorded

## Role Responsibilities Across the Lifecycle

### Planner

Owns:

- deciding what research objects matter enough to promote
- assigning the next role
- recording blockers when an object cannot advance
- deciding when a project is complete enough to stop

### Research

Owns:

- converting raw exploration into source candidates, claim candidates, caveats, and open questions
- separating facts from interpretation
- ensuring important claims reach `registered_claim` rather than remaining trapped in prose

### Data

Owns:

- converting promising sources into ontology-backed source and pipeline definitions
- making datasets reproducible and provenance-bearing
- keeping source freshness state current

### Coding

Owns:

- converting hydrated data into reproducible outputs
- attaching methods, inputs, and verification commands
- promoting analytical results from files to tracked datasets or artifacts

### Artifact

Owns:

- converting draft outputs into user-facing deliverables
- preserving evidence links and trust labels instead of collapsing everything into polished prose

### Health

Owns:

- enforcing that promoted work crossed the required boundaries
- preventing unverifiable or stale research objects from being treated as done

## End-to-End Project Flow

The intended project completion flow is:

1. Bootstrap the project.
2. Planner defines the first approved objective and task sequence.
3. Research agent explores the domain and produces source leads, structured findings, and claim candidates.
4. Data agent formalizes important sources and hydration mappings into `.ontology/`.
5. Hydration produces deterministic datasets and ontology-backed state.
6. Coding agent runs analysis and records inputs, methods, assumptions, and outputs.
7. Artifact agent packages findings into reports, memos, dashboards, or visualizations with evidence links.
8. Session review syncs structured outputs into the integrity ledgers.
9. Health and deterministic verification evaluate the three truth loops.
10. Planner either:
   - promotes the result,
   - routes repair work,
   - or records a blocker.
11. The project is only considered complete when the required user-facing artifacts are either:
   - `verified`, or
   - explicitly left exploratory with disclosed caveats by project policy.

## What “Done” Means

A research project is done when:

- required sources are recorded and usable
- key datasets are hydrated or explicitly unavailable with blockers recorded
- important claims are explicit and evidence-backed
- required artifacts exist
- trusted artifacts are promoted through the integrity gates
- unresolved gaps are either closed or explicitly surfaced as known limitations

“Done” should not mean:

- every interesting avenue has been explored
- every note has been ontologized
- every draft file is perfect

It means the project has a trustworthy, inspectable, and reproducible research spine.

## Current Implementation Direction

The current codebase already partially supports this lifecycle through:

- isolated worker workspaces
- role-specific workflow contracts
- integrity ledgers under `research_plan/state/`
- explicit dependency edges
- hybrid retrieval over chunks plus explicit graph edges
- promotion states such as `exploratory`, `needs_evidence`, `partially_verified`, `verified`, `stale`, and `blocked`

The remaining architectural task is to make the planner treat promotion across these boundaries as first-class project logic rather than as scattered implementation details.
