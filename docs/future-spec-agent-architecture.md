# Future Spec: Agent Architecture

Date: 2026-05-18

## Goal

Move RAIL from an agent-assisted research platform into a mostly autonomous, ontology-first research operating system.

The target is not just:

- run some agents
- produce some files
- hydrate some data

The target is:

- accept an open-ended research question
- turn it into a durable Git-backed project
- grow a structured graph of knowledge in folders and ontology
- expand the ontology when new questions require it
- run hydration, research, coding, and artifact synthesis safely
- reconcile its own state after every batch of work
- close cleanly when repo state, ontology state, integrity state, and live control-plane state agree

## What Stays From The Original Design

The original design is directionally correct and should remain the foundation:

- Git repo is the source of truth for project state
- `.ontology/` is the canonical hydration and ontology runtime surface
- `topics/` holds the knowledge graph in human-readable folder form
- `research_plan/` holds planning, tasking, approvals, and operational history
- `specs/` holds durable project contract and research framing
- `skills/` and `agents/` are repo-local and project-specific where needed
- hydration runs through the shared Python package and SDK
- one agent at a time is the right first operating model

## What Must Be Added

The soccer project showed that the original design is missing several critical layers.

### 1. Audited State Layer

Workers and planners should not write directly into trusted execution state without post-run reconciliation.

Add a mandatory audited state layer that runs after every meaningful batch:

- `session_auditor`
- `planner_auditor`
- `ontology_auditor`
- `integrity_auditor`
- `closeout_auditor`

These auditors establish actual project truth from:

- repo files
- active ontology artifacts
- hydration counts
- integrity gate results
- runner liveness

Autopilot should plan from audited state, not raw worker output.

### 2. Control Planes

The frontend and backend should be modeled as separate but connected planes.

#### Repo plane

Canonical project content:

- `.ontology/`
- `topics/`
- `specs/`
- `research_plan/`
- `skills/`
- `agents/`
- artifacts

#### Runtime plane

Ephemeral operational state:

- active sessions
- session cost
- start/end times
- transient approvals
- worker heartbeats
- secrets handles

#### Projection plane

Read models used by the UI:

- planner board
- ontology summary
- artifact gallery
- session timeline
- blocker dashboard
- integrity status

The repo plane is source of truth. The runtime plane is operational metadata. The projection plane is derived.

### 3. Hard Lifecycle Gates

The platform should enforce the following lifecycle:

1. brief capture
2. planner decomposition
3. source discovery
4. executable source configs
5. hydration
6. ontology health
7. ontology-backed research
8. artifact synthesis
9. closeout audit

No research completion should be allowed before ontology health passes.

No final artifact should be promotable before:

- integrity gate passes
- no active required tasks remain
- no live worker sessions remain
- the ontology artifact is active and current

### 4. Ontology Expansion As A First-Class Capability

The planner must classify every new research question into one of:

- answerable with current ontology
- answerable with recomputation only
- answerable after ontology expansion
- blocked by unavailable data

If expansion is needed, the planner must create:

- source acquisition task
- schema extension task
- transform or pipeline task
- hydration rerun task
- ontology health rerun task
- downstream research task

This is what turns the project into a growing graph of knowledge instead of a one-shot report tree.

### 5. Session Model

Treat every agent run as a Git-backed session with:

- repo base commit
- workspace branch
- role
- task id
- runner
- started/ended timestamps
- session outputs
- verification result
- reconciliation result

The DB should store only operational metadata and never become the source of truth for research content.

### 6. Secrets Model

Secrets should be:

- project-scoped
- agent-allowlisted
- optionally runner-allowlisted
- injected only at session start
- never written back into repo state

This matches the original design direction and should stay.

### 7. Skills Model

There should be two categories of skills:

#### Global skills

Available to every project by default:

- repo contract
- planner basics
- ontology basics
- integrity basics
- hydration basics
- artifact publishing basics

#### Project-local skills

Generated or curated inside the repo:

- source-specific extraction rules
- naming conventions
- domain-specific ontology mappings
- project-specific research methods

Generated project-local skills should themselves be audited by the health layer before being trusted by later sessions.

## Recommended Agent Roles

### Planner agent

Responsible for:

- decomposing the question
- maintaining task graph and specs
- routing user questions
- classifying new questions against current ontology coverage
- sequencing workers

Should not be trusted as the sole validator of completed reality.

### Research agent

Responsible for:

- literature review
- source discovery
- document synthesis
- folder organization inside `topics/`
- source notes and evidence capture

Should write structured research outputs, not just summaries.

### Data agent

Responsible for:

- source configs
- transforms
- pipeline steps
- hydration reruns
- ontology population

Should own `.ontology/` changes and data-quality evidence.

### Coding agent

Responsible for:

- analysis scripts
- derived metrics
- reproducible computations on top of ontology
- exportable tables and JSON outputs

Should never bypass ontology-backed evidence when the project has already reached hydration.

### Artifact agent

Responsible for:

- papers
- dashboards
- presentations
- visual narratives

Should be downstream of ontology-backed analysis, not upstream of it.

### Health agent

Responsible for:

- repo hygiene
- skill health
- stale file cleanup
- verifier drift checks
- contract enforcement

### Audit agents

These are new and critical.

Responsible for:

- reconciling session truth
- reconciling planner truth
- reconciling ontology truth
- reconciling integrity truth
- certifying closeout truth

## UI Requirements

The UI should expose:

- current planner intent
- current active session
- real ontology coverage
- current blockers by category
- repo-backed artifacts
- session history
- intervention history
- follow-up questions the ontology can answer

The user should be able to steer by:

- changing direction
- adding research questions
- approving or pausing tasks
- choosing between expansions
- promoting or cancelling stale work

The user should not need chat alone to understand state.

## First Implementation Order

1. Add `rail.yaml` as a stronger project contract and bootstrap surface.
2. Add audited post-run reconciliation before autopilot can relaunch work.
3. Split repo truth from runtime truth from UI projections.
4. Make ontology expansion a planner-native operation.
5. Add UI surfaces for planner reasoning, ontology coverage, and blocker type.
6. Keep one-agent-at-a-time until reconciliation is reliable.
7. Only then add branch-parallel agent execution.

## Short Version

The biggest addition to the original design is not another worker role.

It is an audited reconciliation layer between agent output and future planning.

That is the missing piece that turns a collection of capable agents into a trustworthy autonomous research system.
