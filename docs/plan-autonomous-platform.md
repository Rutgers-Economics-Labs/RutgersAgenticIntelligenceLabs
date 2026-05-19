# Plan: RAIL Fully Autonomous Research Platform

Date: 2026-05-19  
Branch: `future`  
Specs: `docs/future-spec-*.md`, `docs/future-spec-implementation-milestones.md`

## North star

RAIL is done when it can run this loop **without a meta-operator**, on **several varied real projects**:

1. Clarify brief → compliant repo (`rail.yaml`, ontology, plan)
2. Discover/classify sources (real / attachable / manual / rejected)
3. Build configs, transforms, pipelines
4. Hydrate ontology → activate verified artifact
5. Verify ontology health
6. Research only on verified data
7. Produce paper, tables, figures, HTML dashboard with provenance
8. Post-run auditors certify session, planner, ontology, integrity, closeout
9. Propose grounded follow-up questions; auto-generate expansion task chains

**Success bar** (from specs): no fabricated promotions, no hidden state drift, no manual reconciliation, clean closeout, stable planner/board/runtime convergence — on at least **six archetypes** (see validation matrix below).

---

## Current state (honest)

| Area | Maturity | Notes |
|------|----------|--------|
| Manifest & repo contract | ~90% | M1 on `future`: boot validation, integration tests |
| Session reconciliation | ~85% | M2: zombie/stale repair, lane policy; wired at runner launch |
| Planner/task truth | ~75% | Dedupe, reconcile, session→task sync exist; some test/UI drift |
| Ontology audit plane | ~70% | Hydration registry, health checks; autopilot gating partial |
| Integrity audit plane | ~70% | Admissibility, lineage, closeout gate; legacy schema edges |
| Post-run auditors | ~75% | Five auditors + `reconcile_project_reality`; Convex mocked in validation script |
| Question expansion | ~70% | `question_expansion_service` + autopilot hooks; live script updated |
| Artifact excellence | ~50% | Pipelines exist; not consistently E2E on real agent runs |
| Controlled parallelism | ~30% | Single-lane default; M9 not production-ready |
| Live unattended E2E | ~40% | `validate_autonomous_loop.py` passes 3 archetypes with mocked Convex |

**Rule:** Do not declare autonomy from `validate_autonomous_loop.py` alone. It proves file-based audit machinery, not a live autopilot tick with real workers.

---

## Architecture principle (non-negotiable)

```
Workers → candidate state → Audit plane → certified reality → Autopilot → (one lane) → Workers
```

- Workers produce **candidates** only.
- **Auditors** certify reality (`reconcile_project_reality` → `build_auditor_statuses`).
- **Autopilot** advances **only** from auditor output, never from heuristics or partial signals.

---

## Phase plan (milestones 1–9)

### Phase A — Reliability foundation (M1–M4)

**Goal:** No stuck lanes, no duplicate tasks, no stale ontology pointers.

| # | Milestone | Remaining work |
|---|-----------|----------------|
| 1 | Manifest & repo contract | Web UI manifest summary; align spec `ontology:` vs `hydration`+`paths` (doc or alias) |
| 2 | Session reconciliation | Lane gating done; expose lane status on API/UI |
| 3 | Planner/task truth | Fix autopilot test drift; UI stale/duplicate indicators |
| 4 | Ontology audit plane | Enforce `default_pipeline` for ontology-first at boot; autopilot gates from ontology auditor only |

**Exit criteria:** M1–M4 tests green; one validation project rerun per milestone with no manual reconcile.

### Phase B — Verification loops (M5–M6)

**Goal:** Nothing promotes without admissible sources, lineage, and verification runs.

| # | Milestone | Remaining work |
|---|-----------|----------------|
| 5 | Integrity audit plane | Stabilize closeout gate; legacy schema normalization; integrity UI |
| 6 | Post-run auditors | Hook every worker finalize path to `write_post_run_audit`; audit timeline in API/UI |

**Exit criteria:** Validation script + one live session (real Convex) show all five auditors `ready` before closeout.

### Phase C — Expansion & synthesis (M7–M8)

**Goal:** Midstream redirects and ontology-backed deliverables.

| # | Milestone | Remaining work |
|---|-----------|----------------|
| 7 | Question expansion | Autopilot always calls `_ensure_ontology_expansion_tasks`; all four classification classes |
| 8 | Artifact excellence | E2E LaTeX/markdown paper, DuckDB figures, HTML dashboard, verification certificate |

