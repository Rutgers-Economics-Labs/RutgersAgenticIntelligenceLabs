# Projects

A **project** is the primary unit of organization in RAIL. It is a research domain with its own ontology, data sources, pipelines, analysis scripts, and domain agent — all backed by a GitHub repository and tracked in Convex.

---

## Project Identity

Every project has:
- A **slug** — URL-safe identifier, e.g. `nj-economics`. Immutable after creation.
- A **GitHub repository** — the durable store for all project configs and scripts.
- A **Convex record** — the operational cache powering the UI and API.
- An **ontology** — a project-specific OWL ontology derived from kernel + selected templates + custom extensions.
- A **DuckDB file** — a SQL-queryable mirror of the ontology, rebuilt on every successful hydration.
- A **domain agent** — an AI agent scoped to this project's data and action catalog.

---

## GitHub Repository Layout

Every project repo follows this convention:

```
{project-slug}/
  rail.yaml                    # project manifest — describes this project
  ontology/
    extension.yaml             # project-specific OWL classes and properties
  configs/
    apis/
      {source-slug}.yaml       # one file per data source config
    pipelines/
      {pipeline-slug}.yaml     # one file per pipeline config
  transforms/
    {module}.py                # DataFrame transform functions
  analysis/
    {plugin}.py                # analysis plugins (analyze(onto, **kwargs) interface)
  agents/
    config.yaml                # domain agent configuration
  .github/
    workflows/
      rail-sync.yml            # push webhook trigger
```

The platform reads from and writes to all files under this structure. Users may also work with these files directly on their local machine using `rail-py`.

---

## Project Manifest (`rail.yaml`)

The manifest is the authoritative description of the project. It lives at the repo root.

```yaml
name: NJ Economic Analysis                    # display name
slug: nj-economics                            # immutable, URL-safe identifier
description: "Labor, housing, and income indicators for New Jersey"
github: rutgers-rail/nj-economics             # org/repo
default_branch: main                          # branch the platform syncs with

ontology_templates:                           # optional; applied once at project creation
  - us-geography
  - economic-indicators

agent:
  model: claude-sonnet-4-6                    # LiteLLM model string
  allowed_actions:                            # governs what the agent may do
    - discover_sources
    - create_data_source
    - create_pipeline
    - run_pipeline
    - query_ontology
    - run_sql
    - execute_python
    - generate_report
    - publish_to_github
```

### Manifest Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Human-readable project name |
| `slug` | string | yes | Immutable URL-safe identifier. Must match the Convex `projects.slug`. |
| `description` | string | no | One-paragraph description shown in the project gallery |
| `github` | string | yes | `{org}/{repo}` — the GitHub repository backing this project |
| `default_branch` | string | default `main` | Branch the platform syncs with |
| `ontology_templates` | list of slugs | no | Templates to merge at project creation. Not re-applied on later hydrations. |
| `agent.model` | string | default `claude-sonnet-4-6` | LiteLLM model string for the domain agent |
| `agent.allowed_actions` | list of strings | no | Action catalog for the domain agent. If absent, all actions are allowed. |

---

## Project Lifecycle

```
draft ──────► ready ──────► hydrated
  │             │               │
  │  configs    │  run           │  re-run
  │  defined    │  pipeline      │  pipeline
  └─────────────┘               ▼
                            ontology + DuckDB live
```

| Status | Meaning |
|--------|---------|
| `draft` | Project created; manifest present; configs not yet complete |
| `ready` | At least one pipeline config exists and is valid |
| `hydrated` | At least one successful hydration job has completed; ontology and DuckDB are available |

Status transitions are managed by the platform automatically based on config presence and job outcomes.

---

## Convex Schema — `projects`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Display name |
| `slug` | string | Immutable, indexed `by_slug` |
| `description` | string? | |
| `github` | string? | `{org}/{repo}` |
| `defaultBranch` | string | default `"main"` |
| `status` | string | `"draft"` \| `"ready"` \| `"hydrated"`, indexed `by_status` |
| `ontologyTemplates` | string[] | Template slugs applied at creation |
| `agentModel` | string | LiteLLM model string |
| `agentAllowedActions` | string[] | Action catalog |
| `lastJobId` | string? | ID of the most recent hydration job |
| `lastHydratedAt` | number? | ms timestamp of last successful hydration |
| `ontologyDbPath` | string? | Storage key for the active `onto.db` |
| `duckdbPath` | string? | Storage key for the active `onto.duckdb` |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## GitHub Sync

The platform and the GitHub repo stay in sync bidirectionally. Either side can initiate an update; the sync is idempotent.

