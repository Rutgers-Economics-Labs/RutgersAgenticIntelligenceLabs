# Future Database

This document defines the operational database contract for the future RAIL platform.

## Database Philosophy

The database is not the source of truth for project content.

Git remains the source of truth for:

- ontology YAML
- plans and specs
- research notes
- scripts
- artifacts
- project-local skills

The database stores operational state that Git should not own directly:

- project registration metadata
- secrets
- task sequencing and status
- runner sessions and events
- approvals
- cost and timing metadata
- autonomy policy status and budget tracking
- compact indexes for assumptions, sources, claims, artifact lineage, and verification status

The database should stay intentionally thin.
Its purpose is to help the planner operate the system, not to duplicate the repository.

## Scope Rules

The database should stay lightweight.

It should not store:

- full ontology payloads
- hydrated graph data
- raw report bodies as primary storage
- large artifacts as primary storage
- long-lived duplicated copies of repo files

It may store compact indexes and metadata for those things when needed for UX.
Integrity indexes in the database are caches and query accelerators.
The durable research record should remain in Git under `research_plan/` and `artifacts/`.

## Core Tables

### `projects`

Purpose:

- register a project with the platform
- connect the platform to the Git repository
- hold lightweight operational project settings

Suggested fields:

- `id`
- `slug`
- `name`
- `description`
- `git_repo_url`
- `default_branch`
- `manifest_path`
- `status`
- `created_at`
- `updated_at`

Notes:

- `manifest_path` should usually be `rail.yaml`
- project structure details should be read from the manifest, not duplicated heavily in DB
- the Git repo URL and default branch are the main durable project pointers stored by the platform
- the UI should render from the latest commit on `default_branch`

### `project_secrets`

Purpose:

- store encrypted project-scoped secrets

Suggested fields:

- `id`
- `project_id`
- `key_name`
- `encrypted_value`
- `created_at`
- `updated_at`

### `organization_secrets`

Purpose:

- store encrypted organization-scoped secrets
- provide reusable defaults for multiple projects

Notes:

- V1 may implement organization scope in a minimal form
- project secrets override organization secrets with the same key
- runners resolve secrets through policy, not by exposing every available secret

### `agent_secret_policies`

Purpose:

- define which secrets each role may receive

Suggested fields:

- `id`
- `project_id`
- `agent_role`
- `allowed_secret_names`
- `created_at`
- `updated_at`

Notes:

- V1 policies should resolve against both `organization_secrets` and `project_secrets`
- project values override organization values when names overlap
- policies should be enforced per role before a runner session starts

### `task_boards`

Purpose:

- group the planner-owned task state for a project or session

Suggested fields:

- `id`
- `project_id`
- `session_id`
- `title`
- `status`
- `created_at`
- `updated_at`

### `tasks`

Purpose:

- hold the operational execution queue created by the planner

Suggested fields:

- `id`
- `board_id`
- `project_id`
- `session_id`
- `title`
- `description`
- `status`
- `priority`
- `agent_role`
- `runner`
- `repo_paths`
- `acceptance_criteria`
- `depends_on_task_ids`
- `approval_state`
- `git_snapshot_path`
- `assumptions_touched`
- `sources_touched`
- `artifacts_touched`
- `verification_status`
- `promotion_state`
- `created_at`
- `updated_at`

Notes:

- `git_snapshot_path` points to the mirrored planner view in `research_plan/`

### `task_events`

Purpose:

- record the event timeline for each task

Suggested fields:

- `id`
- `task_id`
- `event_type`
- `payload`
- `created_at`

Event examples:

- `created`
- `moved_to_ready`
- `approval_requested`
- `approval_granted`
- `runner_started`
- `question_asked`
- `blocked`
- `verification_passed`
- `done`

### `agent_sessions`

Purpose:

- store operational metadata about planner and worker sessions

Suggested fields:

- `id`
- `project_id`
- `task_id`
- `role`
- `runner`
- `external_session_id`
- `status`
- `estimated_cost_usd`
- `actual_cost_usd`
- `question_count`
- `started_at`
- `ended_at`
- `created_at`
- `updated_at`

Notes:

- message content that becomes durable project knowledge should be written into Git rather than relied on only in session storage

### `runner_events`

Purpose:

- normalize vendor-specific runner events into a common event stream
- preserve both normalized and raw payloads for debugging

Suggested fields:

- `id`
- `agent_session_id`
- `event_type`
- `normalized_payload`
- `raw_payload`
- `debug_visibility`
- `created_at`

Event examples:

- `session_created`
- `plan_proposed`
- `approval_requested`
- `question_asked`
- `progress`
- `completed`
- `failed`
- `waiting_for_planner`
- `waiting_for_human`

Notes:

- `raw_payload` should be treated as internal or debug-only surface data
- the main application should prefer `normalized_payload`

### `approvals`

Purpose:

- track human approval checkpoints

Suggested fields:

- `id`
- `project_id`
- `task_id`
- `agent_session_id`
- `approval_type`
- `status`
- `requested_by_role`
- `resolved_by_role`
- `granted_by_user_id`
- `requested_at`
- `resolved_at`
- `resolution_note`

Approval examples:

- `run_task`
- `approve_runner_plan`
- `publish_changes`
- `promote_skill`

## Design Constraints

