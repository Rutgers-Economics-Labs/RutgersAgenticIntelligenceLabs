# Future Spec: `rail.yaml` Schema

Date: 2026-05-18

## Purpose

`rail.yaml` should become the explicit project contract for RAIL.

It should define:

- project identity
- repo contract
- ontology entrypoints
- default pipelines
- agent and runner policy
- secret scopes
- lifecycle gates
- verification policy

The goal is to make every project boot with a predictable structure while still allowing topic-specific flexibility.

## Design Principles

1. `rail.yaml` is the single manifest entrypoint for project runtime behavior.
2. Repo content remains authoritative; `rail.yaml` describes how to interpret and operate on that content.
3. All defaults must be overrideable, but every override should be explicit.
4. The schema must support both local mode and API mode.

## Proposed Top-Level Shape

```yaml
version: 1

project:
  name: European Soccer Competitive Ecosystem Analysis
  slug: european-soccer-competitive-ecosystem-analysis
  description: >
    Ontology-backed research project for domestic parity,
    persistence, and cross-competition participation.
  owners:
    - akash
  mode: ontology_first

repo_contract:
  required_paths:
    - .ontology
    - specs
    - research_plan
    - topics
    - agents
    - skills
  flexible_paths:
    - artifacts
    - topics/**
  source_of_truth: git

ontology:
  schema_path: .ontology/ontologies/project-ontology.yaml
  source_root: .ontology/sources
  pipeline_root: .ontology/pipelines
  transform_root: .ontology/transforms
  default_pipeline: project-default
  active_artifact_policy: latest_verified

research:
  brief_path: topics/brief.md
  spec_path: specs/research_question.yaml
  question_policy:
    allow_follow_up_generation: true
    allow_midstream_direction_change: true
    require_question_classification: true

planner:
  current_plan_path: research_plan/current_plan.md
  task_root: research_plan/tasks
  approval_root: research_plan/approvals
  decision_root: research_plan/decisions
  require_audit_before_advance: true
  lane_policy: single_active_worker

agents:
  planner:
    prompt_path: agents/prompts/planner.md
    checklist_path: agents/checklists/planner.md
    allowed_runners: [codex_cli, cursor_cli, jules]
  research:
    prompt_path: agents/prompts/research.md
    checklist_path: agents/checklists/research.md
    allowed_runners: [codex_cli, cursor_cli, jules]
  data:
    prompt_path: agents/prompts/data.md
    checklist_path: agents/checklists/data.md
    allowed_runners: [codex_cli, cursor_cli, jules]
  coding:
    prompt_path: agents/prompts/coding.md
    checklist_path: agents/checklists/coding.md
    allowed_runners: [codex_cli, cursor_cli, jules]
  artifact:
    prompt_path: agents/prompts/artifact.md
    checklist_path: agents/checklists/artifact.md
    allowed_runners: [codex_cli, cursor_cli, jules]
  health:
    prompt_path: agents/prompts/health.md
    checklist_path: agents/checklists/health.md
    allowed_runners: [codex_cli, cursor_cli]

auditors:
  enabled: true
  order:
    - session
    - planner
    - ontology
    - integrity
    - closeout
  fail_closed: true

verification:
  deterministic_command: scripts/run-verification.sh
  require_integrity_gate_for:
    - artifact_generation
    - closeout
  require_ontology_health_before:
    - research
    - artifact
  required_artifact_lineage: true
  required_claim_evidence: true

secrets:
  project_scope: true
  per_agent_allowlists: true
  inject_at_session_start_only: true
  allowed:
    research: [PERPLEXITY_API_KEY, GEMINI_API_KEY]
    data: [KAGGLE_USERNAME, KAGGLE_KEY]
    artifact: []

lifecycle:
  phases:
    - brief
    - scoped
    - source_discovery
    - config_ready
    - hydration_ready
    - hydrated
    - ontology_healthy
    - research_active
    - synthesis_ready
    - closed
  closeout_requires:
    - no_active_agents
    - no_non_done_required_tasks
    - clean_integrity_gate
    - final_artifacts_present
```

## Required Sections

### `project`

Required:

- `name`
- `slug`
- `mode`

Recommended:

- `description`
- `owners`

### `repo_contract`

Defines the minimum required project structure.

Required:

- `required_paths`
- `source_of_truth`

This should be what the health agent and bootstrap use to determine whether a project remains valid.

### `ontology`

Defines all ontology entrypoints.

Required:

- `schema_path`
- `source_root`
- `pipeline_root`
- `default_pipeline`

This is the section the Python package and SDK should read first when launching hydration.

### `research`

Defines the durable research framing contract.

Required:

- `brief_path`
- `spec_path`

Optional:

- question-generation policy
- direction-change policy

### `planner`

Defines where planner artifacts live and how the lane behaves.

Required:

- `current_plan_path`
- `task_root`
- `approval_root`

Important future fields:

- `require_audit_before_advance`
- `lane_policy`

### `agents`

Defines agent-specific prompt, checklist, and runner policy.

Each role should declare:

- prompt path
- checklist path
- allowed runners

Optional future fields:

- required global skills
- allowed project-local skills
- network policy
- max session budget

### `auditors`

This is new and critical.

Required:

- whether auditing is enabled
- audit order
- whether failure closes the gate

If `fail_closed` is true, autopilot should not advance while any required audit is unresolved.

### `verification`

Defines the required verification gates.

Fields should include:

- deterministic verifier command
- which actions require integrity gate
- whether ontology health is mandatory before research
- whether claims and lineage are required

### `secrets`

Defines project-scoped secrets policy.

The schema should support:

- project-wide secret availability
- per-agent allowlists
- injection-at-session-start only

### `lifecycle`

Defines the legal project phase model and closeout requirements.

This is what turns RAIL from “task runner” into “phase-aware research platform.”

## Validation Rules

The manifest loader should reject:

- missing ontology defaults for ontology-first projects
- missing `task_root` or `approval_root`
- `source_of_truth` values other than `git`
- agent roles without prompt/checklist paths
- lifecycle phases that omit `hydrated` or `ontology_healthy` for ontology-first mode

## How This Differs From The Current State

Current projects often imply these rules across:

- folder structure
- planner prompts
- API defaults
- runtime assumptions

The future schema makes them explicit and portable.

## First Implementation Steps

1. Add `version` and `project` support.
2. Add `ontology.default_pipeline`.
3. Add `repo_contract.required_paths`.
4. Add `planner` roots.
5. Add `verification` and `lifecycle` fields.
6. Add `auditors` once the audit plane exists.
