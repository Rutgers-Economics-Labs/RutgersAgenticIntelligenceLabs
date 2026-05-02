# Future Runners

This document defines how RAIL connects to external agent execution systems.

## Runner Strategy

V1 is Jules-first.

Reasons:

- Jules exposes an official API
- it is designed for GitHub repository tasks
- it aligns with the sequential managed-worker model
- it provides a cleaner first implementation target than assuming a generic Claude Code cloud REST surface

Claude Code should remain a planned second runner with a separate adapter.
The planner-facing orchestration model must not depend on Jules-specific event names or concepts.

Conductor is useful as a reference implementation for the local-agent side of the system. The lessons to keep are:

- agent runs should happen in isolated Git workspaces/branches
- setup, run/test, and archive scripts make workspaces repeatable
- local CLI agents can reuse auth already present on the machine
- diff review and merge/adoption should be explicit
- todos and failed checks should block merge/adoption
- checkpoints should capture turn-level changes before destructive rollback is needed

## Runner Abstraction

The platform should define an internal runner interface:

- `create_session(task_payload)`
- `get_session(session_id)`
- `list_events(session_id)`
- `send_message(session_id, message)`
- `approve(session_id, payload)`
- `cancel(session_id)`

The planner and DB should depend on this abstraction rather than on a specific vendor.

The runner layer should also expose workspace lifecycle hooks:

- `prepare_workspace(task_payload)`
- `run_setup(workspace)`
- `run_verification(workspace)`
- `summarize_diff(workspace)`
- `collect_integrity_metadata(workspace)`
- `archive_workspace(workspace)`

These hooks may be no-ops for hosted runners at first, but the planner contract should include them so local runners and future parallel workers do not require a new architecture.
Integrity metadata collection should gather assumptions, provenance, claim evidence, artifact lineage, verification results, and stale-output markers produced during the run.

## Jules Runner

### Responsibilities

- create a managed coding session against a GitHub repo and branch
- send a bounded task prompt
- observe session progress
- surface questions and approval requests back to the planner
- approve plans after human confirmation

### Authentication

The runner should use the Jules API with project or organization scoped credentials stored in the database and injected through the runner layer.

Secrets should be allowlisted per agent role.

### Expected Flow

1. Planner creates a task
2. Runtime checks autonomy policy and requests human approval only when required
3. Runner creates a Jules session
4. Planner sends a task payload
5. Jules returns plan/progress/events
6. If a plan approval is requested, the platform pauses for human confirmation
7. If Jules asks a question, it is relayed to the planner
8. The planner answers directly when possible or relays the question to the human when necessary
9. On completion, the planner records session metadata and triggers verification

### Task Payload Shape

Suggested fields:

```json
{
  "project_slug": "example-project",
  "role": "data",
  "task_id": "task_123",
  "repo_url": "https://github.com/org/repo",
  "branch": "main",
  "allowed_paths": [
    ".ontology/sources",
    ".ontology/pipelines"
  ],
  "allowed_secrets": [
    "FRED_API_KEY",
    "WORLD_BANK_API_KEY"
  ],
  "task_description": "Add and validate a new data source for county labor indicators.",
  "acceptance_criteria": [
    "YAML validates",
    "Hydration dry run succeeds",
    "Notes written to topics/labor-market/data-notes"
  ]
}
```

## Claude Code Runner

Claude Code should be modeled as a local CLI/workspace adapter first, not as an assumed cloud API.

Current design assumptions:

- use the installed Claude Code CLI and the user's local auth where appropriate
- allow environment overrides through scoped runner settings
- do not assume a public REST API equivalent to Jules until confirmed
- support a transport based on CLI, terminal supervision, file-backed commands, or MCP
- run in an isolated workspace/branch rather than directly in the canonical project root

This runner should use the same internal abstraction as Jules.
The first Claude Code integration should be treated as a future managed adapter rather than assumed REST parity with Jules.

## Codex And Local CLI Runners

Codex and other terminal agents should follow the same local workspace pattern:

- create or attach to a workspace
- run setup scripts
- launch the CLI with a bounded prompt
- stream output into `session.ndjson`
- accept planner/human commands through `commands.ndjson`
- run verification scripts
- summarize diffs and blockers before merge/adoption

