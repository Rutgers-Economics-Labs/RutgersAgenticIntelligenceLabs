# Future Spec: Runner Protocol

Date: 2026-05-21

## Summary

RAIL is currently runner-name agnostic but not runner-protocol intelligent. It
can launch six different agent harnesses (jules, claude_code, codex_cli,
gemini_cli, cursor_cli, copilot_cli) but treats them as interchangeable black
boxes: build a prompt, spawn a subprocess, stream stdout, parse what came out.

This spec defines the protocol every runner must satisfy so that RAIL can:

- route tasks by capability instead of by hardcoded name
- give launched agents tool access to project state (MCP or CLI)
- answer questions agents raise mid-run
- normalize events across runners for a coherent operator UI
- learn empirically which runner is best for which task type

The north star is one sentence:

> Every runner must satisfy the same RAIL protocol: receive a typed work order,
> access RAIL tools, produce structured outputs, expose normalized events, and
> pass verification/promotion gates.

This spec depends on the background-health-governance work
([future-spec-background-health-governance.md](./future-spec-background-health-governance.md))
because the audit/promotion gate separation must exist before promotion
decisions can read structured session results.

## Honest current state

| Runner | Current state |
|---|---|
| `jules` | Hosted Google API. Real session lifecycle. Most mature. |
| `claude_code` | Local CLI subprocess. 28 LOC adapter. One-shot, no mid-run steering. |
| `codex_cli` | Local CLI subprocess. 24 LOC adapter. Same shape. |
| `gemini_cli` | Local CLI subprocess. 24 LOC adapter. Same shape. |
| `cursor_cli` | Local CLI subprocess. 13 LOC adapter. Best used attached to IDE. |
| `copilot_cli` | `gh copilot suggest`. 9 LOC adapter. Suggestion-only, not autonomous. |

The five CLI runners all collapse into `LocalCLIRunner` (~900 LOC in
`cli_base.py`) which handles subprocess spawning, event streaming, session
state, and PID tracking. The factory in `packages/api/app/runners/factory.py`
registers them by name. Mid-run steering, approval, and continuation paths are
mostly no-ops for detached local sessions.

## Design principles

1. **Protocol over personality.** Every runner satisfies the same contract.
   Per-runner differences are declared in capability profiles, not handled by
   special-case code paths in the autopilot.
2. **Structured I/O beats stdout parsing.** Work orders in (JSON), session
   results out (JSON). stdout/stderr remain available for debugging but are
   not the control surface. (Same lesson TradingAgents drew about long-running
   multi-agent systems: structured global state beats unstructured chains.)
3. **Capability routing, not name routing.** Tasks declare what capabilities
   they need; the router picks an eligible runner. Operator overrides are
   respected, but they should be the exception.
4. **Agents can ask questions.** Q&A is a first-class protocol element, not a
   workaround. Agents that don't know what to do should ask, not guess.
5. **Honest certification.** No runner is "supported" until it passes
   end-to-end certification on the protocol. Copilot CLI in its current form
   will not pass autonomous certification; it stays advisory-only.

## Contracts

Three Pydantic schemas define the protocol. They live in
`packages/api/app/runners/contracts/`.

### WorkOrder

A typed dispatch record. Replaces ad-hoc `TaskPayload` flattening into a
prompt.

```python
class WorkOrder(BaseModel):
    work_order_id: str
    project_slug: str
    task_type: TaskType   # data_ingestion, analysis, source_discovery,
                          # artifact_writing, health_repair, claim_extraction,
                          # verification
    phase: str | None
    capabilities_required: list[Capability]
    runner_preferred: str | None      # operator override
    runner_allowed: list[str] | None  # project-level allow-list
    allowed_paths: list[str]
    inputs: dict[str, str]            # path references
    outputs_required: list[str]
    trust_policy: TrustPolicy
    cost_budget_usd: float | None
    wall_time_budget_minutes: int | None
    questions_allowed: bool = True
    depends_on: list[str] = []
    created_at: datetime
    created_by: str                   # session_id or "planner"
```

Stored at `research_plan/work_orders/<wo_id>.json` for audit. Passed to the
runner both as a human-readable prompt and a machine-readable file the agent
can re-read with `rail.get_work_order(wo_id)`.

### SessionResult

The required exit artifact. Every session, every runner, every time. If
absent at finalization, the session is `complete_unverified` and not eligible
for promotion.

