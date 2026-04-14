# Future API Surface

This document defines the clean, future-oriented API contract for the RAIL platform.
It also lists legacy surfaces that should not be extended and are candidates for eventual removal.

## Principles

- the project slug is the canonical project identifier for frontend and agent callers
- the DB project `_id` is used internally within server-side mutations
- planner flows use the `/projects/{slug}/planner/` prefix
- settings flows use the `/projects/{slug}/settings/` prefix
- runner flows use the `/projects/{slug}/runner/` prefix (future)
- legacy config-based surfaces are frozen — no new features should target them

---

## Future-Oriented API Inventory

### Project Registration

| Method | Path | Purpose |
|--------|------|---------|
| `GET`    | `/api/v1/projects/` | List all registered projects |
| `POST`   | `/api/v1/projects/` | Register a new project |
| `POST`   | `/api/v1/projects/future/bootstrap` | Bootstrap a new Git-native future project |
| `GET`    | `/api/v1/projects/{slug}/context` | Structured context snapshot for agent init |

### Planner Flow

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/projects/{slug}/planner/home` | Full planner home payload (thread, board, tasks, file refs) |
| `GET`  | `/api/v1/projects/{slug}/planner/thread` | Long-lived planner message thread |
| `POST` | `/api/v1/projects/{slug}/planner/messages` | Append a planner message |
| `GET`  | `/api/v1/projects/{slug}/planner/board` | Task board snapshot |
| `POST` | `/api/v1/projects/{slug}/planner/tasks` | Create a planner task |
| `PATCH`| `/api/v1/projects/{slug}/planner/tasks/{task_id}` | Update a planner task |

### Settings

| Method | Path | Purpose |
|--------|------|---------|
| `GET`    | `/api/v1/projects/{slug}/settings/secrets` | List project secrets (masked) and policies |
| `POST`   | `/api/v1/projects/{slug}/settings/secrets` | Upsert a project secret |
| `DELETE` | `/api/v1/projects/{slug}/settings/secrets/{key_name}` | Delete a secret |
| `GET`    | `/api/v1/projects/{slug}/settings/agent-secret-policies` | List agent secret policies |
| `POST`   | `/api/v1/projects/{slug}/settings/agent-secret-policies` | Upsert an agent secret policy |
| `DELETE` | `/api/v1/projects/{slug}/settings/agent-secret-policies/{agent_role}` | Delete a policy |
| `GET`    | `/api/v1/projects/{slug}/secrets/resolve` | Resolve decrypted secrets for a runner at task start |

### Approvals

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/projects/{slug}/approvals` | List approvals for a project |
| `POST` | `/api/v1/projects/{slug}/approvals` | Request a new approval |
| `POST` | `/api/v1/projects/{slug}/approvals/{approval_id}/resolve` | Resolve (grant/reject) an approval |

### Hydration Registry

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/v1/projects/{slug}/hydration/status` | Check hydration artifact freshness |
| `POST` | `/api/v1/projects/{slug}/hydration/artifacts/register` | Register a new hydration artifact |

### Device Heartbeat

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/projects/{slug}/devices/heartbeat` | Record a device heartbeat for the project |

---

## Convex Query/Mutation Surface (Future)

### `projects`

| Export | Type | Purpose |
|--------|------|---------|
| `getBySlug` | query | Canonical project lookup by slug |
| `getById` | query | Internal ID-based lookup |
| `getByGithubRepo` | query | Lookup by `owner/repo` string |
| `list` | query | List all projects |
| `create` | mutation | Register a project |
| `update` | mutation | Update project by slug |
| `updateById` | mutation | Update project by internal ID |
| `remove` | mutation | Delete a project |

### `plannerMessages`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProjectThread` | query | Paginated message history for a thread |
| `append` | mutation | Append a message to the planner thread |

### `taskBoards`

| Export | Type | Purpose |
|--------|------|---------|
| `get` | query | Get a board by ID |
| `listByProject` | query | List boards for a project |
| `getBoardSummary` | query | Board + tasks grouped by status (for markdown rendering) |
| `create` | mutation | Create a task board |
| `update` | mutation | Update board metadata |

### `tasks`

| Export | Type | Purpose |
|--------|------|---------|
| `get` | query | Get a task by ID |
| `listByProject` | query | List tasks for a project |
| `listByBoard` | query | List tasks on a board |
| `create` | mutation | Create a task |
| `update` | mutation | Update task fields (non-status) |
| `transition` | mutation | Atomic status transition + event record + sync signal |

### `taskEvents`

| Export | Type | Purpose |
|--------|------|---------|
| `listByTask` | query | Paginated event history for a task |
| `append` | mutation | Append a raw event |
| `recordVerification` | mutation | Record normalized verification result, auto-blocks on failure |

