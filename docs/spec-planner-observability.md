# Planner Observability — UI Scope

**Status:** Spec / not yet implemented
**Owner:** unassigned
**Branch suggestion:** `feat/planner-observability-ui`
**Estimated effort:** ~5 days for a competent full-stack agent

## Problem

After Phases 2–5 of the runner protocol, the platform writes a lot of useful state to disk that the UI never surfaces:

| What gets written | Where | Visible in UI today? |
|---|---|---|
| Typed `WorkOrder` per session | `research_plan/work_orders/<wo_id>.json` | ❌ |
| Capability router decision (eligible runners + scores + rejection reasons) | `research_plan/dispatch_log/<wo_id>.json` | ❌ |
| Structured `SessionResult` (claims, sources, datasets, blockers, next_recommended_tasks) | `research_plan/sessions/<id>/session_result.json` | Partial (status only) |
| Q&A log (runner asks via `rail.ask`, planner answers) | `research_plan/qa_log.json` | ❌ |
| Promotion progress ledger | `research_plan/progress_ledger.json` | ❌ |

Operators currently see only the planner board, autopilot toggle, and final task status. They cannot see *why* the planner did what it did. This is the single biggest gap between terminal-power-user observability and the production UI.

Symptom: when a project runs for hours without producing research, the operator has no way to look "into" the planner's reasoning — they have to tail files on disk or read the logs to understand.

## Goal

Give an operator looking at a project page enough visibility to answer, without leaving the UI:

1. *What did the planner decide to do, and what runner did it choose?*
2. *Why did it choose that runner over the others?*
3. *What is the runner currently doing — file changes, commands, thinking — in real time?*
4. *When the runner asks a question, can I answer it without dropping into the terminal?*
5. *What did the runner come back with as structured output, and what's blocking promotion?*

## Existing surface

