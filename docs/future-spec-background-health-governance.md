# Future Spec: Background Health Governance

Date: 2026-05-21

## Summary

RAIL should move from blocking health loops to background health governance.

The core rule is:

> research should run optimistically; promotion should run pessimistically

That means:

- research, data, coding, and artifact workers may continue producing candidate work while health is imperfect
- auditors should run continuously in the background
- maintenance should be queued as explicit repair work, not occupy the main research lane by default
- strict blocking should happen only at trust boundaries such as promotion, merge, publish, verification, and closeout

This preserves rigor without letting audit and cleanup consume the entire autonomy budget.

## Problem

RAIL currently treats parts of health and integrity maintenance as foreground work.

That creates several failure modes:

- research is delayed while the system proves that it is safe to continue
- audit and cleanup tasks compete with substantive research tasks for the active lane
- repeated audit writes can trigger repeated repo changes and repeated autopilot wakeups
- partially useful findings are suppressed instead of being preserved as candidate work
- the system gets trapped in repair loops rather than moving source -> data -> ontology -> analysis -> claim -> artifact

The symptom is repeated durable audit commits with little change in trusted project state.

## Design Principle

RAIL must distinguish between:

1. learning whether something is true
2. deciding whether something is trusted

Learning should be cheap and continuous.

Trust promotion should be strict and fail-closed.

The system should not block learning in order to maintain cleanliness.
It should block trust claims until cleanliness is restored.

## Policy Shift

Replace the implicit policy:

`health blocked -> no more research`

with:

`health blocked -> research may continue, but outputs remain candidate`

Every meaningful output should have an explicit trust state.

Minimum trust states:

- `candidate`
- `draft`
- `unverified`
- `blocked_for_promotion`
- `verified`
- `rejected`

## Operating Model

### Four Lanes

RAIL should run four conceptual lanes instead of one blocking lifecycle lane.

| Lane | Runs while research is active? | Can write to Git? | Can block research? |
|---|---|---|---|
| Research lane | Yes | Yes | No, unless there is a hard safety issue |
| Audit lane | Yes | Usually no | No |
| Maintenance lane | Yes, throttled | Only via branch, patch, or proposal | No, except hard repair |
| Promotion lane | Only at trust boundaries | Yes | Yes |

### Lane Responsibilities

#### Research lane

Produces candidate state:

- source notes
- fetch configs
- transforms
- hydration outputs
- analyses
- claim candidates
- draft artifacts

#### Audit lane

Observes state and classifies project health:

- session liveness
- planner truth
- ontology health
- integrity and lineage
- promotion readiness

Audit should annotate project state, not dominate it.

#### Maintenance lane

Executes bounded repair tasks such as:

- deduplicating task files
- reconciling stale runtime session rows
- rebuilding missing lineage records
- normalizing schema drift
- repairing stale ontology pointers

Maintenance should be spawned only from concrete findings and should be branch-isolated whenever possible.

#### Promotion lane

Owns trust boundaries:

- claim verification
- artifact promotion
- merge or publish actions
- final memo publication
- project closeout

This lane remains strict and fail-closed.

## Health Architecture

Health should no longer be modeled primarily as a permanent foreground agent role.

Instead it should be split into three components.

### 1. Background Auditors

These are mostly read-only and run:

- after every worker session
- periodically during long-running projects
- before promotion
- before closeout

They answer questions like:

- is the ontology current?
- are sources stale?
- do candidate claims lack support?
- are there duplicate tasks?
- are there stale sessions?
- are artifacts missing lineage?

They should emit structured status such as:

```json
{
  "research_allowed": true,
  "promotion_allowed": false,
  "severity": "medium",
  "reason": "artifact lineage missing",
  "recommended_action": "rebuild_lineage_for_artifact",
  "affected_artifacts": ["artifacts/final_memo.md"]
}
```

### 2. Repair Planner

This converts audit findings into explicit maintenance tasks.

Repairs should be ranked by:

- severity
- scope
- reversibility
- promotion impact
- current lane contention

Repair tasks should not be implicitly equivalent to research blockers.

### 3. Maintenance Workers

These are occasional workers, not permanent health loops.

They should:

- run only on concrete repair tasks
- prefer deterministic or low-risk fixes
- operate in isolated branches or patch proposals when touching planner or integrity state
- be throttled so they do not starve research work

## What Should Block

### Should Not Block Research

The following should not block research, coding, data, or draft artifact generation:

- missing final audit
- missing claim evidence
- stale source warning
- incomplete lineage
- partially stale ontology
- open repair task
- non-promoted artifact
- source not yet trusted

These conditions should instead downgrade trust or promotion state.

### Should Block Specific Risky Operations

The following may block the specific risky operation they affect:

- secret leak risk
- invalid `rail.yaml`
- active branch conflict
- repo corruption risk
- attempt to promote unsupported claim
- attempt to publish final artifact with failed verification
- attempt to use inadmissible source for a trusted claim
- attempt to close project with active sessions

### Promotion-Only Blocking

The default rule should be:

- candidate work is allowed
- trusted work is gated

## Candidate Work Contract

RAIL should explicitly support messy intermediate states.

A worker should be allowed to emit a claim like:

```json
{
  "claim": "Cold weather appears associated with higher real-time prices in ISO-NE.",
  "status": "candidate",
  "trust_level": "unverified",
  "blockers": [
    "NOAA extract not fully linked",
    "price panel not verified",
    "lineage incomplete"
  ]
}
```

