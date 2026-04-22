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

## Runner Abstraction

The platform should define an internal runner interface:

- `create_session(task_payload)`
- `get_session(session_id)`
- `list_events(session_id)`
- `send_message(session_id, message)`
- `approve(session_id, payload)`
- `cancel(session_id)`

The planner and DB should depend on this abstraction rather than on a specific vendor.

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
2. User approves execution
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

Claude Code should be modeled as a future adapter.

Current design assumptions:

- use Anthropic-supported remote or cloud workflows where available
- do not assume a public REST API equivalent to Jules until confirmed
- support a transport based on CLI, remote session orchestration, or MCP

This runner should use the same internal abstraction as Jules.
The first Claude Code integration should be treated as a future managed adapter rather than assumed REST parity with Jules.

## Runner Event Model

All runner backends should normalize events into a common shape:

- `session_created`
- `plan_proposed`
- `approval_requested`
- `question_asked`
- `progress`
- `file_change_detected`
- `completed`
- `failed`
- `cancelled`
- `waiting_for_planner`
- `waiting_for_human`

The planner consumes these normalized events and updates task state.

## Secrets Injection

Secrets are stored in the database and resolved at runtime.

Rules:

- both organization and project scope are supported
- project secrets override organization secrets
- every agent role has an explicit allowlist
- secret values are never written into the repository
- secret injection should be session-scoped and least-privilege

## Human-in-the-Loop

Write-capable runs must stop before execution until a human approves:

- task start
- plan approval when required by the runner
- publish/merge action when applicable

Read-only validation runs may proceed without approval.

## V1 Operating Constraints

- one active worker session at a time per project
- planner remains the single human-facing role
- runner adapters may emit vendor-specific raw events, but the app should operate on normalized events
- publishing or merging agent changes is a separate approval checkpoint from starting a run
