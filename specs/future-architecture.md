# Future Architecture

This document defines the next platform contract for RAIL.

The guiding principle is:

- keep the ontology kernel and hydration engine stable
- move project truth into a Git-backed repo contract
- keep the database lightweight and operational
- run one worker agent at a time in V1
- support configurable autonomy while keeping research evidence-gated
- require human approval only at policy-defined escalation boundaries

## Keep, Remove, and Add

### Keep

- the YAML-backed ontology and hydration kernel
- the Python package and SDK for hydration and ontology access
- deterministic validation and verification primitives
- repo-backed project state and file-based knowledge organization
- project-local skills and role files
- isolated worker workspaces using Git branches or worktrees as the unit of change

### Remove or De-Emphasize

- database-first storage of project content
- mirrored platform state acting as the durable source of truth for specs, plans, ontology files, or artifacts
- a generic multi-agent swarm in V1
- frontend flows that prioritize forms and records over the repository tree
- coupling the ontology kernel to a specific runner vendor

### Add

- a planner-first orchestration model with specialized worker roles
- a Git-native repository contract rooted in `rail.yaml`
- a planner-owned Kanban/task system stored in Git-visible files under `research_plan/`
- autonomy modes that let trusted projects run in fire-and-forget mode
- a research integrity layer for assumptions, provenance, claim evidence, and reproducibility
- runner adapters that normalize vendor events into a shared planner control flow
- workspace setup, run, review, and archive hooks for repeatable agent execution
- health and auditing as a first-class role

## Product Thesis

RAIL is a Git-native research and analysis platform for ontology-driven economic work.

Each project is a repository with two major surfaces:

- `.ontology/` contains the declarative ontology, source definitions, and hydration pipelines used by the Python package
- the rest of the repository contains research plans, agent context, scripts, analysis outputs, and artifacts intended for human and agent collaboration

The platform dashboard reads from this repository structure to show plans, progress, outputs, and artifacts in a structured way.

## Stable Kernel

The following parts are treated as the stable kernel and should be preserved:

- YAML ontology definition and extension model
- YAML source and pipeline definition model
- Python hydration package and SDK surface
- ontology export and query flow
- deterministic validation and verification primitives

The kernel should not be coupled to product-specific agent workflows.

## Future Platform Layers

### 1. Kernel Layer

Responsible for:

- loading `rail.yaml`
- reading `.ontology/`
- validating YAML configs
- executing hydration jobs
- exposing a Python package and service interface for ontology access

### 2. Repository Contract Layer

Responsible for:

- defining the canonical project structure
- giving the frontend a stable filesystem contract
- giving agents predictable write targets
- separating ontology state from project research state

### 3. Operational Control Layer

Responsible for:

- secrets management
- active agent session handles
- live run state
- approval gates that need immediate interaction
- lightweight cost/status metadata

This layer is intentionally small. Durable plans, tasks, approvals, session summaries, and artifacts live in the repository. The database should keep only projects, currently running agents, and encrypted secrets/policies.

### 4. Agent Runner Layer

Responsible for:

- dispatching tasks to managed agent backends
- handling callbacks, questions, logs, and status transitions
- enforcing per-agent capabilities and secret allowlists
- preparing isolated workspaces for write-capable workers
- mirroring live session events into repo-backed files

V1 supports one active worker at a time. The first production runner is Jules.
The planner remains the only role that talks directly to the human.

Conductor's useful lesson for RAIL is that workers should not edit the canonical working tree directly when they can instead work in an isolated Git workspace. In V1, RAIL may still run only one worker at a time, but each write-capable session should be modeled as a workspace with a branch, a setup step, a run/test step, a review step, and an archive/cleanup step.

### 5. Research Integrity Layer

Responsible for:

- recording assumptions, decisions, and methodology choices as durable project state
- recording source provenance for every dataset, citation, API call, downloaded reference, and manual input
- mapping important artifact/report claims to evidence files, queries, scripts, source notes, or datasets
- tracking artifact lineage from sources and assumptions through scripts, datasets, charts, dashboards, and reports
- marking outputs stale when an upstream assumption, source, script, or dataset changes
- enforcing promotion gates from exploratory output to verified artifact to final deliverable
- producing confidence/status labels such as `exploratory`, `needs_evidence`, `partially_verified`, `verified`, `stale`, and `blocked`
- preferring deterministic reproducibility checks over LLM judgment

This layer is what lets RAIL become more autonomous without becoming less trustworthy.
Agents may explore freely inside their allowed workspaces, but outputs should not be promoted as trusted deliverables unless they have evidence, lineage, and verification metadata.

### 6. Presentation Layer

Responsible for:

- planner chat
- task board and run history
- repo-backed file views
- artifact rendering
- verification and approval UX

## V1 Execution Model

The first release uses a sequential planner-controlled workflow with configurable autonomy:

1. User chats with the planner
2. Planner writes or updates specs in `specs/`
3. Planner writes execution plans in `research_plan/`
4. Planner decomposes work into tasks
5. Planner records initial assumptions, source requirements, and verification expectations
6. Tasks are stored as Markdown task cards under `research_plan/tasks/`
7. Runtime checks the configured autonomy policy for whether the next step may proceed
8. Exactly one worker agent runs in an isolated session workspace
9. Worker questions and approval requests are relayed back to the planner only when policy requires escalation
10. Worker outputs include assumptions, source records, artifact lineage, and claim evidence
11. Health and deterministic verification checks run
12. Outputs that pass evidence gates may be promoted; failed checks become blockers or open questions
13. Planner updates repo-backed plan/task/session files and proposes or starts the next task according to autonomy policy