Health should then explain:

- the claim exists
- the claim is useful
- the claim is not trusted yet
- the system knows what is missing

This is better than preventing the claim from being created.

## Audit Write Policy

The audit system should be observational by default and durable only at meaningful transition points.

### Idempotent Audit Writes

Before writing a durable audit certificate, compute a stable identity:

`audit_key = session_id + base_commit + terminal_status + payload_hash`

If the stored key already matches:

- skip rewrite
- skip Git commit
- skip autopilot wakeup

The same session should not produce repeated durable commits for the same audit payload.

### Commit Audits Only On Transitions

Durable audit commits should happen only when one of the following occurs:

- a session reaches a terminal state
- an artifact is promoted
- a claim is verified or rejected
- a branch is merged
- a project is closed
- a user explicitly checkpoints the project

High-frequency health snapshots should not be committed by default.

### Ignore Audit-Only Churn

Autopilot should ignore commits that modify only:

- `research_plan/audits/**`
- `research_plan/state/latest_audit.json`
- `.rail_runtime/**`

unless the underlying gate status changed in a way that affects:

- promotion readiness
- closeout readiness
- lane availability

## Runtime vs Repo Storage

Git should store durable certificates.

Git should not store high-frequency monitoring noise.

### Store In Runtime or Projection State

High-frequency status should live in:

- Convex or runtime DB
- projection endpoints
- `.rail_runtime/`
- in-memory lane state

### Store In Git

Durable repo state should include:

- terminal session certificates
- promotion certificates
- verification certificates
- closeout certificates
- explicitly accepted repair decisions

## Maintenance Safety Model

Maintenance workers should prefer proposals before mutation.

Recommended outputs:

- `research_plan/repair_proposals/<id>.json`
- branch-isolated patch
- structured deterministic fix plan

RAIL can then decide to:

- auto-apply a small safe repair
- queue a medium repair
- ask the operator about a risky repair
- ignore a low-value repair

Cleaners should not freely rewrite planner, lineage, and audit files on the active research branch while research workers are running.

## Lifecycle Policy

The lifecycle should be relaxed for candidate work and strict for promotion.

### Previous Implicit Model

`brief -> source discovery -> hydration -> ontology health -> research -> artifacts -> audit -> close`

### New Model

`brief -> source discovery -> hydration -> research may start with partial data -> audits run continuously -> artifacts remain draft until gates pass -> promotion and closeout require clean health`

### Phase Behavior

When the project is in `research_active`:

Allowed:

- source discovery
- coding
- analysis
- candidate claims
- draft artifacts
- additional hydration

Blocked:

- verified artifact promotion
- final memo publication
- project closeout

This prevents ontology and integrity perfection from becoming a prerequisite for learning.

## Work Order Implications

Health should be represented as structured governance state, not primarily as a conversational actor.

Work orders should consume fields like:

- `auditor_status`
- `promotion_allowed`
- `research_allowed`
- `severity`
- `affected_artifacts`
- `recommended_action`

External executors should be able to read this state and continue productively without relying on long health-agent conversations.

## Required API and Service Changes

### Autopilot

- allow research tasks to proceed when auditors are blocking promotion but not blocking safety
- separate `research_allowed` from `promotion_allowed`
- deprioritize maintenance when a higher-value research task is ready
- ignore audit-only repo churn unless trust boundary state changes

### Audit Service

- make durable audit writes idempotent
- expose latest auditor status separately from durable certificates
- classify findings by severity and boundary impact

### Reconciliation Service

- emit repair proposals for non-urgent issues
- distinguish safe auto-repair from advisory findings
- avoid mutating trusted state for low-severity projection drift during active research

### Planner

- treat maintenance as a separate task class
- stop inserting repair tasks ahead of substantive research unless they unblock safety-critical execution
- represent candidate outputs explicitly rather than treating all incomplete work as failure

### Control Plane

Surface:

- current lane
- research allowed
- promotion allowed
- top blockers
- trust state of latest artifacts
- active repair proposals

The operator should see exactly why research can continue and exactly why promotion cannot.

## Migration Strategy

### Phase 1

- make audit writes idempotent
- add `research_allowed` and `promotion_allowed` to auditor outputs
- stop audit-only commits from waking autopilot unless gate status changed

### Phase 2

- move high-frequency health snapshots out of Git
- introduce maintenance task class and repair proposals
- deprioritize health tasks in the main lane unless safety-critical

### Phase 3

- require promotion-only gates for claims and artifacts
- add candidate, draft, unverified, blocked_for_promotion, verified, and rejected trust states
- expose lane and trust-state views in the operator UI

## Success Criteria

This spec is successful when:

- repeated audit commits for unchanged session payloads stop occurring
- research tasks continue to make forward progress while health findings remain open
- candidate claims and draft artifacts are preserved instead of suppressed
- promotion remains fail-closed
- closeout remains fail-closed
- the operator can clearly distinguish "research may continue" from "trusted promotion is blocked"

## Bottom Line

RAIL should not block learning in order to maintain cleanliness.

It should maintain cleanliness continuously in the background and block only when the system is about to:

- trust a claim
- promote an artifact
- merge a branch
- publish a result
- close a project

That is the right balance between autonomy, rigor, and forward progress.