### Push to GitHub → Platform

1. A push to the project's `default_branch` fires a webhook to `POST /api/v1/github/sync`.
2. The API verifies the HMAC-SHA256 signature using `GITHUB_WEBHOOK_SECRET`.
3. The API fetches the changed files from the GitHub Contents API.
4. For each changed file:
   - `rail.yaml` → update Convex `projects` record
   - `configs/apis/*.yaml` → upsert `apiConfigs` in Convex
   - `configs/pipelines/*.yaml` → upsert `pipelineConfigs` in Convex
   - `ontology/extension.yaml` → upsert `ontologyConfigs` in Convex
   - `agents/config.yaml` → update `projects.agentModel` and `projects.agentAllowedActions`
   - `transforms/*.py` or `analysis/*.py` → stored as plain files; engine picks them up from repo clone at hydration time
5. If a pipeline config changed, a hydration job is automatically triggered.

### Platform → GitHub

1. A user edits a config on the platform (Convex mutation fires).
2. The frontend calls `POST /api/v1/github/publish` with the project slug and changed config.
3. The API uses the GitHub App to commit the changed file to the project repo on `default_branch`.
4. The resulting push fires the webhook — the platform handles it idempotently (content hash check prevents re-hydration if content is unchanged).

### Conflict Handling

If both sides change the same file between syncs, the platform takes the GitHub version as authoritative (last GitHub push wins). The UI shows a warning if local Convex state diverges from the last known GitHub commit hash.

---

## GitHub App Setup

The platform uses a single GitHub App (not per-user OAuth) installed on the RAIL organization:

| Setting | Value |
|---------|-------|
| App ID | `GITHUB_APP_ID` env var |
| Private key | `GITHUB_APP_PRIVATE_KEY` env var (PEM string) |
| Permissions | `contents: write`, `metadata: read`, `webhooks: read` |
| Webhook events | `push` |
| Webhook URL | `https://{platform-domain}/api/v1/github/sync` |

The API generates a short-lived installation token at request time using the App credentials. This token is used for all Contents API calls (read and write). No user-level OAuth is required.

---

## Local Development with `rail-py`

Researchers can work with a project entirely on their local machine:

```python
import rail

# Clone the project repo first, then:
project = rail.local("./nj-economics")

# Run hydration locally (uses packages/engine directly)
project.hydrate("nj-hydration")

# Query the resulting ontology
df = project.query("SELECT hasName, hasValue, hasDate FROM LaborIndicator LIMIT 100")

# Access the owlready2 World directly
onto = project.ontology()
for state in onto.State.instances():
    print(state.hasName, state.hasPopulation)
```

When `rail.local()` is used, the engine runs against the local repo's `configs/` and `ontology/` directories — no API keys or Convex access required. The same YAML configs power both local and cloud execution.

```python
# Cloud mode — connects to the platform API
project = rail.connect("nj-economics", api_key="rail_...")
project.hydrate("nj-hydration")          # triggers job on platform
df = project.query("SELECT ...")         # queries platform DuckDB
```

The interface is identical regardless of mode. The `rail-py` package lives in `packages/rail-py/` and is installed internally via:

```bash
pip install -e packages/rail-py                    # local monorepo
pip install git+ssh://git@github.com/rutgers-rail/rail.git#subdirectory=packages/rail-py
```

---

## Connector Templates in the Context of Projects

When a project's API config uses `extends`, the hydration worker resolves it:

```yaml
# projects/nj-economics/configs/apis/nj_unemployment.yaml
extends: fred-observations          # slug of a connectorTemplate in Convex
name: nj_unemployment
params:
  series_id: NJURN
  observation_start: "2000-01-01"
```

The connector template provides the boilerplate (base URL, auth params, response format, field mapping conventions). The project config overrides only what is specific to this data request. The engine receives a fully merged YAML with no `extends` field — connector resolution is invisible to the engine.

See `specs/connectors.md` for the full connector template specification.

---

## Project Scoping Rules

All platform resources are scoped to a project:

| Resource | Scoped to project? | Notes |
|----------|-------------------|-------|
| API configs | yes | Stored in Convex with `projectSlug` field |
| Ontology configs | yes | |
| Pipeline configs | yes | |
| Hydration jobs | yes | |
| Agent sessions | yes | Domain agent only sees its project's data |
| Workspaces | yes | |
| Connector templates | **no** | Shared across all projects |
| Ontology templates | **no** | Shared across all projects |
| Ontology (onto.db) | yes | Per-project OWL file |
| DuckDB | yes | Per-project DuckDB file |

All project data and research is public to all platform users — there is no per-user access control at this time.