```python
class SessionResult(BaseModel):
    session_id: str
    work_order_id: str | None
    status: SessionStatus  # completed, failed, cancelled, blocked,
                           # needs_followup
    summary: str
    task_type: TaskType
    files_changed: list[str]
    claims: list[ClaimCandidate] = []
    sources: list[SourceRecord] = []
    datasets: list[DatasetRecord] = []
    blockers: list[Blocker] = []
    questions_asked: list[str] = []   # question_ids (Phase 4)
    verification: VerificationRequest | None
    next_recommended_tasks: list[RecommendedTask] = []
    cost_recorded_usd: float | None
    duration_seconds: float
    runner_name: str
    completed_at: datetime
```

Written by the agent at session end to
`research_plan/sessions/<id>/session_result.json`.

### RunnerProfile

Static capability declaration. One YAML per registered runner under
`packages/api/app/runners/profiles/`.

```python
class RunnerProfile(BaseModel):
    name: str
    adapter: AdapterType    # local_cli, hosted_api, attached_ide
    default_command: str | None
    status: CertificationStatus  # experimental, certified, advisory_only,
                                 # deprecated
    execution: ExecutionCapabilities
    capabilities: dict[str, CapabilityState]
    task_affinity: dict[TaskType, float]  # 0..1 score per task type
    output_contract: OutputContract
```

`ExecutionCapabilities` declares: mode, supports_streaming, supports_resume,
supports_midrun_messages, supports_native_approval, supports_cancel,
supports_mcp.

`CapabilityState` is `"yes" | "no" | "configurable" | "unknown"` — three-valued
logic matters because some capabilities (MCP, web browse) depend on per-user
configuration that RAIL can't infer.

## Phase plan

Seven phases, ~8 weeks for one engineer, ~3-4 weeks if parallelized. A
Minimum Viable Path is called out at the end.

### Phase 0 — Contracts and test harness (week 1)

Establish the typed contracts everything else depends on.

**Deliverables**
- `packages/api/app/runners/contracts/work_order.py`
- `packages/api/app/runners/contracts/session_result.py`
- `packages/api/app/runners/contracts/runner_profile.py`
- `packages/api/tests/runner_certification/` — test harness for contract
  validation and stub-runner certification

**Acceptance** — schemas validate hand-written samples; harness runs a stub
runner and passes certification.

### Phase 1 — Runner profiles + probe system (week 2)

**Deliverables**
- `packages/api/app/runners/profiles/{jules,claude_code,codex_cli,gemini_cli,cursor_cli,copilot_cli}.yaml`
- `packages/api/app/runners/probe.py` — installed? authenticated? trivial
  session? MCP available?
- `GET /api/runners`, `GET /api/runners/{name}/probe`
- Operator UI runner-readiness matrix

**Acceptance** — all six profiles exist, probe runs without crashing on a
clean machine, UI shows accurate red/yellow/green.

**CLI verification** — first real cross-runner test. Probe expected outcomes
on a clean dev machine documented in the certification matrix below.

### Phase 2 — Structured I/O (weeks 3-4)

Replace prompt-only dispatch with typed work orders + required session
results.

**Deliverables**
- Work order generator in the planner
- Runner adapters updated to copy work order into session workspace
- Session result enforcer at finalization
- Migration shim for legacy `TaskPayload`

**Acceptance** — end-to-end test against `claude_code`: planner emits work
order → runner sees prompt + JSON → session ends with valid
`session_result.json` → promotion gate reads structured output.

### Phase 3 — MCP injection + CLI fallback (week 5)

**Deliverables**
- `packages/api/app/runners/mcp_injector.py` — per-session MCP config
  generator (never mutates global config)
- New MCP tools: `rail.list_project_state`, `rail.get_work_order`,
  `rail.submit_session_result`, `rail.ask` (placeholder for Phase 4)
- `rail` CLI fallback for runners without MCP: `rail work-order current`,
  `rail ask`, `rail submit-result`

**Acceptance** — launched `claude_code` session calls `rail.list_project_state`
via MCP and gets real state. Launched `codex_cli` session without MCP runs
`rail work-order current` and gets the same payload.

### Phase 4 — Q&A protocol (week 6)

Highest-leverage single addition. Agents that don't know what to do can ask
instead of guessing.

**Deliverables**
- `packages/api/app/services/planner_answer_service.py` — three-tier
  resolver: cache → planner LLM → human escalation
- `research_plan/decisions/qa_log.json` durable answer log
- MCP tool `rail.ask` and file fallback
  `research_plan/sessions/{id}/questions.json` (polled by RAIL)