### `approvals`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProject` | query | List approvals for a project |
| `create` | mutation | Request an approval |
| `resolve` | mutation | Grant or reject an approval |

### `projectSecrets`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProject` | query | List secrets for a project |
| `upsert` | mutation | Create or update a secret |
| `deleteByKey` | mutation | Delete a secret by key name |

### `agentSecretPolicies`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProject` | query | List policies for a project |
| `upsert` | mutation | Create or update a policy |
| `deleteByRole` | mutation | Delete a policy by agent role |

### `runnerEvents`

| Export | Type | Purpose |
|--------|------|---------|
| `listBySession` | query | Event stream for an agent session |
| `append` | mutation | Append a runner event |

### `agentSessions`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProject` | query | List sessions for a project |
| `create` | mutation | Open a new agent session |
| `update` | mutation | Update session metadata |

### `hydrationArtifacts`

| Export | Type | Purpose |
|--------|------|---------|
| `listByProject` | query | List artifacts for a project |
| `register` | mutation | Register a new hydration artifact |
| `markStale` | mutation | Mark an artifact as stale |

### `devices`

| Export | Type | Purpose |
|--------|------|---------|
| `heartbeat` | mutation | Upsert a device record |

---

## Deprecated / Legacy Surface

These modules predate the Git-native future architecture.
They should not receive new features and are candidates for removal after migration.

| Surface | Location | Reason deprecated |
|---------|----------|--------------------|
| `apiConfigs` table + mutations | `convex/configs.ts` | Replaced by Git-native `.ontology/` YAML |
| `ontologyConfigs` table + mutations | `convex/configs.ts` | Replaced by Git-native ontology YAML |
| `pipelineConfigs` table + mutations | `convex/configs.ts` | Replaced by Git-native pipeline YAML |
| `hydrationJobs` table | `convex/jobs.ts` | References legacy `pipelineConfigId`; replaced by `hydrationArtifacts` registry |
| `connectorTemplates` table | `convex/connectors.ts` | V1 connectors are YAML-defined in-repo, not DB-stored templates |
| `ontologyTemplates` table | `convex/ontologyTemplates.ts` | Replaced by in-repo agent YAML + `.ontology/` |
| `workspaces` table (notebook cells) | `convex/workspaces.ts` | Analysis workspace predates future architecture |
| `analysisScripts` table | `convex/analysis.ts` | Replaced by topic scripts in Git |
| `questionSessions` table | `convex/questionSessions.ts` | Ad-hoc Q&A session; not part of planner workflow |
| `ontologySnapshots` table | `convex/quality.ts` | Quality snapshots; superseded by artifact registry |
| `projects.get` query | `convex/projects.ts` | Duplicate of `getBySlug` — use `getBySlug` |
| `projects.forkProject` mutation | `convex/projects.ts` | Forks legacy config objects; Git-native fork is a repo fork |
| `projects.resetStatus` mutation | `convex/projects.ts` | Dev-only utility; not part of production API contract |
| `/api/v1/configs/*` router | `packages/api/app/routers/configs.py` | Manages legacy DB-stored YAML configs |
| `/api/v1/jobs/*` router | `packages/api/app/routers/jobs.py` | Legacy hydration job management |
| `/api/v1/connectors/*` router | `packages/api/app/routers/connectors.py` | Legacy connector template management |
| `/api/v1/analysis/*` router | `packages/api/app/routers/analysis.py` | Legacy analysis script runner |
| `/api/v1/workspaces/*` router | `packages/api/app/routers/workspaces.py` | Legacy notebook workspace |
| `/api/v1/register-artifacts` endpoint | `packages/api/app/routers/projects.py` | Use `/projects/{slug}/hydration/artifacts/register` instead |

---

## Python SDK Surface (`rail-py`)

### Stable (`packages/rail-py/rail/`)

| Module | Purpose |
|--------|---------|
| `manifest.py` | `RailManifest` Pydantic model, `load_manifest()` |
| `project.py` | `Project` class — entry point for SDK users |
| `local.py` | `LocalEngine` — local hydration and query |
| `client.py` | `CloudClient` — HTTP client for cloud mode |
| `bootstrap.py` | `bootstrap_future_project()` — repo scaffolding |
| `planner_sync.py` | `PlannerSync` — Git mirror writes for planner files |
| `verification.py` | Deterministic verification hooks (six layers) |
| `completion_gate.py` | `PlannerCompletionGate`, `RunnerCompletionGate` |

### Deprecated

| Module | Reason |
|--------|--------|
| `rail/agent.py` `AgentClient` | Pre-planner agent chat; superseded by planner flow |
| `packages/api/app/services/planner_service.py` inline markdown renderers | Replaced by `PlannerSync` |