## Autonomy Modes

RAIL should support project-level autonomy modes rather than hard-coding one approval posture for all projects.

Suggested modes:

- `assisted`: human approval is required before write-capable worker runs and before adoption/publish actions.
- `supervised_autopilot`: routine write-capable research work may run automatically, but high-risk actions and low-confidence outputs require human approval.
- `autopilot`: the planner may continue decomposing, executing, verifying, repairing, and regenerating artifacts until the research plan is complete or a policy boundary is crossed.

Example manifest shape:

```yaml
autonomy:
  mode: supervised_autopilot
  require_human_for:
    - publish_changes
    - destructive_delete
    - paid_api_over_budget
    - missing_source_data
    - low_confidence_claims
    - methodology_change_with_material_effect
  allow_without_human:
    - plan_decomposition
    - source_discovery
    - data_ingestion
    - analysis_scripts
    - artifact_generation
    - verification
    - assumption_recording
  max_runtime_minutes: 180
  max_cost_usd: 20
  max_retries_per_task: 3
```

Autonomy policy should be enforced before dispatch, before publishing/adoption, and before any destructive or externally visible operation.
If a task crosses a policy boundary, it should become `blocked` or `awaiting_approval` with a clear explanation.

## Approval Gates

Human approval is required when the configured autonomy policy requires it.

Common approval boundaries:

- publishing agent-generated changes
- destructive deletion outside ephemeral generated files
- changing methodology in a way that materially changes conclusions
- accepting low-confidence or partially verified claims into final artifacts
- continuing when required source data is missing or sources materially disagree
- promoting project-specific skills into a broader shared library

In assisted mode, starting write-capable worker runs may also require approval.
In autopilot modes, routine write-capable research work can proceed without approval if it stays inside role path allowlists and project policy limits.
Automatic deterministic checks may run without approval.

## Internal Task Board

The planning agent owns an internal task system similar to Jira or Kanban.

This is not a durable database feature. It is a repo-backed planning surface.

The planner creates tasks from the active spec and plan, then advances them sequentially.
The current board state and task summaries live in Git under `research_plan/`.
The database only tracks live handles needed to interact with currently running agents.

Core task statuses:

- `backlog`
- `ready`
- `awaiting_approval`
- `running`
- `blocked`
- `review`
- `done`
- `cancelled`

The planner updates task state after every agent callback or verification event by editing the repo-backed task files.
The planner decides when a worker question can be answered from project context and when it must be escalated to the human.

## Workspace Lifecycle

RAIL should adopt the strongest parts of Conductor's workspace model while keeping the planner-first architecture:

1. **Create workspace:** start from the configured default branch or an approved task branch.
2. **Setup workspace:** run a repo-defined setup script to install dependencies and inject only allowlisted environment files/secrets.
3. **Run worker:** execute Jules, Claude Code, Codex, or another adapter with a bounded task payload.
4. **Mirror session:** write normalized events to `session.ndjson`, commands to `commands.ndjson`, state to `state.json`, and summaries to `summary.md`.
5. **Test workspace:** run a repo-defined verification command or run script.
6. **Review diff:** show changed files, task acceptance status, todos, and verification results before merge.
7. **Adopt, merge, or publish:** apply autonomy policy before publishing, merging, or copying changes into the canonical branch.
8. **Archive workspace:** clean up temporary workspaces and external resources after the durable session summary is written.

V1 still enforces one active worker at a time. The workspace abstraction exists so V2 can safely allow parallel workers on separate branches/worktrees.

## Merge Blockers And Checkpoints

RAIL should support two lightweight safety mechanisms:

- **Todos as blockers:** task acceptance criteria, unresolved questions, failed checks, and health-agent findings should block merge/adoption until resolved.
- **Checkpoints:** before each planner-approved worker turn, capture a lightweight Git snapshot or private ref so the system can explain and undo changes from that turn without confusing durable project history.
- **Evidence gates:** unsupported claims, unsourced datasets, missing lineage, failed verification, and stale assumptions should block artifact promotion.

## Key Architectural Rules

- Git is the source of truth for project content
- `.ontology/` is the source of truth for hydration inputs
- `rail.yaml` is the source of truth for project structure and agent policy
- the latest commit on the configured default branch is the source of truth for what the UI renders
- the database stores operational state only
- planner task state lives in Git; active execution handles live in the database
- agents may create knowledge under `topics/`, but they may not invent top-level contracts
- every agent write must target an allowed path based on role
- every nontrivial dataset must have source provenance or be explicitly marked synthetic/test data
- every final artifact must have lineage metadata and verification status
- important report claims should map to evidence before promotion to final deliverable
- assumption changes should mark dependent outputs stale until rerun or revalidated
- verification should prefer deterministic checks over LLM judgment
- write-capable workers should run in an isolated workspace/branch when possible
- merge, publish, or adoption is separate from task execution and follows autonomy policy

## Out of Scope for V1

- concurrent workers on separate branches
- automatic merge conflict resolution
- global shared project skills without review
- direct cloud execution through multiple runner backends on day one
