# Project Setup Agent

The **project setup agent** is a conversational assistant that helps researchers configure, manage, and debug their RAIL projects. It is distinct from the research agent (`specs/agents.md`): the setup agent operates on project structure and configuration, while the research agent runs research workflows against already-hydrated data.

---

## Purpose

When a researcher creates a new project or needs to debug a failing pipeline, the project setup agent guides them through:

1. Linking an ontology, pipeline, and data sources to the project
2. Triggering hydration and monitoring progress
3. Diagnosing failures from job logs
4. Discovering and adding new data sources from the registry
5. Creating new YAML configs on the fly

The agent understands the RAIL project lifecycle (`draft → ready → hydrated`) and enforces it — for example, it will not trigger hydration unless a pipeline is linked.

---

## API Route — `/api/v1/project-agent`

Router: `packages/api/app/routers/project_agent.py`

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/chat` | `{project_id, message, history[], model?}` | SSE stream |
| POST | `/task` | `{project_id, task, model?}` | `{execution_job_id}` |

### `POST /chat`

Streaming chat endpoint. Accepts a `project_id` to scope all tools to that project. Returns SSE events:

```
data: {"type": "text_delta", "text": "Let me check your project..."}
data: {"type": "tool_call", "id": "call_abc", "name": "get_project_info", "args": {}}
data: {"type": "tool_result", "id": "call_abc", "name": "get_project_info", "result": {...}}
data: {"type": "done"}
```

### `POST /task`

Fires an **autonomous agent run** without user interaction. Tracks progress via `executionJobs`. Returns immediately with `execution_job_id`; frontend polls or subscribes to job status.

Used for background tasks like: "set up this project with unemployment data and run hydration."

---

## Tool Catalog

All tools are scoped to the `project_id` passed in the request.

### `get_project_info`

Returns the current project state: `name`, `slug`, `status`, `ontologyConfigSlug`, `pipelineConfigSlug`, `apiConfigSlugs[]`.

**Rule:** Called first on every new conversation before any other tool.

### `list_available_configs`

Lists all configs in the platform that can be linked to the project.

| Parameter | Type | Values |
|-----------|------|--------|
| `config_type` | string | `"ontologies"` \| `"apis"` \| `"pipelines"` \| `"all"` |

Returns lists of `{name, slug}` objects. **Always call before linking anything** — never guess a slug.

### `link_ontology`

Sets the project's ontology config. Writes `ontologyConfigSlug` to the project record.

```json
{"slug": "nj-ontology"}
```

### `link_pipeline`

Sets the project's pipeline config and advances status to `"ready"`. Writes `pipelineConfigSlug`.

```json
{"slug": "nj-census-pipeline"}
```

### `add_data_source` / `remove_data_source`

Attaches or detaches an API config slug from `apiConfigSlugs[]` on the project.

```json
{"slug": "census-acs5-nj"}
```

### `run_hydration`

Triggers the hydration job for the project's linked pipeline. Returns `jobId`.

Precondition: pipeline must be linked. The tool returns an error if not.

### `get_recent_jobs`

Lists the most recent hydration jobs for the project.

| Parameter | Default |
|-----------|---------|
| `limit` | 5 |

Returns: `[{jobId, status, createdAt, errorMessage, stepResults[]}]`

Status values: `queued`, `running`, `success`, `failed`, `cancelled`

### `get_job_logs`

Fetches detailed log lines for a specific job. Used to diagnose failures.

```json
{"job_id": "j_abc123"}
```

Returns: `[{level, message, timestamp}]` — e.g. `[error] Failed to fetch Census data: 429 rate limited`

### `create_config`

Creates a new YAML config in the platform (ontology, API, or pipeline). After creating, use `add_data_source` or `link_pipeline` to attach it.

| Parameter | Description |
|-----------|-------------|
| `config_type` | `"apis"` \| `"ontologies"` \| `"pipelines"` |
| `name` | Human-readable name |
| `slug` | URL-safe unique slug |
| `content` | Full YAML string |

### `search_data_registry`

Searches `dataSourceRegistry` for known public data series. Used to discover what data is available before creating configs.

| Parameter | Required |
|-----------|----------|
| `query` | yes |
| `provider` | no |
| `geography` | no |
| `limit` | no (default 10) |

### `save_to_knowledge_base`

Saves a research note, configuration summary, or compiled finding to `contextDocuments` scoped to the project.

| Parameter | Description |
|-----------|-------------|
| `name` | Document title |
| `content` | Full text content |

---

## Standard Workflows

### New project setup
1. `get_project_info` — see current state
2. `list_available_configs("all")` — discover what exists
3. `link_ontology`, `link_pipeline`, `add_data_source` as needed
4. `run_hydration` → `get_recent_jobs` to confirm success

### Debug a failed job
1. `get_recent_jobs` — find the failed job ID
2. `get_job_logs(job_id)` — read the error
3. Explain root cause and suggest a fix

### Add a new data source
1. `search_data_registry(query=<topic>)` — find matching datasets
2. `list_available_configs("apis")` — check if config already exists
3. If not: `create_config` with proper YAML, then `add_data_source`
4. If yes: `add_data_source(slug=<existing slug>)`

---

## Autonomous Task Endpoint

`POST /project-agent/task` accepts a free-text `task` and runs the full agent loop without user input. Progress is tracked as an `executionJob` record in Convex.

The endpoint returns immediately:
```json
{"execution_job_id": "ej_xyz"}
```

The frontend subscribes to this job's status and displays a progress feed.

**Use cases:**
- "Set up this project with Census ACS5 unemployment data for New Jersey and run hydration"
- "Debug why the last hydration failed and apply the fix"
- "Add GDP data from the World Bank to this project"

---

## Relationship to the Research Agent

| | Project Setup Agent | Research Agent |
|--|---------------------|----------------|
| **Router** | `/project-agent` | `/agent` |
| **Purpose** | Configure project structure | Run research workflows |
| **Input** | `project_id` + message | `project_id?` + message |
| **Tool focus** | link configs, run hydration, debug jobs | SQL, Python, ontology queries, reports |
| **Persistence** | `projectChats` Convex table | `agentSessions` Convex table |
| **UI** | Project dashboard chat panel | `/[project]/agent` page |
| **Autonomous mode** | Yes — `POST /task` | No |

---

## Convex Table — `projectChats`

Project setup agent conversations are stored in `projectChats` (distinct from the research agent's `agentSessions`).

| Field | Type | Notes |
|-------|------|-------|
| `projectId` | string | Foreign key to `projects._id` |
| `messages` | array | `[{role, content, toolCalls?, toolResults?}]` |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## Frontend — Project Chat Panel

The project setup agent is accessible from the project dashboard as a side panel. It is pre-scoped to the current project — the user does not need to specify a project.

**Entry points:**
- "Set up my project" button on the project overview page
- "Debug" button on failed job cards in the jobs list
- "Add data" button on the sources page
