# Future `rail.yaml`

This document defines the `rail.yaml` project manifest for the future RAIL platform.

## Purpose

`rail.yaml` is the lightweight project manifest at the root of every RAIL repository.

It exists to:

- declare the project identity
- define the top-level repository contract
- tell the hydration kernel where `.ontology/` lives
- tell the frontend how to load project content
- tell the runner layer which default execution policy to use
- point to workspace setup, verification, and archive scripts
- point to richer agent definitions stored under `agents/`

It should not contain full prompts, large embedded specs, or detailed role instructions.

## Design Rules

`rail.yaml` should be:

- lightweight
- human-readable
- easy to diff
- stable across projects
- expressive enough for the frontend and kernel to load a project without guessing

`rail.yaml` should not be:

- a replacement for files under `agents/`
- a storage location for secrets
- a dump of planner state
- a large ontology definition

## Location

`rail.yaml` must live at the repository root.

```text
project-root/
  rail.yaml
```

The database should store only the path to this file, not duplicate its contents heavily.

## Responsibilities

### Kernel Responsibilities

The hydration package should use `rail.yaml` to:

- locate `.ontology/`
- locate the ontology entry file
- locate sources and pipelines directories
- determine default hydration behavior

### Frontend Responsibilities

The dashboard should use `rail.yaml` to:

- understand the project structure
- load the major content roots
- determine which directories should appear in the repo-aware navigation
- find the planner-visible plan area and artifact area

### Runner Responsibilities

The runner layer should use `rail.yaml` to:

- read default runner choice
- read whether sequential execution is required
- read where role definitions live
- enforce the presence of the required project roots
- read workspace isolation mode
- find setup, verification, and archive scripts

## Top-Level Shape

The manifest should use a small number of top-level sections:

- `version`
- `project`
- `paths`
- `hydration`
- `agents`
- `workspaces`
- `frontend`

## Field Specification

### `version`

Purpose:

- manifest schema version

Type:

- integer

Required:

- yes

Example:

```yaml
version: 1
```

### `project`

Purpose:

- basic project identity and Git defaults

Suggested fields:

- `name`
- `slug`
- `default_branch`
- `description`

Required fields:

- `name`
- `slug`
- `default_branch`

Example:

```yaml
project:
  name: "Rutgers Economic Research"
  slug: "rutgers-economic-research"
  default_branch: "main"
  description: "Ontology-driven economic analysis project"
```

### `paths`

Purpose:

- declare the canonical content roots used by the platform

Required fields:

- `ontology_root`
- `topics_root`
- `specs_root`
- `plan_root`
- `agents_root`
- `skills_root`
- `artifacts_root`

Notes:

- these should normally use the standard names
- the manifest allows renaming in case a project needs a variant later
- V1 setup flows should still create the canonical defaults

Example:

```yaml
paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"
```

### `hydration`

Purpose:

- tell the kernel where to load the ontology and hydration inputs from

Required fields:

- `ontology_file`
- `sources_dir`
- `pipelines_dir`

Optional fields:

- `transforms_dir`
- `default_pipeline`
- `hydration_mode`

Notes:

- these paths should resolve relative to the repository root
- the Python package should treat these as the default locations when running hydration jobs

Example:

```yaml
hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"
  transforms_dir: ".ontology/transforms"
  hydration_mode: "full"
```

### `agents`

Purpose:

- define lightweight execution defaults and point to richer role definitions

Required fields:

- `roles_dir`
- `default_runner`
- `sequential_execution`

Optional fields:

- `approval_required_for_write_runs` (legacy shorthand for `autonomy.mode: assisted`)
- `planner_thread_mode`
- `default_planner_role`
- `default_worker_roles`
- `question_relay_mode`

Notes:

- this section should stay lightweight
- role prompts, role policies, path allowlists, and runner-specific options belong in files under `agents/`

Example:

```yaml
agents:
  roles_dir: "agents"
  default_runner: "jules"
  sequential_execution: true
  planner_thread_mode: "project"
  default_planner_role: "planner"
  question_relay_mode: "planner_first"
```

### `autonomy`

Purpose:

- define how much work the planner and workers may do without human approval
- define escalation boundaries for fire-and-forget research runs

Required fields:

- none in V1

Optional fields:

- `mode`
- `require_human_for`
- `allow_without_human`
- `max_runtime_minutes`
- `max_cost_usd`
- `max_retries_per_task`

Notes:

- `mode` should be one of `assisted`, `supervised_autopilot`, or `autopilot`
- if omitted, V1 should default to `assisted`
- `approval_required_for_write_runs: true` maps to `mode: assisted` for compatibility
- autonomy policy never overrides role path allowlists, secret allowlists, or integrity gates

