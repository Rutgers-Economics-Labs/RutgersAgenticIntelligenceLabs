# Future Frontend

This document defines the future dashboard for the RAIL platform.

For the detailed product spec, page-by-page information architecture, and
agent-observability requirements, see `specs/frontend-command-center.md`.

## Operating Model

The frontend is split evenly across three persistent planes:

- planner chat and execution control
- repository and knowledge views
- artifacts and run timeline
- workspace review and merge/adoption control
- research integrity views for assumptions, sources, claim evidence, lineage, and stale outputs

The UI should feel like an agent command center rather than a form-based admin console.
The frontend should prefer repository-backed rendering whenever durable project state is involved.

## Primary Layout

### Left Plane: Planner

Responsibilities:

- open-ended chat with the planner
- display approval requests
- display autonomy mode, active budgets, and policy boundaries
- show blocker questions from worker sessions
- show current plan summary
- show current task and next proposed task
- show current assumptions and decisions relevant to the active plan
- relay worker questions to the human only when the planner cannot answer them from existing context
- show unresolved todos/blockers that prevent merge or adoption

### Center Plane: Repository

Responsibilities:

- render the repo tree based on `rail.yaml`
- show `specs/`, `research_plan/`, `.ontology/`, `topics/`, `skills/`, and `agents/`
- show `research_plan/state/` integrity indexes in human-friendly forms
- open files with syntax-aware viewers
- show commit and diff context for current session outputs
- keep the topic tree flexible and exploratory rather than schema-bound
- show active workspace branch/worktree context when a worker is running

### Right Plane: Artifacts and Timeline

Responsibilities:

- render dashboards, charts, and reports from `artifacts/`
- show the sequential timeline of planner and worker runs
- show verification and health status
- show artifact promotion state, lineage, claim evidence, and stale-output warnings
- show completed task history and costs
- show workspace diffs, todos, checkpoints, and merge/adoption controls

This plane should render repo-backed artifacts from `artifacts/` while also showing live runner status from the operational database.

## Loading Model

The frontend should render project content primarily from the Git repository and the `rail.yaml` manifest.
In hosted mode, the default read model should be the latest commit on the configured default branch.
For GitHub-backed projects, this can be implemented with raw file fetches, tree APIs, or a lightweight repo content proxy.

The database supplements the repo with operational data:

- currently running agents
- secrets metadata
- active runner status and reconnect handles
- live runner events that have not yet been mirrored into files
- autonomy policy and budget status
- lightweight indexes for assumptions, sources, claims, artifact lineage, and verification status

The database should not be treated as the primary renderer for plans, specs, topics, ontology files, or artifacts.
The frontend should load task board state, approvals, blockers, and completed session summaries from repo-backed files whenever possible.

## Primary Screens

### Project Home

Shows:

- planner chat
- active plan
- top-level repo summary
- latest artifacts
- recent runs

### Spec View

Shows:

- files from `specs/`
- approval history
- planner-authored changes

### Plan View

Shows:

- files from `research_plan/`
- current task board
- dependencies and blockers
- assumptions, decisions, methodology, open questions, and rerun options

The frontend should render both:

- the Git-visible planner task board in `research_plan/`
- the currently running agent state from the live control database

Task cards should deep-link to the exact repo paths assigned to the active worker.
Task cards should also deep-link to the worker session folder, diff review, todos, and verification output when present.
Task cards should expose integrity status: sources touched, assumptions touched, artifacts touched, verification status, and promotion state.

### Workspace Review View

Shows:

- active worker session
- workspace branch or worktree path
- changed files and diff summary
- unresolved todos/blockers
- verification output
- assumptions, source records, claim evidence, and artifact lineage created by the session
- checkpoint/snapshot metadata
- merge/adoption approval control

This view is the RAIL equivalent of Conductor's diff/review flow. Worker completion should not automatically mean the changes are adopted.
In autopilot modes, this view should also show which steps were auto-approved by policy and which policy boundary would require human review.

### Ontology View

Shows:

- `.ontology/ontology.yaml`
- source and pipeline inventories
- hydration status
- validation results

### Topic Workspace View

