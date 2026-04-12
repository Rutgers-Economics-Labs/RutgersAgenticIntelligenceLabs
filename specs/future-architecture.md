# Future Architecture

This document defines the next platform contract for RAIL.

The guiding principle is:

- keep the ontology kernel and hydration engine stable
- move project truth into a Git-backed repo contract
- keep the database lightweight and operational
- run one worker agent at a time in V1
- require human approval before write-capable agent execution

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
- agent session tracking
- run state
- approval gates
- task board state
- cost tracking

This data lives in the database, not in ontology artifacts.

### 4. Agent Runner Layer

Responsible for:

- dispatching tasks to managed agent backends
- handling callbacks, questions, logs, and status transitions
- enforcing per-agent capabilities and secret allowlists

V1 supports one active worker at a time. The first production runner is Jules.

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
5. Tasks are stored in the internal task board
6. User approves the next execution step
7. Exactly one worker agent runs
8. Worker commits outputs into the repository contract
9. Health and verification checks run
10. Planner updates plan status and proposes the next task

## Approval Gates

Human approval is required before:

- starting any write-capable worker run
- publishing agent-generated changes
- promoting project-specific skills into a broader shared library

Automatic deterministic checks may run without approval when they are read-only.

## Internal Task Board

The planning agent owns an internal task system similar to Jira or Kanban.

This is not the source of truth for project content. It is the source of truth for project execution state.

The planner creates tasks from the active spec and plan, then advances them sequentially.
For visibility, the planner also mirrors the current board state and task summaries into Git under `research_plan/`.
The database remains the operational store for status transitions, timestamps, runner metadata, and approvals.

Core task statuses:

- `backlog`
- `ready`
- `awaiting_approval`
- `running`
- `blocked`
- `review`
- `done`
- `cancelled`

The planner updates task state after every agent callback or verification event.

## Key Architectural Rules

- Git is the source of truth for project content
- `.ontology/` is the source of truth for hydration inputs
- `rail.yaml` is the source of truth for project structure and agent policy
- the database stores operational state only
- planner task state is mirrored into Git for visibility, but executed from DB state
- agents may create knowledge under `topics/`, but they may not invent top-level contracts
- every agent write must target an allowed path based on role
- verification should prefer deterministic checks over LLM judgment

## Out of Scope for V1

- concurrent workers on separate branches
- automatic merge conflict resolution
- global shared project skills without review
- direct cloud execution through multiple runner backends on day one
