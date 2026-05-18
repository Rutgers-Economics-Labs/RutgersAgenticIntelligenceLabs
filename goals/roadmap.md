# RAIL Roadmap

## What "Done" Means

RAIL is fully autonomous when it can complete the following loop without a meta-operator:

1. clarify the research brief with the user
2. create a compliant repo with `rail.yaml`, ontology scaffolding, specs, and planning structure
3. discover sources and separate real, attachable, manual, and unusable candidates
4. build executable configs, transforms, and pipelines
5. hydrate the ontology and activate the correct artifact
6. verify ontology health
7. run ontology-backed research only on verified data
8. generate papers, dashboards, tables, and figures with provenance
9. audit its own sessions, tasks, integrity state, and closeout state
10. propose follow-up questions grounded in current ontology coverage

This loop must close with no fabricated promotions, no hidden state drift, no manual reconciliation, no ambiguous blockers, and clean audited closeout — on several varied real projects, not just one.

---

## Five Requirements For Full Autonomy

All five must be true at the same time. Progress on four out of five is not enough.

### 1. Audited State Authority

The system must have one authoritative state model. Truth cannot be split across planner rows, repo task files, runtime sessions, ontology artifacts, integrity ledgers, and UI projections. Autopilot advances only from audited reality, not from optimistic heuristics or partial signals.

### 2. Hard Lifecycle Gates

RAIL must reliably stop itself unless each phase is actually satisfied: source discovery, source admissibility, pipeline readiness, hydration success, ontology health, research validity, artifact lineage, and closeout. "Looks mostly done" is not a passing gate.

Lifecycle phases:
`brief → scoped → source_discovery → config_ready → hydration_ready → hydrated → ontology_healthy → research_active → synthesis_ready → closed`

### 3. Automatic Ontology-Backed Question Expansion

A set-and-forget system cannot only finish the current task list. It must classify new questions as answerable now, answerable after requery, answerable after expansion, or blocked by data — then generate the right next tasks without drifting.

### 4. End-To-End Anti-Fabrication Enforcement

No claim promotion without admissible sources. No evidence inflation through summaries. No stale or empty ontology treated as real coverage. No artifact promotion without provenance and a completed verification run.

### 5. Operator-Clear Control Plane

Even when no operator is needed, the system must always be able to explain:
- what phase it is in
- what is actually blocked
- what repair it is attempting
- why it is allowed to advance
- why it considers the project complete

---

## What Is Practically Missing

- ontology auditor as the real authority for readiness and artifact activation
- planner auditor enforcement to suppress drift, ghost tasks, and low-value churn
- durable audit artifacts committed to repo
- single authoritative blocker/phase/next-action projection in API and UI
- automatic ontology expansion planning and follow-up question generation
- closeout certification that is truly self-healing
- repeated success on several different real project types

---

## Milestone Sequence

The nine milestones below build from reliability foundation to full autonomy. Each milestone must ship with unit tests, integration tests, and at least one real example project rerun.

| Milestone | Core Deliverable | Pillar |
|---|---|---|
| 1 — Manifest & Repo Contract | `rail.yaml` schema and validation | 1, 2 |
| 2 — Session Reconciliation | stale/zombie session detection and repair | 1 |
| 3 — Planner/Task Truth | canonical task identity, dedup, supersession | 1 |
| 4 — Ontology Audit Plane | active artifact audit, hydration state, health checks | 1, 2 |
| 5 — Integrity Audit Plane | source admissibility, lineage enforcement, closeout gate | 2, 4 |
| 6 — Post-Run Auditors | session, planner, ontology, integrity, closeout auditors firing automatically | 1, 2 |
| 7 — Question Expansion | classify questions by ontology readiness, generate expansion tasks | 3 |
| 8 — Artifact Excellence | lineage-backed papers, figures, dashboards, and verification certificates | 4 |
| 9 — Controlled Parallelism | branch-isolated workers, ownership contracts, audited merge | 1, 2 |

---

## Required Project Archetypes For Validation

Do not call the platform autonomous until at least several projects of varying type complete cleanly:

1. ontology-heavy public-data project
2. time-series policy/econ project
3. document-heavy literature project
4. manual-ingest or gated-source project
5. midstream-direction-change project
6. multi-expansion ontology project

---

## Current Maturity Estimate (2026-05-18)

- operator-assisted research platform: ~70–80%
- unattended autonomous end-to-end: ~35–50%

The gap is reconciliation, verification, anti-fabrication controls, and lifecycle enforcement — not model capability.

---

## Detailed Specs

- `docs/future-spec-autonomous-platform-roadmap.md` — architecture, planes, anti-fabrication system, audit agents
- `docs/future-spec-implementation-milestones.md` — milestone deliverables by package
- `docs/future-spec-agent-architecture.md` — agent roles and contracts
- `docs/future-spec-rail-yaml-schema.md` — manifest schema
- `docs/future-spec-auditor-agents.md` — auditor agent contracts
- `docs/future-spec-gap-from-original-design.md` — what diverged from the original design
