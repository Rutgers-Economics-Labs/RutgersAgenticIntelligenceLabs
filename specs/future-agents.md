# Future Agents

This document defines the V1 agent model for the future RAIL platform.

## Core Principles

- one worker agent runs at a time
- the planner is the only agent that talks directly to the user
- every worker gets a bounded task with allowed paths and allowed secrets
- every write-capable run requires human approval
- project skills are local to the project by default

## Agent Roles

### Planner

Purpose:

- converse with the user
- gather missing requirements
- write plans into `research_plan/`
- write or update durable specs in `specs/`
- create and sequence tasks in the task board
- decide which worker should run next
- relay worker questions back to the human when necessary
- answer worker questions directly when the answer already exists in project context
- own the single active execution slot in V1

Key outputs:

- plan documents
- spec updates
- task board entries
- approval requests

### Research Agent

Purpose:

- gather external information
- read websites, papers, and documentation
- synthesize findings into project knowledge
- organize materials inside `topics/`
- prepare reusable context for data, coding, artifact, and health work

Key outputs:

- summaries
- source notes
- citations
- downloaded references and cleaned notes

### Data Agent

Purpose:

- extend or refine ontology-backed data coverage
- author source YAML and pipeline YAML
- write ingestion transforms
- run dry checks for new data mappings

Key outputs:

- `.ontology/sources/*.yaml`
- `.ontology/pipelines/*.yaml`
- optional transforms
- data quality notes

### Coding Agent

Purpose:

- write scripts that operate on hydrated ontology data and topic context
- perform analysis
- generate structured outputs for downstream artifacts

Key outputs:

- topic scripts
- output JSON and charts
- analysis notebooks or Python scripts

### Artifact Agent

Purpose:

- package outputs for presentation
- generate papers, dashboards, visualizations, and polished summaries

Key outputs:

- files in `artifacts/`
- dashboard configs
- report bundles

### Health Agent

Purpose:

- enforce repo hygiene
- validate that outputs match the approved spec
- audit new project skills
- identify unnecessary generated files and failed run debris

Key outputs:

- health report
- cleanup proposals
- skill review outcomes

## Planner and Worker Control Flow

V1 uses a planner-controlled sequential workflow:

1. the planner talks to the human and writes the active plan
2. the planner creates or updates tasks in the internal board
3. the planner selects exactly one worker task to run
4. the user approves the run
5. the worker executes inside its allowed repo paths and secret policy
6. any worker questions are routed back to the planner
7. the planner either answers from context or asks the human
8. the worker completes and writes durable outputs into Git
9. health and deterministic verification run
10. the planner updates `research_plan/` and proposes the next step

## Planner-Owned Task Board

The planner uses an internal task board stored in the database.
For Git visibility, the planner also writes a mirrored human-readable board snapshot into `research_plan/`.

Suggested entities:

- `task_boards`
- `tasks`
- `task_events`

Task fields:

- `project_id`
- `session_id`
- `title`
- `description`
- `status`
- `agent_role`
- `repo_paths`
- `acceptance_criteria`
- `depends_on_task_ids`
- `approval_state`
- `created_at`
- `updated_at`

The planner writes human-readable plan documents and board snapshots to `research_plan/`, but the database is the operational system for task sequencing and status.

## Agent Sessions

The database stores operational session metadata for all planner and worker runs.

Suggested fields:

- `project_id`
- `role`
- `runner`
- `external_session_id`
- `status`
- `started_at`
- `ended_at`
- `estimated_cost_usd`
- `actual_cost_usd`
- `approval_required`
- `approval_granted_by`

Detailed user-facing content still lives in Git when it becomes durable project knowledge.

## Skills Model

### Global Starter Skills

The platform should ship a baseline set of global starter skills used when initializing a project.

Examples:

- repo contract rules
- citation formatting
- deterministic verification norms
- YAML style conventions
- artifact naming conventions

These are baseline starter skills, not a shared mutable memory pool.

These are copied into the project at setup time.

### Project Skills

All newly created skills live in the project `skills/` folder by default.

These may encode:

- source-specific ingestion knowledge
- domain-specific analysis procedures
- local verification checklists
- presentation conventions

### Promotion Workflow

Project skills are only promoted into a broader shared pool after explicit review.

The health agent can recommend promotion, but promotion should require human approval.
The health agent should also be able to flag project-local skills as stale, overbroad, or unsafe before reuse.

## Project Bootstrap Command

The platform should provide a simple project initialization flow that:

1. creates the required folder structure
2. writes a starter `rail.yaml`
3. copies global starter skills into `skills/`
4. writes starter planner and agent configs into `agents/`
5. initializes a starter plan document and board snapshot in `research_plan/`

This command may exist as:

- a CLI command
- a dashboard action
- or both

## Verification Rules

Verification should be deterministic whenever possible.

Examples:

- YAML validation
- path policy checks
- script execution success
- schema checks
- artifact existence checks
- task acceptance checklist completion

LLM review should support, not replace, these checks.

## V1 Runner Notes

- Jules is the first supported worker runner
- Claude Code remains a future runner adapter
- planner state should not depend on any single runner vendor
- the system should normalize runner questions, approvals, progress, and completion into a shared planner-facing model