Already present (don't rebuild):

- `apps/web/components/planner-workbench.tsx` — board + chat + presets
- `apps/web/components/task-board.tsx` — task cards
- `apps/web/components/operator-overview-strip.tsx` — health auditors summary
- `apps/web/lib/api.ts` — typed REST client (no work-order/dispatch endpoints yet)

Already present on the backend (just needs API + UI wiring):

- `GET /api/v1/runners/sessions/{session_id}/work-order` → reads work order JSON for a session (already implemented in `app/routers/runners.py:414`)
- Files on disk under `research_plan/work_orders/`, `research_plan/dispatch_log/`, `research_plan/sessions/*/session_result.json`, `research_plan/qa_log.json`

What's missing on the backend:

- No endpoint exposing the *dispatch decision log* (the router's rationale)
- No endpoint exposing the *session_result.json* in structured form
- No endpoint streaming live RunnerEvents to the UI (events are persisted but only polled via `list_events`)
- No endpoint surfacing the `qa_log.json` or accepting an operator answer to a pending question
- No "pending dispatch" / approval queue for the dry-run pattern

## Scope — four shipping units

The four units are independent and can be merged separately. Ship them in this order; each one is independently useful.

### Unit 1 — Work Order Inspector (highest leverage)

**What it is.** A panel/route at `/projects/[slug]/sessions/[sessionId]` (or as a drawer from the task card) that shows, for one session:

- **Work order** — the typed `WorkOrder` JSON: task_type, capabilities_required, allowed_paths, runner_preferred, cost/time budgets, trust_policy, depends_on
- **Dispatch decision** — which runner was selected, what its score was, the scores of the other eligible runners, and the rejection reasons for the ineligible ones (the `_log_decision` payload from `capability_router.py:_log_decision`)
- **Session result** — once the session finishes, the parsed `SessionResult`: claims with confidence, sources with admissibility, datasets with row counts, blockers, `next_recommended_tasks`, certification status (passed/failed + issues)

**Why it matters.** This is the single document that explains "what did RAIL just do." Today it's three JSON files an operator has to find on disk.

**Backend deltas.**

```
GET /api/v1/runners/sessions/{session_id}/dispatch-decision
  → returns research_plan/dispatch_log/<wo_id>.json (404 if no WO)

GET /api/v1/runners/sessions/{session_id}/result
  → returns research_plan/sessions/<id>/session_result.json
     parsed against SessionResult schema (400 if invalid, 404 if absent)
```

The work-order endpoint already exists; just plumb the other two.

**Frontend deltas.**

- `lib/api.ts`: add `fetchWorkOrder(sessionId, slug)`, `fetchDispatchDecision(...)`, `fetchSessionResult(...)`; corresponding TypeScript types mirroring the Pydantic models
- New component `components/work-order-inspector.tsx` with three tabs: **Work Order**, **Dispatch Decision**, **Result**
- Surface from `task-board.tsx` task cards — clicking a task with `agentSessionId` opens the inspector

**Acceptance.**

- For a finished session, the inspector shows all three documents
- Dispatch decision shows a sorted runner scoreboard with rationale strings ("Missing required capabilities: query_duckdb")
- Session result shows certification status and any blockers conspicuously
- Empty/in-progress states render without crashing

---

### Unit 2 — Live Planner Decision Stream

**What it is.** A new pinned panel in `planner-workbench.tsx` showing the planner's recent decisions as they happen: "dispatched WO-abc to codex_cli", "requeued task-xyz because integrity gate blocked", "skipped planner turn because no ready tasks". Each entry expands to show the rationale.

**Why it matters.** Today the planner runs autonomously and the operator only sees the *result* — they don't see the planner's reasoning in flight. Hard to debug "why did it pick that task next."

**Backend deltas.**

- Add a `PlannerDecision` event type written by `_execute_planner_tool` in `planner_runtime.py` with fields: `tool`, `args`, `result_summary`, `rationale`, `timestamp`
- Persist to `research_plan/planner_decisions.jsonl` (append-only) and emit via the existing Convex events channel
- `GET /api/v1/projects/{slug}/planner/decisions?limit=50` → tail of the JSONL

**Frontend deltas.**

- `lib/api.ts`: `fetchPlannerDecisions(slug)`
- New component `components/planner-decision-feed.tsx` with relative timestamps + expandable rationale rows
- Mount inside `planner-workbench.tsx`

**Acceptance.**

- Each call to `_execute_planner_tool` writes a decision line
- UI polls every ~5s while autopilot is running
- The router's selection rationale appears in the dispatch decision entry

---

### Unit 3 — Mid-session Q&A panel

**What it is.** A persistent inbox in `floating-planner-chat.tsx` showing questions that runners have asked via `rail.ask` and are awaiting a tier-3 (human) answer. The operator types a reply and the runner unblocks.

**Why it matters.** The three-tier resolver (cache → planner LLM → human) exists but the tier-3 UI surface doesn't. Today an operator has to write the answer into `qa_log.json` by hand.

**Backend deltas.**

- `GET /api/v1/projects/{slug}/qa/pending` → list of `QAQuestion` records with `status="awaiting_human"` from `qa_log.json`
- `POST /api/v1/projects/{slug}/qa/{question_id}/answer` body `{answer: str}` → patches the entry, sets status to `answered`, signals the waiting runner (file-watcher or polling at the runner end)
- Verify that `planner_answer_service.py` actually escalates to tier-3 instead of just falling back to LLM (look for the escalation condition)

**Frontend deltas.**

- Add a tab/badge to `floating-planner-chat.tsx`: "Pending Questions (N)"
- Each question shows: who asked (runner + session), the question, context, suggested cached answer if any
- Operator can answer or "promote cached" (apply the suggested answer)

**Acceptance.**

- A runner calling `rail.ask` with no cache + LLM-low-confidence shows up in pending within ~5s
- Operator answer unblocks the runner within ~5s
- Answer is persisted to `qa_log.json` cache for future tier-1 hits

---

### Unit 4 — Dry-run / approve-before-dispatch

**What it is.** A new operator-toggle on the project page: "Hold dispatches for review." When on, every WorkOrder generated by the planner is held in a `pending_dispatch` queue until the operator clicks **Dispatch**, **Edit**, or **Reject**.

**Why it matters.** This is the lowest-effort guard against runaway autopilot loops. When you ran a project for a day with no research output, this would have caught the wrong dispatch on iteration #1.

**Backend deltas.**

- New project-level config flag `dispatch_approval_required` (default false) stored alongside autopilot config
- In `session_lifecycle._dispatch_work_order` (or wherever the WO is committed): if flag is on, write to `research_plan/pending_dispatch/<wo_id>.json` and return instead of launching the runner
- `GET /api/v1/projects/{slug}/dispatches/pending` → list
- `POST /api/v1/projects/{slug}/dispatches/{wo_id}/approve` body `{edits?: Partial<WorkOrder>}` → dispatches with optional edits
- `POST /api/v1/projects/{slug}/dispatches/{wo_id}/reject` body `{reason: str}` → marks rejected, planner will get a "rejected" outcome and must decide what to do next

**Frontend deltas.**

- Toggle in `operator-overview-strip.tsx`
- New panel in `planner-workbench.tsx`: pending dispatches with **Dispatch** / **Edit JSON** / **Reject** buttons per entry

**Acceptance.**

- With flag on, no runner subprocess is launched until the operator clicks dispatch
- Edits to the WO JSON are validated against the schema before dispatch
- Rejection writes a rejection blocker into the planner's next turn

## Out of scope

- Real-time WebSocket event streaming (use polling at 2–5s intervals for now)
- Replaying or branching past sessions
- Multi-project rollup views
- Runner profile editing UI (profiles stay YAML-first)

## File-level inventory of what exists today

```
apps/web/
  components/
    planner-workbench.tsx        821 lines  ← board, chat, presets, autopilot toggle
    task-board.tsx               619 lines  ← task cards (where WO inspector deep-link lands)
    operator-overview-strip.tsx  280 lines  ← health auditors banner
    floating-planner-chat.tsx           ?   ← chat overlay (where Q&A inbox lands)
  lib/
    api.ts                       528 lines  ← REST client; no WO/dispatch/QA functions yet
    types.ts                       ?         ← PlannerTask, AutopilotStatus, etc.

packages/api/
  app/routers/runners.py    ← work-order endpoint already at line 414
  app/services/capability_router.py    ← _log_decision writes dispatch_log
  app/services/planner_answer_service.py    ← Q&A three-tier resolver
  app/runners/contracts/    ← WorkOrder + SessionResult Pydantic models (source of truth for TS types)
```

## Risks and watch-outs

- **Convex coupling.** The current API mixes file-based reads (work orders, session_result.json) with Convex-backed queries. The new endpoints should follow the *file-first* pattern — read from disk, fall back gracefully if Convex is down. The planner UI must work in fully-local mode.
- **TS type drift.** The TypeScript types should be generated from the Pydantic models, not hand-written, to avoid drift. Simplest path: a `tools/sync-contract-types.ts` script that reads JSON schemas exported by `WorkOrder.model_json_schema()` etc. and emits `apps/web/lib/contract-types.ts`. Acceptable starter alternative: hand-written types with a one-line comment pointing at the Pydantic source.
- **Polling cost.** Decision feed + Q&A inbox + pending dispatch each poll every 2–5s. If a user has 5 projects open in tabs, that's a lot of requests. Consider a single `/projects/{slug}/observability/tick` endpoint that returns all three deltas in one call.
- **Dry-run approval can deadlock the planner.** If the operator forgets to approve, autopilot stalls. Mitigation: surface "N dispatches pending review" prominently on the project page and in the autopilot status pill.

---

## Handoff prompt for the next agent

> Below is the prompt to give to a fresh coding agent (Claude Code, Codex, etc.) to execute this scope. Copy from `>>>` to the next `>>>`.

---

>>> AGENT HANDOFF — Planner Observability UI

You are picking up a scoped frontend + backend task in the RAIL repository. The full design is in `docs/spec-planner-observability.md` — read it first, end to end, before touching any code.

**Goal.** Surface the planner's reasoning, dispatch decisions, runner output, and Q&A questions in the Next.js UI so operators don't have to tail files on disk to understand what RAIL is doing.

**Branch.** Start from `yaml-driven-hydration` (or `main` after PR #60 merges). Create `feat/planner-observability-ui`. Open one PR per shipping unit; do not bundle all four into one PR.

**Constraints.**

1. Ship **Unit 1 first** (Work Order Inspector). It's the most leverage and the other units assume the inspector's data plumbing exists.
2. Each unit must be independently mergeable, tested, and useful.
3. Read endpoints are *file-first*: read from `research_plan/...` JSON on disk before falling back to Convex. The UI must continue to work for projects whose Convex is offline.
4. Add tests at the level you change:
   - Backend: pytest in `packages/api/tests/`. New endpoints get at least one happy path + one 404 + one malformed-file test.
   - Frontend: vitest/react-testing-library if it's already set up; otherwise component-level smoke tests for the inspector showing it renders all three tabs with mock data.
5. TypeScript types for `WorkOrder` / `SessionResult` go in `apps/web/lib/contract-types.ts` with a header comment naming the Pydantic source. Do not hand-redefine fields in multiple places.
6. Follow the project conventions in `CLAUDE.md` files. Don't add comments explaining *what* code does; only comments explaining *why* something non-obvious is the case.
7. Don't add new dependencies without flagging it in the PR description.
8. **Do not** commit anything under `generated_projects/`, `uploaded_key`, `*.pid`, or `apps/web/.screenshots/` — these are runtime/local-only.
9. **Do not** weaken or remove `continue-on-error: false` in `.github/workflows/ci.yml`. If CI surfaces a regression, fix the regression — don't hide it.
10. Run the full local test suite before opening each PR: `cd packages/api && python -m pytest tests/ -n auto`. Should be 961 passing, 0 failing. If you introduce new failures, fix them before requesting review.

**Validation milestone** — after Unit 1, demonstrate:

- Start the API locally and the dev server (`make api` + `cd apps/web && npm run dev`).
- Open a project page that has at least one finished session.
- Click into the inspector — all three tabs show the correct data from disk.
- Provide a screenshot in the PR description.

**Out of scope** — do not pull in: real-time WebSocket streaming, session replay, multi-project rollups, runner profile editing UI. The doc lists these explicitly.

**Open questions you may need to resolve as you go.**

- Where exactly should the inspector mount? Drawer from task card, or its own `/projects/[slug]/sessions/[id]` route? Either is fine; pick one and justify in the PR.
- The dispatch decision JSON shape from `capability_router.py:_log_decision` is the source of truth — verify it matches what's already on disk in a real project before designing the UI tab around it.
- For Unit 4, the planner-side handling of a rejected dispatch needs design — does the planner treat rejection as a `blocker`, a `requeue`, or something else? Talk to whoever owns `planner_runtime.py` (or pattern-match how it handles other refusals).

**Done means.**

- All four units shipped, each behind its own PR with green CI.
- A short follow-up doc `docs/planner-observability-rollout.md` documenting what was built, screenshots, and any deviations from this spec.
- The validation milestone screenshot is in the Unit 1 PR.

If you get stuck, stop and ask before building speculatively. This scope is intentionally written to make every unit testable in isolation; if you find yourself wanting to refactor across units, you're probably going outside scope.

>>> END HANDOFF
