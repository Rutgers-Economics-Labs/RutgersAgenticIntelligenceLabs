# Future Architecture

This document defines the next platform contract for RAIL.

The guiding principle is:

- keep the ontology kernel and hydration engine stable
- move project truth into a Git-backed repo contract
- keep the database lightweight and operational
- run one worker agent at a time in V1
- require human approval before write-capable agent execution

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

### 5. Presentation Layer

Responsible for:

- planner chat
- task board and run history
- repo-backed file views
- artifact rendering
- verification and approval UX

## V1 Execution Model

The first release uses a sequential planner-controlled workflow:

1. User chats with the planner
2. Planner writes or updates specs in `specs/`
3. Planner writes execution plans in `research_plan/`
4. Planner decomposes work into tasks
5. Tasks are stored as Markdown task cards under `research_plan/tasks/`
6. User approves the next execution step
7. Exactly one worker agent runs in an isolated session workspace
8. Worker questions and approval requests are relayed back to the planner
9. Worker changes are reviewed through a diff/review step before merge or adoption
10. Health and verification checks run
11. Planner updates repo-backed plan/task/session files and proposes the next task

## Approval Gates

Human approval is required before:

- starting any write-capable worker run
- publishing agent-generated changes
- promoting project-specific skills into a broader shared library

Automatic deterministic checks may run without approval when they are read-only.

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
7. **Adopt or merge:** require human approval before publishing, merging, or copying changes into the canonical branch.
8. **Archive workspace:** clean up temporary workspaces and external resources after the durable session summary is written.

V1 still enforces one active worker at a time. The workspace abstraction exists so V2 can safely allow parallel workers on separate branches/worktrees.

## Merge Blockers And Checkpoints

RAIL should support two lightweight safety mechanisms:

- **Todos as blockers:** task acceptance criteria, unresolved questions, failed checks, and health-agent findings should block merge/adoption until resolved.
- **Checkpoints:** before each planner-approved worker turn, capture a lightweight Git snapshot or private ref so the system can explain and undo changes from that turn without confusing durable project history.

## Key Architectural Rules

- Git is the source of truth for project content
- `.ontology/` is the source of truth for hydration inputs
- `rail.yaml` is the source of truth for project structure and agent policy
- the latest commit on the configured default branch is the source of truth for what the UI renders
- the database stores operational state only
- planner task state lives in Git; active execution handles live in the database
- agents may create knowledge under `topics/`, but they may not invent top-level contracts
- every agent write must target an allowed path based on role
- verification should prefer deterministic checks over LLM judgment
- write-capable workers should run in an isolated workspace/branch when possible
- merge or adoption is separate from task execution and requires human approval

## Out of Scope for V1

- concurrent workers on separate branches
- automatic merge conflict resolution
- global shared project skills without review
- direct cloud execution through multiple runner backends on day one
