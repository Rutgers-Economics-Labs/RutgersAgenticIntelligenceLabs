# Build Queue

Current remaining gaps after the `yaml-driven-hydration` stabilization pass.

This file tracks work that is still meaningfully unfinished. Items that were already built in this branch have been removed from the old queue.

---

## Immediate Follow-up

### A. Verification Stability
- Keep Python and frontend tests aligned with the current product routes and agent/session model.
- Prefer fixing stale assertions and unsupported test assumptions over preserving legacy route expectations.
- Document the supported local verification flow for `rail-py` so root-level acceptance checks work without ad hoc shell state.

### B. Hydration Follow-through
- Add automatic quality snapshots after successful hydration runs.
- Decide whether successful hydration should surface more derived-artifact status in the UI beyond current logs and job status.
- Audit pipeline validation against all checked-in example configs whenever schema fields evolve.

---

## Product Gaps Still Open

### 1. Project Manifest / `rail.yaml`
**Spec:** `specs/projects.md`
- Define `rail.yaml` as a real source of truth and wire parsing/sync into project lifecycle flows.
- Decide how manifest state interacts with Convex project records and GitHub sync.

### 2. Ontology Template Depth
**Spec:** `specs/ontology-kernel.md`
- Seed stronger ontology template coverage, including platform-oriented templates such as `platform-objects`.
- Tighten template application in project creation so chosen templates materially affect the initial project state.

### 3. Connector Catalog Depth
**Spec:** `specs/connectors.md`
- Expand the seeded connector template library so the registry is useful without manual template authoring.
- Decide how `connectorTemplates` and `dataSourceRegistry` should relate long term.

### 4. GitHub Sync Hardening
**Spec:** `specs/projects.md`, `specs/api.md`
- Improve sync-status accuracy beyond the current placeholder `in_sync: true`.
- Harden publish/sync idempotency, diff visibility, and branch-awareness.

### 5. Automatic Quality / Monitoring Hooks
**Spec:** `specs/data-quality.md`, `specs/schedule.md`
- Auto-create quality snapshots on successful hydration and scheduled runs.
- Surface quality drift and freshness changes closer to jobs/pipelines workflows.

### 6. IRI Convention Cleanup
**Spec:** `specs/ontology-kernel.md`
- Decide whether to migrate fully to the canonical RAIL namespace.
- If yes, plan a backward-compatible migration for existing ontologies and references.

---

## Midterm Improvements

See `specs/improvements.md` for the broader roadmap. The highest-signal items still look like:

1. Object-property join tables in DuckDB export
2. Cross-project SQL / attached DuckDB analysis
3. Ontology migration tooling
4. Pluggable triple-store backend
5. Unstructured-data pipeline integration