Shows:

- navigable topic tree
- notes, scripts, and outputs inside `topics/`
- topic-local graphs of files and outputs when available

The UI should not force a rigid schema within a topic subtree.
It should simply understand conventions like `overview.md`, `scripts/`, `outputs/`, and nested subtopics when present.

### Artifact View

Shows:

- reports
- PDFs
- chart bundles
- dashboard JSON rendered into interactive components
- promotion state and verification status
- artifact lineage graph
- assumptions and sources used
- claim evidence for narrative/report claims
- stale-output warnings and rerun actions

Every artifact should support quick actions:

- explain this
- show source data
- show generating script or query
- show assumptions
- show verification
- rerun affected outputs
- compare with previous version

### Research Integrity View

Shows:

- assumption ledger with editable assumptions and affected outputs
- decision ledger and methodology notes
- source/provenance ledger for datasets, citations, API calls, downloads, and manual inputs
- claim-to-evidence map
- artifact lineage map
- stale-output queue
- verification run history

This view should make the system inspectable without forcing users to read raw logs.
It should answer practical questions:

- What assumptions did RAIL make?
- Which artifacts depend on this assumption?
- What data supports this claim?
- Which outputs are stale?
- What needs to rerun if I change this?
- Which outputs are verified enough to trust?

### Rerun and Assumption Editing UX

Users should be able to change an assumption from the UI and see the affected downstream outputs before rerunning.

Expected flow:

1. User edits or adds an assumption.
2. UI shows affected datasets, scripts, charts, reports, and dashboards.
3. Planner proposes a rerun task set.
4. Autonomy policy decides whether rerun starts immediately or asks for approval.
5. New outputs are compared against previous outputs.
6. Stale markers are cleared only after successful rerun or revalidation.

## Task Board UX

The planner-owned task system should be visible in the UI as a simple Kanban-style board with a timeline companion.

Columns:

- backlog
- ready
- awaiting approval
- running
- blocked
- review
- done
- stale

The task board is operational state from the database, but each task should deep-link to relevant repo files and session events.
The UI should also surface the planner-authored Git snapshot so users can inspect planned work as durable project context.

## Project Setup UX

The platform should support a simple setup flow that:

- creates a repo using the required folder contract
- writes `rail.yaml`
- installs starter project skills
- initializes starter `agents/` files
- creates an initial `research_plan/` document
- creates initial assumption, provenance, claim-evidence, and artifact-lineage files
- creates optional workspace scripts under `scripts/`

The setup flow should be available from the dashboard.
It should also exist as a bootstrap command for local-first users.

## Database Surfaces Needed By Frontend

Minimum operational surfaces:

- `projects`
- `project_secrets`
- `running_agents`
- autonomy policy and budget status
- active runner reconnect/status handles
- optional live event cache for events not yet flushed to repo files
- lightweight indexes for assumptions, sources, claims, artifact lineage, and verification status

Repo-backed frontend surfaces:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/assumptions.md`
- `research_plan/decisions.md`
- `research_plan/methodology.md`
- `research_plan/provenance.md`
- `research_plan/claim_evidence.md`
- `research_plan/open_questions.md`
- `research_plan/rerun_options.md`
- `research_plan/verification_summary.md`
- `research_plan/state/assumptions.json`
- `research_plan/state/sources.json`
- `research_plan/state/claims.json`
- `research_plan/state/artifact_lineage.json`
- `research_plan/state/verification_runs.json`
- `research_plan/tasks/*.md`
- `research_plan/approvals.md`
- `research_plan/blockers.md`
- `research_plan/sessions/**/summary.md`
- `research_plan/sessions/**/diff.md`
- `research_plan/sessions/**/todos.md`
- `research_plan/sessions/**/verification.md`

## Design Direction

The redesign should preserve a calm, structured research-tool feel.

Preferred characteristics:

- split-pane layout with strong information hierarchy
- repo-aware navigation
- visible execution state without log overload
- artifact-first presentation for final outputs
- assumption/evidence-first trust surfaces for final outputs
- clean approval and blocker UX
- equal emphasis on planner, repo, and artifact/timeline planes
