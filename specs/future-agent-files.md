# Future Agent Files

This document defines the file structure and schema for agent configuration in a future RAIL project.

## Purpose

The `agents/` directory holds the rich role definitions that power the planner and worker agents.

`rail.yaml` stays lightweight and points to this directory. The files in `agents/` contain:

- role metadata
- runner policy
- path permissions
- secret allowlists
- tool policy
- prompt references
- completion and verification requirements

## Directory Layout

Recommended structure:

```text
agents/
  planner.yaml
  research.yaml
  data.yaml
  coding.yaml
  artifact.yaml
  health.yaml
  prompts/
    planner.md
    research.md
    data.md
    coding.md
    artifact.md
    health.md
  checklists/
    planner.md
    research.md
    data.md
    coding.md
    artifact.md
    health.md
```

## Design Rules

- one YAML file per role
- one primary system prompt markdown file per role
- one checklist markdown file per role
- YAML should define policy and references, not embed giant prompt bodies
- all paths should be repository-relative

## Common YAML Schema

Each role file should support this shape:

```yaml
role: data
label: "Data Agent"
purpose: "Create and validate ontology-backed ingestion."

runner:
  default: jules
  approval_required: true
  max_retries: 3
  timeout_minutes: 20

threading:
  mode: task_scoped

permissions:
  read:
    - ".ontology"
    - "topics"
    - "specs"
    - "research_plan"
    - "skills"
  write:
    - ".ontology/sources"
    - ".ontology/pipelines"
    - ".ontology/transforms"
  deny:
    - "agents"

secrets:
  allow:
    - "FRED_API_KEY"

tools:
  allow:
    - "read_repo"
    - "write_repo"
    - "validate_yaml"
    - "run_hydration_dry_run"
  deny:
    - "publish_changes"

prompts:
  system: "agents/prompts/data.md"
  checklist: "agents/checklists/data.md"

completion:
  requires:
    - "yaml_valid"
    - "dry_run_passed"
```

## Required Sections

### `role`

- unique identifier for the role
- should match the file name

### `label`

- human-friendly role label for the frontend

### `purpose`

- short description of the role

### `runner`

Controls execution policy for the role.

Suggested fields:

- `default`
- `approval_required`
- `max_retries`
- `timeout_minutes`
- `read_only`

### `threading`

Controls how the role is scoped in conversation/session terms.

Supported V1 values:

- `project_scoped`
- `task_scoped`

Recommended defaults:

- planner: `project_scoped`
- all workers: `task_scoped`

### `permissions`

Defines repository path policy.

Suggested subfields:

- `read`
- `write`
- `deny`

Rules:

- all writes must land in allowed roots
- denied paths override broader read/write rules
- V1 should reject tasks that require writes outside declared roots

### `secrets`

Defines project secret access.

Suggested subfields:

- `allow`

Rules:

- secret names only
- values come from the database at runtime
- V1 resolves against project secrets only

### `tools`

Defines allowed and denied tool categories.

Suggested subfields:

- `allow`
- `deny`

Examples:

- `read_repo`
- `write_repo`
- `web_research`
- `query_ontology`
- `run_hydration`
- `run_hydration_dry_run`
- `execute_python`
- `render_artifact`
- `publish_changes`

### `prompts`

References markdown files used by the runner/orchestrator.

Suggested subfields:

- `system`
- `checklist`
- `style_guide`

### `completion`

Defines the deterministic requirements that must pass before the role can mark a task complete.

Suggested subfields:

- `requires`
- `artifacts`

## Role-Specific Expectations

### `planner.yaml`

Should include:

- `threading.mode: project_scoped`
- write access to `specs/`, `research_plan/`, and possibly `agents/`
- permission to create DB tasks and approvals
- no direct secret requirements by default

### `research.yaml`

Should include:

- web research enabled
- write access to `topics/`
- citation and note-writing checklist
- read-only access to `.ontology/`

### `data.yaml`

Should include:

- write access to `.ontology/sources`, `.ontology/pipelines`, `.ontology/transforms`
- access to provider secrets
- hydration dry-run and schema validation requirements

### `coding.yaml`

Should include:

- write access to topic scripts and outputs
- access to ontology query and Python execution tools
- explicit limits on output locations

### `artifact.yaml`

Should include:

- write access to `artifacts/`
- rendering and packaging tools
- naming and format checklist

### `health.yaml`

Should include:

- broad read access
- narrow cleanup/delete authority
- skill audit and verification authority
- strict deny rules for unsafe destructive changes outside cleanup scope

## Validation Rules

The agent config validator should enforce:

- role file exists for every declared role
- prompt and checklist files exist
- all configured paths are repo-relative
- denied paths are not also treated as allowed writes
- completion requirements are not empty for write-capable roles