Example:

```yaml
autonomy:
  mode: "supervised_autopilot"
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
```

### `integrity`

Purpose:

- define the evidence and reproducibility requirements for trusted outputs

Required fields:

- none in V1

Optional fields:

- `allow_synthetic_data`
- `require_source_for_datasets`
- `require_lineage_for_final_artifacts`
- `require_evidence_for_report_claims`
- `stale_outputs_block_promotion`

Example:

```yaml
integrity:
  allow_synthetic_data: false
  require_source_for_datasets: true
  require_lineage_for_final_artifacts: true
  require_evidence_for_report_claims: true
  stale_outputs_block_promotion: true
```

### `workspaces`

Purpose:

- define how write-capable worker sessions prepare, test, review, and clean up isolated workspaces

Required fields:

- none in V1

Optional fields:

- `mode`
- `root`
- `setup_script`
- `verification_script`
- `archive_script`
- `nonconcurrent_run`
- `checkpoint_mode`

Notes:

- this section is inspired by Conductor's workspace and script model
- scripts should run from the worker workspace root
- script bodies should live in files when they become more than a short command
- secrets must be injected by the runtime, not stored in `rail.yaml`
- V1 may run one worker at a time while still using isolated workspace metadata

Example:

```yaml
workspaces:
  mode: "isolated"
  root: ".rail/workspaces"
  setup_script: "scripts/setup-workspace.sh"
  verification_script: "scripts/run-verification.sh"
  archive_script: "scripts/archive-workspace.sh"
  nonconcurrent_run: true
  checkpoint_mode: "git-ref"
```

### `frontend`

Purpose:

- define how the dashboard should interpret and render repository-backed content

Required fields:

- `topic_index_mode`
- `artifact_index_mode`

Optional fields:

- `show_repo_tree`
- `show_task_board_snapshot`
- `default_home_view`
- `git_render_mode`

Notes:

- this section should not become a full UI theme system
- it is meant to guide loading and display behavior, not style every component

Example:

```yaml
frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
  show_repo_tree: true
  show_task_board_snapshot: true
  default_home_view: "planner"
  git_render_mode: "default_branch"
```

## Full Example

```yaml
version: 1

project:
  name: "Economic Analysis Platform"
  slug: "economic-analysis-platform"
  default_branch: "main"
  description: "Git-native ontology and agent workflow project"

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
  transforms_dir: ".ontology/transforms"
  hydration_mode: "full"

agents:
  roles_dir: "agents"
  default_runner: "jules"
  sequential_execution: true
  planner_thread_mode: "project"
  default_planner_role: "planner"
  question_relay_mode: "planner_first"

autonomy:
  mode: "assisted"
  require_human_for:
    - publish_changes
    - destructive_delete
    - missing_source_data
    - low_confidence_claims
    - methodology_change_with_material_effect
  allow_without_human:
    - plan_decomposition
    - source_discovery
    - verification
    - assumption_recording

integrity:
  allow_synthetic_data: false
  require_source_for_datasets: true
  require_lineage_for_final_artifacts: true
  require_evidence_for_report_claims: true
  stale_outputs_block_promotion: true

frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
  show_repo_tree: true
  show_task_board_snapshot: true
  default_home_view: "planner"
  git_render_mode: "default_branch"
```

## What Lives Outside `rail.yaml`

These should live elsewhere:

- full planner prompt
- worker prompts
- per-role path allowlists
- per-role secret allowlists
- skill content
- task board data
- planner message history
- full ontology schema

Recommended homes:

- `agents/` for prompts, role configs, allowlists, and runner-specific policy
- `skills/` for project-local skills
- `research_plan/` for planner-authored plans and board snapshots
- `.ontology/` for ontology and hydration inputs

## Validation Rules

The manifest validator should enforce:

- all required top-level sections exist
- all required paths are present
- all configured paths are relative repository paths
- `default_runner` is a supported runner identifier
- `sequential_execution` is `true` in V1
- `autonomy.mode` is one of `assisted`, `supervised_autopilot`, or `autopilot` when present
- `approval_required_for_write_runs`, if present, is treated as a legacy compatibility flag
- integrity policy values are booleans when present
- hydration paths point inside `.ontology/` unless an explicit future exception is allowed

## V1 Constraints

For V1, the platform should assume:

- a single active worker at a time
- a long-lived project-level planner thread
- planner-first question relay
- autonomy defaults to `assisted`
- supervised autopilot and autopilot may run routine write-capable research tasks without approval if role policies, budgets, and integrity gates allow it
- both organization and project secret scopes with per-role allowlists
- Jules as the first supported runner

The manifest should reflect these defaults without hardcoding every future platform option.