**Exit criteria:** Artifacts with lineage; closeout passes with expansion tasks satisfied.

### Phase D — Scale safely (M9)

**Defer until A–C pass.** Branch isolation, ownership, audited merge, conflict UI.

---

## Validation matrix (required archetypes)

| Archetype | Primary stress | Pass definition |
|-----------|----------------|-----------------|
| 1. Ontology-heavy public data | FRED/API hydrate | Closeout clean; DuckDB populated; no fake sources |
| 2. Time-series policy/econ | e.g. `nj-housing-rates-study` | Claims tied to series; paper + dashboard |
| 3. Document-heavy literature | No `.ontology` initially | Integrity without ontology or explicit skip |
| 4. Manual-ingest | PDFs/uploads | Source typing + admissibility |
| 5. Midstream direction change | Brief pivot | Planner supersession; no duplicate tasks |
| 6. Multi-expansion ontology | Follow-up questions | Expansion tasks created and completed |

**Per archetype checklist:**

- [ ] `boot_validate_project` passes at activate
- [ ] `reconcile_project_reality` → no uncertified drift after each worker
- [ ] All five auditors `ready` before synthesis
- [ ] `closeout_auditor` issues certificate
- [ ] Zero operator edits to integrity state or task files

---

## Execution order

### Sprint 1 — Close the control plane (done)

1. ~~Fix remaining autopilot service test failures.~~
2. ~~API: `GET /projects/{slug}/reality` — `project_reality_status` + lane availability.~~
3. ~~Autopilot: `load_validated_manifest()` on every tick; block launch if lane unavailable.~~
4. Post-run audit on all runner finalize paths (CLI + cloud) — verify in Sprint 2 live run.

Shipped: `62575dc` on `future`.

### Sprint 2 — First live E2E (in progress)

**Stack:** API + Convex + `FRED_API_KEY`, `localRepoPath` → validation project.

1. ~~Hydrate FRED pipeline (real).~~ Done via `run_live_agent_loop.py`
2. ~~Run planner + research + audits + expansion tasks.~~ Done (Gemini + FRED)
3. Closeout demo: `python scripts/run_live_agent_loop.py --defer-expansion` (cancels auto expansion tasks for audit pass)
4. **Remaining:** API + Convex project registration, live autopilot tick, artifact/HTML dashboard (Sprint 3)
5. Runbook: `docs/validation/nj-housing-affordability/README.md`

### Sprint 3 — Artifact excellence + archetypes 4–6

1. Harden artifact / figure pipelines.
2. Run manual-ingest, midstream-pivot, multi-expansion projects.
3. Fix only the blocker class per failure.

### Sprint 4 — M9 parallelism (optional)

Only after six archetypes pass unattended once.

---

## What not to do

- Do not add features outside the milestone sequence.
- Do not advance autopilot from task board heuristics.
- Do not mark closed without `closeout_auditor` certificate.
- Do not treat Convex-mocked validation as full autonomy proof.
- Do not start M9 before single-lane E2E is stable.

---

## Spec reading guide

| Milestone | Read first |
|-----------|------------|
| M3 | `docs/future-spec-autonomous-platform-roadmap.md` |
| M4 | Roadmap + hydration registry contracts |
| M5–6 | `docs/future-spec-auditor-agents.md` |
| M7 | Roadmap question expansion + `question_expansion_service.py` |
| M8 | `docs/future-spec-implementation-milestones.md` § Milestone 8 |
| Gaps | `docs/future-spec-gap-from-original-design.md` |

---

## Progress log

| Date | Item | Status |
|------|------|--------|
| 2026-05-19 | M1 manifest boot validation | Shipped (`4ad61ab`) |
| 2026-05-19 | M2 session reconciliation + lane gating | Shipped (`5293837`) |
| 2026-05-19 | Live loop expansion tasks (M7 script) | Shipped (`a7afb7f`) |
| 2026-05-19 | This plan document | Created |
| 2026-05-19 | Sprint 1 control plane | Shipped (`62575dc`) |
| 2026-05-19 | Sprint 2 live loop (FRED + Gemini) | Shipped (`041a4c9`, `38cf1d7`) |
| 2026-05-19 | Live loop all auditors ready (`--defer-expansion`) | Verified |
| 2026-05-19 | `validate_autonomous_loop.py` (3 archetypes) | PASS |