- Operator inbox UI for Tier-3 escalations
- Embedding-based question similarity for Tier-1 cache hits

**Acceptance** — agent asks methodology question mid-session; planner answers
from Tier 2 with rationale citing project docs; answer flows back; both
question and answer logged; re-asked question hits Tier-1 cache.

### Phase 5 — Capability router (week 7)

**Deliverables**
- `packages/api/app/services/capability_router.py`
- `rail.yaml` extensions: `runners.allowed`, `runners.preferred`
- Routing decision log: `research_plan/dispatch_log/<wo_id>.json`
- Deprecation of `_matches_task_identity` plumbing in
  `autopilot_service.py`
- Operator override (`runner: ...` in work order) still respected

**Acceptance** — work order with only `capabilities_required` gets routed
automatically; decision log shows reasoning; explicit override wins.

### Phase 6 — Context compilers + event normalizers (week 8, ongoing)

**Deliverables**
- Per-task-type context compilers under
  `packages/api/app/runners/context_compilers/`
- Per-runner wrappers (claude_code, codex_cli, gemini_cli, cursor_cli) that
  apply runner-specific framing to a shared context pack
- Per-runner event normalizers that map runner-specific stdout into the
  shared event taxonomy (`session_started`, `tool_call_started`,
  `claim_candidate_emitted`, `verification_completed`, etc.)
- UI shows structured events instead of raw logs

**Acceptance** — same task to `claude_code` vs `codex_cli` produces materially
different prompts; UI shows structured events instead of stdout.

This phase is ongoing — initial cut in week 8, refined empirically over time
using the runner scoreboard.

### Phase 7 — End-to-end smoke test on a real project (week 9)

**Deliverables**
- One project (recommend NJ housing — closer to closeout than power-markets
  and has fewer source-admissibility issues) run end-to-end through the
  protocol
- At least three different runners used for different task types
- At least one Q&A exchange logged
- No human task-routing decisions
- Documented in `docs/validation/runner-protocol-smoke-test-2026-XX.md`

**Acceptance** — project produces a final memo with claim-level provenance
using the new protocol, fully populated `qa_log.json`, runner scoreboard
shows empirical data for at least three runners.

## CLI certification matrix

Expected outcome after all phases:

| Runner | Phase 1 probe | Phase 2 I/O | Phase 3 MCP/CLI | Phase 4 Q&A | Phase 5 router-eligible | Certification |
|---|---|---|---|---|---|---|
| `jules` | green | green | green (API) | green | yes | **Fully certified — managed API runner** |
| `claude_code` | green | green | green (MCP) | green | yes | **Fully certified — autonomous CLI runner** |
| `codex_cli` | green | green | green (MCP/CLI) | green | yes | **Fully certified — autonomous CLI runner** |
| `gemini_cli` | green | green | green (MCP) | green | yes | **Fully certified — autonomous CLI runner** |
| `cursor_cli` | yellow | yellow | green (MCP) | green | yes (attached) | **Certified — attached-mode runner only** |
| `copilot_cli` | yellow | red | partial (CLI read-only) | n/a | no | **Certified — advisory only, no autonomous tasks** |

This is the honest support matrix the operator UI should show. Five runners
can drive autonomous research (with `cursor_cli` requiring an attached IDE);
one is advisory-only and is excluded from the autonomous routing pool.

## Q&A protocol (detail)

Today an autonomous agent that doesn't know what to do has three bad options:
make a judgment call and document it as an assumption (silent drift), mark
the task blocked (work stops, planner has no info to unblock), or get it
wrong (verification fails later, expensive to recover). None of these
produce learning.

The Q&A protocol makes questions first-class.

### Mechanism

`rail.ask(...)` is an MCP tool (with CLI fallback `rail ask "..."`). The agent
emits a structured question mid-run:

```json
{
  "question_id": "q_2026_001",
  "question": "Should I use FRED UNRATE (seasonally adjusted) or UNRATENSA?",
  "context": "Building monthly panel 2010-2024. Methodology note doesn't specify.",
  "options": ["seasonally_adjusted", "not_seasonally_adjusted", "both"],
  "default_if_no_answer": "seasonally_adjusted",
  "blocking": false,
  "category": "methodology_choice"
}
```

Returns:

```json
{
  "answer": "seasonally_adjusted",
  "rationale": "NJ housing precedent (decisions.md 2026-04) used SA series.",
  "source": "planner_llm",
  "confidence": 0.78,
  "decision_recorded_at": "research_plan/decisions/qa_log.json#q_2026_001"
}
```