- the DB must be sufficient to resume operational state after process restart
- the DB must remain small enough to inspect and reason about directly
- a project must still be understandable from Git even if the DB is unavailable
- secret values must never be mirrored into Git snapshots
- the database must never become the only place where planner intent or worker outputs exist

### `planner_messages`

Purpose:

- store the planner chat and user interaction history needed for the dashboard
- support a long-lived planner thread at the project level

Suggested fields:

- `id`
- `project_id`
- `session_id`
- `thread_id`
- `role`
- `content`
- `message_type`
- `created_at`

Notes:

- this is operational UX state, not the durable home for finalized plans
- the long-lived planner thread should be scoped to the project and remain available across sequential worker runs

### `artifact_index`

Purpose:

- provide lightweight metadata so the UI can quickly show artifacts without making the DB the storage layer

Suggested fields:

- `id`
- `project_id`
- `path`
- `artifact_type`
- `title`
- `promotion_state`
- `verification_status`
- `lineage_path`
- `commit_sha`
- `created_at`

### `autonomy_policies`

Purpose:

- cache the effective autonomy policy for a project
- support fast UI display of mode, budgets, and escalation boundaries

Suggested fields:

- `id`
- `project_id`
- `mode`
- `require_human_for`
- `allow_without_human`
- `max_runtime_minutes`
- `max_cost_usd`
- `max_retries_per_task`
- `source_manifest_path`
- `created_at`
- `updated_at`

Notes:

- `source_manifest_path` usually points to `rail.yaml`
- the repo manifest remains the durable source of truth
- this table may cache the last valid effective policy used by the runtime

### `assumption_index`

Purpose:

- provide fast UI access to assumptions and affected outputs

Suggested fields:

- `id`
- `project_id`
- `assumption_key`
- `title`
- `value`
- `status`
- `source_path`
- `affected_paths`
- `created_at`
- `updated_at`

Notes:

- `source_path` points to `research_plan/state/assumptions.json` or a Markdown ledger section
- assumption edits should mark dependent outputs stale until rerun or revalidated

### `source_index`

Purpose:

- provide fast UI access to source provenance records

Suggested fields:

- `id`
- `project_id`
- `source_key`
- `source_type`
- `title`
- `url_or_path`
- `retrieved_at`
- `license`
- `quality_status`
- `source_path`
- `created_at`
- `updated_at`

### `claim_index`

Purpose:

- provide fast UI access to report/dashboard claims and their evidence

Suggested fields:

- `id`
- `project_id`
- `claim_key`
- `claim_text`
- `artifact_path`
- `evidence_paths`
- `status`
- `confidence`
- `source_path`
- `created_at`
- `updated_at`

Notes:

- claims without evidence should prevent final artifact promotion

### `artifact_lineage_index`

Purpose:

- support artifact dependency graphs and stale-output detection

Suggested fields:

- `id`
- `project_id`
- `artifact_path`
- `promotion_state`
- `input_paths`
- `script_paths`
- `source_keys`
- `assumption_keys`
- `claim_keys`
- `verification_run_ids`
- `lineage_path`
- `created_at`
- `updated_at`

### `verification_runs`

Purpose:

- record compact verification outcomes for UI and policy checks

Suggested fields:

- `id`
- `project_id`
- `task_id`
- `agent_session_id`
- `status`
- `checks`
- `artifact_paths`
- `blockers`
- `source_path`
- `created_at`
- `updated_at`

Notes:

- detailed verification reports should still live in Git
- failed verification should create blockers and prevent artifact promotion unless policy explicitly allows partial verification

### `repo_sync_events`

Purpose:

- track sync activity between the platform and Git provider

Suggested fields:

- `id`
- `project_id`
- `direction`
- `commit_sha`
- `status`
- `summary`
- `created_at`

## Recommended Status Enums

### Task Status

- `backlog`
- `ready`
- `awaiting_approval`
- `running`
- `blocked`
- `review`
- `done`
- `cancelled`
- `stale`

### Agent Session Status

- `queued`
- `running`
- `awaiting_input`
- `awaiting_approval`
- `completed`
- `failed`
- `cancelled`

### Artifact Promotion State

- `exploratory`
- `draft`
- `needs_evidence`
- `partially_verified`
- `verified`
- `stale`
- `blocked`

### Verification Status

- `not_run`
- `running`
- `passed`
- `failed`
- `partial`
- `stale`

### Approval Status

- `pending`
- `approved`
- `rejected`
- `expired`

## Git Mirror Rules

The planner should mirror operational task state into Git for visibility.

Suggested mirrored files:

- `research_plan/current_plan.md`
- `research_plan/task_board.md`
- `research_plan/tasks/<task-slug>.md`
- `research_plan/assumptions.md`
- `research_plan/provenance.md`
- `research_plan/claim_evidence.md`
- `research_plan/verification_summary.md`
- `research_plan/state/*.json`

The DB remains authoritative for real-time execution state, but the mirrored files give users and future agents durable context.

## Open Design Questions

These items should be finalized next:

1. whether `projects` also needs an explicit owner or workspace identifier in V1
2. whether `tasks.depends_on_task_ids` should stay inline or move to a dedicated dependency table
3. whether planner message summaries should be snapshotted into Git on a schedule or only when plans change