Local CLI runners may be less interactive than hosted APIs. Their capability metadata should tell the planner whether they support:

- live message injection
- approval callbacks
- cancellation
- event streaming
- structured tool call extraction
- checkpoint creation
- structured completion summaries
- artifact lineage and integrity metadata emission

## Runner Event Model

All runner backends should normalize events into a common shape:

- `session_created`
- `workspace_created`
- `setup_started`
- `setup_completed`
- `plan_proposed`
- `approval_requested`
- `question_asked`
- `progress`
- `file_change_detected`
- `verification_started`
- `verification_completed`
- `integrity_metadata_collected`
- `artifact_marked_stale`
- `artifact_promoted`
- `diff_ready`
- `merge_blocked`
- `completed`
- `failed`
- `cancelled`
- `waiting_for_planner`
- `waiting_for_human`

The planner consumes these normalized events and updates task state.

## Workspace Scripts

Each project may define scripts for worker workspaces:

- setup script: runs when a workspace is created
- run script: runs tests, dev servers, or verification commands
- archive script: cleans up temporary resources when a workspace is archived

Script requirements:

- scripts run from the workspace root
- scripts receive environment variables for project root, workspace root, branch, task id, role, and allocated ports when relevant
- scripts must not write secrets into Git-tracked files
- nonconcurrent mode should be supported for resources that cannot run in parallel

V1 may store these scripts in `rail.yaml` or `agents/*.yaml`, but the command bodies should remain editable repo files when they become long.

## Diff Review And Merge

Runner completion does not mean changes are adopted.

After a worker finishes:

1. collect changed files
2. run deterministic verification
3. collect assumptions, provenance, claim evidence, and artifact lineage
4. render a diff summary
5. list unresolved todos/blockers, including missing evidence and stale outputs
6. apply autonomy policy before merge, PR creation, publishing, or copying changes into the canonical branch

The planner should never silently merge or publish worker changes unless the project autonomy policy explicitly permits the action.
Even in autopilot mode, outputs should not be promoted to trusted artifacts unless required integrity gates pass.

## Worker Completion Summary

Every runner should produce or normalize a compact completion summary so the planner does not need to infer outcomes from raw logs.

Suggested shape:

```json
{
  "status": "completed",
  "assumptions_added": [],
  "assumptions_changed": [],
  "sources_used": [],
  "datasets_created": [],
  "artifacts_created": [],
  "claims_created": [],
  "verification_results": [],
  "open_questions": [],
  "blockers": [],
  "recommended_next_tasks": []
}
```

If a worker cannot complete without inventing data, fabricating citations, or making unsupported claims, the normalized status should be `blocked` or `failed` with a clear reason.

## Checkpoints

Before each approved worker turn, the runtime should create a lightweight checkpoint.

Acceptable implementations:

- private Git ref
- temporary branch
- patch file
- workspace snapshot metadata

Checkpoints are not a replacement for Git history. They are a safety rail for undoing a single agent turn or explaining what changed between turns.

## Secrets Injection

Secrets are stored in the database and resolved at runtime.

Rules:

- both organization and project scope are supported
- project secrets override organization secrets
- every agent role has an explicit allowlist
- secret values are never written into the repository
- secret injection should be session-scoped and least-privilege
- local runners may reuse existing local auth, but the planner must still record which secret policy or auth mode was used

## Human-in-the-Loop

Write-capable runs follow the project autonomy policy.
In assisted mode, runs should stop before execution until a human approves:

- task start
- plan approval when required by the runner
- publish/merge action when applicable

Read-only validation runs may proceed without approval.
In supervised autopilot or autopilot mode, routine write-capable work may proceed without approval if it stays within role allowlists, budget limits, and integrity policy.

## V1 Operating Constraints

- one active worker session at a time per project
- planner remains the single human-facing role
- runner adapters may emit vendor-specific raw events, but the app should operate on normalized events
- publishing or merging agent changes is separate from starting a run and follows autonomy policy
- even with one active worker, model each write-capable run as a workspace so parallel worktrees can be added later