### Three answering tiers

1. **Cached decision.** Embedding similarity search over
   `research_plan/decisions/qa_log.json`. If a near-duplicate decision exists
   in scope, reuse it. Free, instant, consistent.
2. **Planner LLM with project context.** Pass question + brief + methodology
   + recent decisions + claim graph. Returns answer with confidence score and
   rationale citing the project context used. Handles most routine questions.
3. **Human escalation.** Triggered when LLM confidence is below threshold or
   the question is tagged `scope_change | trust_state | ethics |
   external_resource`. Lands in operator inbox; agent gets
   `answer: "deferred"` and instructions to use default with assumption, or
   block if `blocking: true`.

### Durable memory

Every Q&A pair lands in `research_plan/decisions/qa_log.json` regardless of
tier. This is the project's institutional memory. Six months later when
someone asks "why are we using SA series?", the answer + rationale is in the
log.

### Integration with phases

- Work order schema (Phase 0/2): `questions_allowed: bool` field
- Session result schema (Phase 0/2): `questions_asked: [question_id, ...]`
- MCP injection (Phase 3): `rail.ask` added to default tool set
- Runner profile (Phase 1): `supports_native_questions: bool`. Runners that
  can't easily emit MCP calls mid-run get a file-based fallback (write
  `questions.json`, RAIL polls).
- Runner scoreboard (Phase 6): `questions_per_session` and
  `question_answer_acceptance_rate` — runners that ask good questions get
  higher routing weight on ambiguous tasks.

### Implementation note

The Tier-2 planner LLM should use the same model family as the asking agent
when possible. Cross-model semantic drift (e.g., Codex asking, Claude
answering) means the planner has to be very explicit about its rationale
because the asking model won't share the answering model's defaults.

## Minimum Viable Path (3 weeks)

If you want to slice aggressively:

- **Week 1** — Phase 0 (contracts + harness)
- **Week 2** — Phase 1 limited to `claude_code` + `jules`; Phase 2 limited to
  `claude_code`
- **Week 3** — Phase 3 limited to `claude_code` MCP; Phase 4 (Q&A) on
  `claude_code` only; Phase 7 smoke test on NJ housing using only
  `claude_code`

This proves the architecture without multi-runner sprawl. Adding
`codex_cli`, `gemini_cli`, `cursor_cli` afterward is mostly profile YAML + a
20-line adapter once the protocol is proven.

**The protocol matters more than the breadth of runner support.** Recommend
the MVP slice unless there's specific pressure to launch with all five
autonomous runners simultaneously.

## Risks

1. **MCP support is a moving target.** Codex/Gemini/Cursor MCP support is
   relatively new; expect schema/auth changes between now and ship.
   Re-certification needed quarterly.
2. **Per-runner auth setup is not automated.** Phase 1 probe surfaces it;
   Phase 7 smoke test requires it manually. A `rail setup-runners` CLI would
   help; add as Phase 5 deliverable.
3. **API costs during certification testing.** Running every runner through
   every phase test could cost $50-200. Build a small deterministic fixture
   project (~10 files) for repeated runs.
4. **Tier-3 human escalation needs a UI surface that doesn't exist yet.**
   Could start with email/static page; full inbox UI is Phase 4+.
5. **Prerequisites from `fix/research-not-blocked-by-health`** — the audit
   idempotency, research/promotion split, and verification anchor fixes on
   that branch are required before Phase 2 can reliably test session result
   emission. Land that branch first or stack this one on it.

## Success criteria

This spec is successful when:

- An operator can type a research question and RAIL routes it across at least
  three different runners (chosen by capability, not name) to produce a final
  memo with claim-level provenance.
- Every session ends with a structured `session_result.json` regardless of
  runner.
- Agents ask the planner ≥1 question per non-trivial session and the planner
  resolves ≥80% from Tier 1 or Tier 2 without human escalation.
- Adding a new runner is a YAML profile + a 20-line adapter, no autopilot
  changes.
- The operator UI shows a runner readiness matrix with truthful certification
  states, not just "registered."

## Bottom line

The current six-runner registration is a real start. The gap is that "runner
support" today means "we can spawn a CLI" — not "we have an executor we can
reason about, route to, steer, or trust." This spec closes that gap with a
shared protocol every runner satisfies, and an honest certification matrix
showing which runners pass it.

The protocol matters more than any individual runner. Ship the protocol on
one runner first; extend to the rest from there.
