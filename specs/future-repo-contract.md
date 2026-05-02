# Future Repo Contract

This document defines the canonical Git repository structure for a RAIL project.

The contract is strict at the top level and flexible within topic workspaces.

This is intentional:

- top-level predictability gives the planner, frontend, and Python package a stable contract
- topic-level flexibility allows agents to build their own knowledge, script, and output graph inside a project

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
    state/
  agents/
  skills/
  artifacts/
  scripts/
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

They may also create topic-local conventions when useful, as long as those conventions remain inside the topic subtree and do not replace the required top-level contract.

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
- session summaries
- workspace review notes
- merge/adoption blockers
- assumption and decision ledgers
- source provenance records
- claim-to-evidence mappings
- artifact lineage and stale-output records

Recommended structure:

```text
research_plan/
  current_plan.md
  task_board.md
  assumptions.md
  decisions.md
  methodology.md
  provenance.md
  claim_evidence.md
  open_questions.md
  rerun_options.md
  verification_summary.md
  tasks/
  sessions/
  state/
    assumptions.json
    sources.json
    claims.json
    artifact_lineage.json
    verification_runs.json
```

Markdown files are the durable human/planner-readable research record.
JSON files under `research_plan/state/` are machine-readable indexes for the UI, rerun planner, and verification tools.
The JSON indexes may be rebuilt from Markdown/session/artifact metadata when possible, but the platform should keep them current during normal operation.

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

### `scripts/`

Optional but recommended. Stores repo-defined automation scripts used by planner and runner workspaces.

Recommended examples:

- `scripts/setup-workspace.sh`
- `scripts/run-verification.sh`
- `scripts/archive-workspace.sh`

These scripts are inspired by Conductor's setup/run/archive script model. They should be committed to Git when shared across the project. Local secrets and `.env` files must remain outside Git and be injected through the runtime secret policy.

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
  scripts_root: "scripts"

hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"

agents:
  default_runner: "jules"
  sequential_execution: true
  role_manifest_mode: "lightweight"
  roles_dir: "agents"

autonomy:
  mode: "assisted" # assisted | supervised_autopilot | autopilot
  require_human_for:
    - publish_changes
    - destructive_delete
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

integrity:
  allow_synthetic_data: false
  require_source_for_datasets: true
  require_lineage_for_final_artifacts: true
  require_evidence_for_report_claims: true
  stale_outputs_block_promotion: true

workspaces:
  mode: "isolated"
  setup_script: "scripts/setup-workspace.sh"
  verification_script: "scripts/run-verification.sh"
  archive_script: "scripts/archive-workspace.sh"

frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
```

## Frontend Loading Rules

The dashboard should load project content from the repo using this contract:

- read `rail.yaml` first
- read `.ontology/` for ontology metadata and hydration inputs
- read `research_plan/` for current plans and planner outputs
- read `research_plan/state/` for assumptions, sources, claims, artifact lineage, and verification indexes
- read `topics/` for topic trees, notes, scripts, and outputs
- read `artifacts/` for final user-facing deliverables
- read `skills/` and `agents/` for project capabilities and configuration views
- read workspace review files and session summaries under `research_plan/`

In hosted mode, this should resolve against the latest commit on the configured default branch.

## Allowed Role Write Surfaces

### Planner

May write to:

- `specs/`
- `research_plan/`
- `agents/`

May create tasks in `research_plan/tasks/`.
May write workspace review, assumption, decision, provenance, claim-evidence, rerun, and merge/adoption notes under `research_plan/`.

### Research Agent

May write to:

- `topics/`
- `artifacts/notes/` if defined
- source notes and provenance drafts under assigned topic paths

### Data Agent

May write to:

- `.ontology/sources/`
- `.ontology/pipelines/`
- `.ontology/transforms/`
- `topics/*/data-notes/`
- dataset provenance entries through the planner/session review flow

### Coding Agent

May write to:

- `topics/*/scripts/`
- `topics/*/outputs/`
- `artifacts/`
- artifact lineage drafts for outputs it creates

### Artifact Agent

May write to:

- `artifacts/`
- topic-local presentation subfolders when needed
- artifact metadata and claim-evidence drafts for generated deliverables

### Health Agent

May modify:

- generated temp files
- task metadata in `research_plan/tasks/`
- blocker and health reports in `research_plan/`
- verification summaries and stale-output markers under `research_plan/`

## Workspace Review Files

Each write-capable worker session should have a durable review surface.

Recommended path:

```text
research_plan/sessions/<role>/<session-id>/
  session.ndjson
  commands.ndjson
  state.json
  summary.md
  diff.md
  todos.md
  verification.md
  assumptions.md
  provenance.md
  claim_evidence.md
  artifact_lineage.json
```

The machine protocol is still NDJSON and JSON. Markdown files are the human/planner-readable review layer.

Worker outputs should include enough integrity metadata for the planner and health agent to decide whether changes can be promoted:

- assumptions introduced or changed
- source records used or created
- datasets generated and their upstream source lineage
- artifacts generated and their input/script/source/assumption lineage
- important claims and their evidence references
- verification commands run and results
- unresolved questions or blockers

## Worktree And Branch Policy

RAIL should prefer isolated Git workspaces for worker runs:

- one workspace per active worker session
- one task branch per write-capable run
- no worker writes directly to the canonical default branch
- autonomy policy approval required before merge, PR creation, publishing, or copying workspace changes into the canonical branch
- archive/cleanup after durable summaries and review files are written

V1 may enforce one active worker at a time, but the repo contract should not prevent future parallel branches/worktrees.
- project-local skills under review

The health agent should not silently delete user-authored source material outside approved cleanup paths.
It should prefer proposing cleanup and requiring approval for any destructive action outside ephemeral generated files.
