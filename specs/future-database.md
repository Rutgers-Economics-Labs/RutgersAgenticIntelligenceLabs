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

## Scope Rules

The database should stay lightweight.

It should not store:

- full ontology payloads
- hydrated graph data
- raw report bodies as primary storage
- large artifacts as primary storage
- long-lived duplicated copies of repo files

It may store compact indexes and metadata for those things when needed for UX.

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

- deferred until after V1
- shared secret scope for future multi-project or multi-user deployments

Status:

- not required in V1
- should not block the initial implementation

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

- V1 policies should resolve only against `project_secrets`
- a later version may extend these policies with organization defaults

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
- `granted_by_user_id`
- `requested_at`
- `resolved_at`

Approval examples:

- `run_task`
- `approve_runner_plan`
- `publish_changes`
- `promote_skill`

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
- `commit_sha`
- `created_at`

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

### Agent Session Status

- `queued`
- `running`
- `awaiting_input`
- `awaiting_approval`
- `completed`
- `failed`
- `cancelled`

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

The DB remains authoritative for real-time execution state, but the mirrored files give users and future agents durable context.

## Open Design Questions

These items should be finalized next:

1. whether `projects` also needs an explicit owner or workspace identifier in V1
2. whether `tasks.depends_on_task_ids` should stay inline or move to a dedicated dependency table
3. whether planner message summaries should be snapshotted into Git on a schedule or only when plans change
