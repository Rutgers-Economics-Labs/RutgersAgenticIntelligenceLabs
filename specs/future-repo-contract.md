# Future Repo Contract

This document defines the canonical Git repository structure for a RAIL project.

The contract is strict at the top level and flexible within topic workspaces.

## Top-Level Structure

```text
project-root/
  .ontology/
    ontology.yaml
    sources/
    pipelines/
    transforms/
  topics/
  specs/
  research_plan/
  agents/
  skills/
  artifacts/
  rail.yaml
  README.md
```

## Required Paths

### `.ontology/`

Required. This directory is owned by the hydration kernel and Python package.

Expected contents:

- `ontology.yaml`
- `sources/*.yaml`
- `pipelines/*.yaml`
- optional `transforms/`

The Python package should load hydration jobs from `.ontology/`.

### `topics/`

Required. This is the flexible project knowledge workspace.

The planner and worker agents may create nested folders under `topics/` to organize:

- literature review
- source notes
- downloaded documents
- breakdowns and memos
- scripts
- analysis outputs
- intermediate datasets
- visualizations

The platform must allow freedom inside each topic subtree as long as generated files remain inside `topics/` or `artifacts/`.

Recommended example:

```text
topics/
  labor-market/
    overview.md
    county-comparison/
      breakdown.md
      notes/
      scripts/
      outputs/
```

### `specs/`

Required. Stores durable project and execution specifications.

Examples:

- architecture specs
- ontology design specs
- feature specs
- approval snapshots

The planner may update specs directly when a new plan is approved.

### `research_plan/`

Required. Stores live planning artifacts produced by the planner.

Examples:

- current execution plan
- task decomposition
- kanban or task board snapshots
- blockers
- approval notes
- sequencing documents

### `agents/`

Required. Stores agent definitions and runner-facing metadata.

Expected examples:

- role configs
- prompts
- policies
- path allowlists

### `skills/`

Required. Stores project-specific reusable skills.

The project is initialized with a baseline set of global starter skills copied into this directory.

Agents may create or refine skills here, but newly created skills should remain project-scoped unless explicitly promoted through review.

### `artifacts/`

Required. Stores user-facing final outputs and renderable deliverables.

Examples:

- reports
- PDFs
- dashboard JSON
- exported charts
- presentation-ready summaries

## `rail.yaml`

Required. This is the project manifest.

It defines the repository contract, runtime defaults, and dashboard behavior.
`rail.yaml` should remain lightweight. Full prompts, rich role definitions, path allowlists, and runner-facing role configs should live under `agents/`.

Draft shape:

```yaml
version: 1

project:
  name: "Example Project"
  slug: "example-project"
  default_branch: "main"

paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"

hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"

agents:
  approval_required_for_write_runs: true
  default_runner: "jules"
  sequential_execution: true
  role_manifest_mode: "lightweight"
  roles_dir: "agents"

frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
```

## Frontend Loading Rules

The dashboard should load project content from the repo using this contract:

- read `rail.yaml` first
- read `.ontology/` for ontology metadata and hydration inputs
- read `research_plan/` for current plans and planner outputs
- read `topics/` for topic trees, notes, scripts, and outputs
- read `artifacts/` for final user-facing deliverables
- read `skills/` and `agents/` for project capabilities and configuration views

## Allowed Role Write Surfaces

### Planner

May write to:

- `specs/`
- `research_plan/`
- `agents/`

May create tasks in the database.
Should also mirror planner-visible task snapshots into `research_plan/`.

### Research Agent

May write to:

- `topics/`
- `artifacts/notes/` if defined

### Data Agent

May write to:

- `.ontology/sources/`
- `.ontology/pipelines/`
- `.ontology/transforms/`
- `topics/*/data-notes/`

### Coding Agent

May write to:

- `topics/*/scripts/`
- `topics/*/outputs/`
- `artifacts/`

### Artifact Agent

May write to:

- `artifacts/`
- topic-local presentation subfolders when needed

### Health Agent

May modify:

- generated temp files
- task metadata in DB
- project-local skills under review

The health agent should not silently delete user-authored source material outside approved cleanup paths.
