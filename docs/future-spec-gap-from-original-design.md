# Future Spec: Gap From The Original Design

Date: 2026-05-18

## Summary

The original design was strong on the repo contract, agent roles, and ontology-first philosophy.

What it underestimated was the amount of machinery needed to keep all of these layers in sync once real autonomous work starts:

- repo files
- planner tasks
- runner sessions
- active ontology artifacts
- integrity ledgers
- UI projections

The soccer project proved that the high-level design works, but also showed exactly where it needs more structure.

## What The Original Design Got Right

### 1. Git as source of truth

This is still correct.

The actual research state should live in:

- the repo
- the ontology folder
- project specs
- research plan
- topic folders
- artifacts

The DB should stay lightweight and operational.

### 2. Ontology-first project shape

This was also correct.

The `.ontology/` folder should remain the canonical surface for:

- source definitions
- transforms
- pipelines
- ontology schema
- hydration jobs

### 3. Role-based agents

The division between:

- planner
- research
- data
- coding
- artifact synthesis

still makes sense.

### 4. Open-ended question flow

The idea that the planner chats with the human, refines parameters, and adjusts the plan over time is also right.

### 5. Project-specific skills

Repo-local skills are a good design choice and should remain part of the system.

## Where The Original Design Was Incomplete

### 1. Planner truth was treated as too authoritative

Original design:

- planner writes plan
- planner creates tasks
- workers do tasks
- planner advances project

What the soccer project taught:

- planner state often diverges from actual repo reality
- runner state often diverges from actual session reality
- closeout state often diverges from actual integrity reality

So planner truth cannot be the final truth.

Needed addition:

- audited truth layer after worker batches

### 2. The board and task system needed stronger semantics

Original design implied a Jira/Kanban style system, which is good.

What was missing:

- canonical task identity rules
- supersession rules
- stale task cleanup
- duplicate/truncated task prevention
- evidence-based task completion

Without these, the board becomes noisy and trust erodes quickly.

### 3. Hydration needed to be a harder gate

Original design assumed the ontology would be hydrated on demand through the package.

That part is fine.

What was missing was the enforcement that:

- research cannot be treated as complete before hydration
- dashboards/papers cannot count as final before ontology health passes
- planner cannot stop early just because a lot of planning files exist

### 4. The DB/runtime model needed clearer boundaries

Original design was close here, but not strict enough in practice.

Needed rule:

- DB stores only operational metadata
- repo stores all durable project state
- UI projections are derived from repo + audited runtime metadata

If the runtime DB is allowed to drift into state authority, the system becomes hard to reconcile.

### 5. Health/cleanup was under-scoped

You already anticipated a health agent, which was good.

But the soccer project showed that “delete unnecessary files and keep things organized” is not enough.

The health layer must also detect:

- stale sessions
- zombie processes
- duplicated tasks
- integrity drift
- stale ontology pointers
- repo/runtime mismatches

That is bigger than hygiene. It is operational reconciliation.

### 6. Agent sessions needed stronger contracts

Original design treated sessions mostly as cloud-agent work episodes.

What was missing:

- explicit session lineage
- session reconciliation rules
- durable finalization semantics
- post-run audit requirement

Without that, a worker can do correct work and still leave the platform in a wrong state.

### 7. The knowledge graph needed two forms

Your design already had:

- folder graph in `topics/`
- ontology graph in `.ontology/`

What needs to be made more explicit is that these are different but linked:

#### Folder knowledge graph

Human-readable:

- notes
- papers
- analyses
- source summaries
- subtopics

#### Ontology knowledge graph

Machine-queryable:

- entities
- measures
- relations
- observations
- participation records

The future spec should treat these as coupled layers, not interchangeable ones.

## What Must Be Added To Reach The Intended Design

### Add `rail.yaml` as the explicit project contract

It should declare:

- project metadata
- default pipeline
- repo contract expectations
- ontology entrypoints
- agent policies
- secret scopes
- allowed runners
- completion gates

### Add audited post-batch reconciliation

After each worker batch:

- inspect actual repo outputs
- inspect actual ontology outputs
- inspect actual session state
- update planner state from evidence

### Add phase-aware completion rules

The system should know whether a project is:

- scoped
- source-ready
- hydration-ready
- hydrated
- ontology-healthy
- research-active
- synthesis-ready
- closed

### Add ontology expansion planning

The system should be able to absorb new user questions midstream by deciding whether:

- current ontology is enough
- recomputation is enough
- ontology expansion is required

### Add better steering surfaces

The original design assumed more conversational steering.

That still matters, but the UI also needs explicit control surfaces for:

- current active lane
- blocker type
- next queued tasks
- proposed expansions
- ontology coverage
- finalization readiness

## What This Means In Practice

The original design was mostly missing one architectural principle:

> agent output is not trusted state until it has been reconciled against project reality

That one principle explains most of the difference between the original design and the improved one.

## Bottom Line

The design did not need to be replaced.

It needed to be strengthened with:

- audited truth
- stricter lifecycle gates
- stronger session semantics
- stronger task semantics
- clearer separation between repo truth and runtime metadata

That is how it becomes a true end-to-end ontology-backed research platform instead of a promising but supervision-heavy agent workflow.
