# RAIL Autonomous Loop Validation Report

**Date:** 2026-05-19 (updated)
**All archetypes passed:** True
**FRED API used:** True (real HTTP calls)
**Zero fabricated sources:** True
**Zero meta-operator reconciliation:** True
**Success threshold met:** True (4 real archetypes + autopilot loop proofs)

## Summary

RAIL's autonomous loop has been validated across **four varied project archetypes** using real agent execution and real external data, plus autopilot loop proofs that show the platform (not an operator) drives launch → audit → closeout. The success threshold — at least three varied archetypes with zero meta-operator reconciliation, zero fabricated promotions, clean closeout audits, and stable planner/runtime convergence — is met.

---

## Category A — Gemini CLI Agent Sessions (Three New Archetypes)

Three projects were run end-to-end by a real Gemini CLI agent (gemini-2.5-flash, approval-mode: yolo) writing files directly to project directories. Platform handled repo bootstrap, FRED hydration, and post-run auditors. All 6 sessions per project passed all five auditors.

| Project | Archetype | Sessions | DuckDB Rows | All Auditors Ready |
|---------|-----------|----------|-------------|-------------------|
| nj-housing-rates-study | time-series-econ | 6 | 313 | ✓ |
| nj-labor-market-synthesis | document-synthesis | 6 | 269 | ✓ |
| northeast-housing-comparison | cross-sectional | 6 | 132 | ✓ |

**Agent phases (Gemini CLI):** 1 (brief clarification), 3 (source discovery), 5 (hydration), 6 (research), 7 (artifacts), 9 (follow-up questions)
**Platform phases:** 2 (repo bootstrap), 4 (ontology audit), 8 (post-run auditors)

All projects report:
- `session: ready`, `planner: ready`, `ontology: ready`, `integrity: ready`, `closeout: ready`
- `zeroFabrication: true`, `zeroMetaOperatorReconciliation: true`

Evidence: `/docs/validation/gemini_cli_loop_summary.json`

---

## Category B — Real Codex CLI Agent Sessions (European Soccer, 51 Sessions)

The European Soccer project was executed by 51 real Codex CLI agent sessions before M6 (Post-Run Auditors) was implemented. The repair script retroactively wrote post-run audit files using `repair_stale_session_audits()`. All five auditors report ready after repair.

- **Project:** European Soccer Competitive Ecosystem Analysis
- **Real agent sessions:** 51 (Codex CLI, pre-M6)
- **Real GitHub commit hashes** (e.g., 2e9d239) in session state
- **Real verification stdout** ("VERIFICATION PASSED") in session summaries
- **Real DuckDB** with populated ontology rows at `.ontology/onto.duckdb`
- **All five auditors:** ready

Evidence: `/docs/validation/soccer_audit_repair_summary.json`

---

## Category C — Scripted Validation (Three Archetypes, Real FRED API)

The Convex DB layer (project registry, running-agent tracking) is mocked to isolate file-based platform components. All other layers are real:
- Real FRED API HTTP calls (NJSTHPI, NJURN, CPIAUCSL, GDPC1, UNRATE)
- Real DuckDB population and row-count verification
- Real integrity state (sources.json, artifact_lineage.json, verification_runs.json)
- Real session lifecycle state files (state.json, summary.md)
- Real post-run audit JSON files written by `write_post_run_audit()`
- Real `build_auditor_statuses()` pipeline with all five auditors

| Project | Archetype | Audit File |
|---------|-----------|-----------|
| NJ Housing and Unemployment Study | time-series-policy-econ | audits/sess-data-001.json |
| NJ Labor Market Literature Review | document-heavy-literature | audits/sess-research-001.json |
| US Economic Indicators Ontology Study | ontology-first-public-data | audits/sess-coding-001.json |

All three: session/planner/ontology/integrity/closeout = ready.

---

## Category D — Autopilot-Driven Autonomous Loop (Unit Tests)

Four tests prove the **autopilot loop** drives project completion without operator intervention and advances only from audited reality:

- `test_autopilot_drives_time_series_econ_to_closeout` (time-series-econ)
- `test_autopilot_drives_document_synthesis_to_closeout` (document-synthesis, multi-task sequencing)
- `test_autopilot_drives_cross_sectional_to_closeout` (planner → worker → worker sequencing)
- `test_autopilot_audit_gate_blocks_until_audit_is_written` (audit gate blocks until a real audit file exists)

All tests assert: autopilot launches sessions via `launch_task_runner`, writes real session state + audit files, blocks on audit gate until certified, then calls `_mark_project_completed`. Evidence: `packages/api/tests/test_autopilot_autonomous_loop.py`.

---

## Platform Trust Improvements (Post-Validation)

Four coding gaps closed after the initial validation:

1. **Durable audit commits** — `write_post_run_audit()` now stages and commits audit files (`research_plan/audits/{session_id}.json/md`) to the project's git history. Audit certificates are permanent once written.

2. **Single authoritative status endpoint** — `GET /api/projects/{slug}/phase` returns lifecycle phase, top blocker, next recommended action, and all five auditor statuses in one call. No more partial-signal assembly by operators or autopilot.

3. **Planner drift suppression** — The planner auditor now tracks `taskSaturationCount`. When open tasks exceed the saturation threshold (10), new planner-role sessions are blocked until existing work is resolved.

4. **Artifact promotion gate** — The `POST /integrity/artifacts/promote` endpoint already blocks promotion to `partially_verified` or `verified` when ontology or integrity auditors are blocked. This gate now also applies to all API-level promotion calls.

---

## What This Does Not Cover

Live end-to-end sessions with a deployed Convex instance (requiring agent credentials and a live Convex deployment) have not been run from this codebase. The Gemini CLI sessions in Category A demonstrate real agent execution and file-based state management without requiring a live Convex DB. The Convex layer handles UI/API tracking and is exercised in integration via the mocked client patterns.
