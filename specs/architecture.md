# Platform Architecture

RAIL is a **Data OS** — a platform where ontologies are the type system, connectors are the drivers, pipelines are the processes, and agents are programs that run against a structured knowledge graph. Projects are isolated research domains, each backed by a GitHub repository and owning their own ontology and data. A shared registry of connector templates and ontology modules makes the ecosystem composable without forcing a global schema.

## Monorepo Layout

```
packages/
  engine/               Python hydration engine (owlready2 + SQLite)
  api/                  FastAPI service (wraps engine, exposes REST)
  web/                  Next.js frontend + Convex backend-as-a-service
  rail-py/              Internal Python client package (cloud + local modes)
scripts/
  seed_convex.py        One-shot script: load local YAMLs into Convex
Makefile                Root orchestration (install, dev, hydrate, seed, …)
.env                    Local secrets at repo root; not committed
```

## Package Responsibilities

| Package | Runtime | Role |
|---------|---------|------|
| `packages/engine/` | Python 3.11+ | OWL ontology builder and pipeline orchestrator; no web dependencies |
| `packages/api/` | Python + uvicorn | HTTP bridge: wraps engine modules, owns Convex mutations for jobs, exposes REST to the web; runs LLM-powered agent |
| `packages/web/` | Node.js + Next.js 15 | React frontend; Convex for real-time config/job/session state; calls FastAPI for ontology data, SQL, code execution, and agent chat |
| `packages/rail-py/` | Python 3.11+ | Internal client package: `rail.connect()` (cloud, wraps FastAPI) and `rail.local()` (direct engine import) with identical project interface |

## The Three-Layer Ontology Model

RAIL ontologies are structured in three layers that mirror an OS:

| Layer | Analogy | Contents | Mutability |
|-------|---------|----------|------------|
| **Kernel** | OS kernel | Universal properties every individual carries | Immutable — changing is a breaking change |
| **Standard Library** | stdlib / package registry | Ontology templates: geography, economics, demographics, time series | Additive only — templates never constrain userspace |
| **Userspace** | User programs | Project-specific classes, properties, individuals | Fully custom — platform has no opinion here |

The kernel is defined in `packages/engine/ontology/kernel.yaml` and automatically merged into every project ontology at hydration time. Templates live in the Convex `ontologyTemplates` table and are applied at project creation. Project ontology extensions live in the project's GitHub repo and are the primary customization surface. See `specs/ontology-kernel.md` for the full specification.

## Connectors as Drivers

Shared connector templates abstract away data source specifics (auth patterns, response formats, pagination) so projects only specify what is unique to them (series IDs, filters, date ranges). Templates live in the Convex `connectorTemplates` table — any platform user can add or edit them via the UI.

A project API config declares `extends: <connector_slug>` to inherit a template; its own fields override the template at hydration time. Connector *types* that require new engine code (e.g., GraphQL, S3, WebSocket) are added via PR to the platform repo. YAML-level connector patterns (new REST APIs, new FRED series conventions) are added via the platform UI with no deploy required.

## Projects

Every research domain is a **project**: an isolated ontology + dataset + pipeline + agent bundle backed by a GitHub repository. Projects are registered in Convex and their configs are kept in sync bidirectionally with their repo (push to GitHub → platform rehydrates; edit on platform → commit to GitHub). All project data and research is public to all platform users. See `specs/projects.md`.

## Convex Tables

| Table | Purpose |
|-------|---------|
| `apiConfigs` | Project-scoped API source configs (YAML) |
| `ontologyConfigs` | Project-scoped ontology extension configs (YAML) |
| `pipelineConfigs` | Project-scoped pipeline configs (YAML) |
| `hydrationJobs` | Job tracking for pipeline runs |
| `jobLogs` | Streaming log lines from hydration worker |
| `projects` | Project registry — manifest, GitHub link, status, agent config |
| `agentSessions` | Agent conversation history (project-scoped) |
| `workspaces` | Notebook-style workspaces with cells (project-scoped) |
| `connectorTemplates` | Shared data source connector templates — editable by any user |
| `ontologyTemplates` | Shared ontology module templates — editable by any user |

## Detailed Specifications

- [API Service](api.md) — FastAPI endpoints and Convex client.
- [Frontend](frontend.md) — Next.js App Router and local state.
- [Hydration Engine](engine.md) — Python pipeline orchestrator and owlready2 interactions.
- [Engine Plugins](plugins.md) — Transform and analysis plugin architecture.
- [YAML Config Schemas](yaml-config.md) — Definitions for API sources, Ontology, and Pipelines.
- [Engine Standalone UI](engine-ui.md) — Streamlit explorer app (`app.py`).
- [Ontology Kernel & Templates](ontology-kernel.md) — Kernel properties, template system, extension rules.
- [Projects](projects.md) — Project manifest, GitHub sync, lifecycle.
- [Connectors](connectors.md) — Shared connector templates, extends resolution, initial connector set.
- [Agents](agents.md) — Domain agent model, tool catalog, research workflow loop.
- [Scheduled Pipelines](schedule.md) — Cron scheduling, incremental hydration, collection windows.
- [Data Quality](data-quality.md) — Quality reports, null rates, snapshot diffing.
- [rail-py](rail-py.md) — Internal Python client package (cloud + local modes).
- [Midterm Improvements](improvements.md) — Planned architectural improvements post-initial release.

## Data Flow — Config-driven Hydration

```
User (browser) → pipelines page → POST /api/v1/jobs
                                        │
                              jobs router (FastAPI)
                                        │
                              ┌─────────┴──────────┐
                              │ query Convex for    │
                              │ pipeline + API YAML │
                              └─────────┬──────────┘
                                        │
                              Convex: create hydrationJob (queued)
                                        │
                              asyncio.create_task: hydration_worker.run()
                                        │
                              ┌─────────┴──────────────────────────────┐
                              │ Resolve connector templates             │
                              │   for each api config with `extends`:  │
                              │   fetch connectorTemplates from Convex  │
                              │   deep-merge: project overrides template│
                              │ Write merged YAMLs to tmpdir            │
                              │ Spawn: pipeline_runner_cli.py           │
                              │ Stream stdout → Convex jobLogs          │
                              │ On success: reload ontology_service     │
                              │             export to DuckDB            │
                              │             update sql_service path     │
                              └────────────────────────────────────────┘

Browser (jobs page) → useQuery(api.jobs.list) ← Convex reactive push
Browser (jobs page) → GET /api/v1/jobs/{id}/logs ← FastAPI polls Convex
```

## Data Flow — GitHub Sync

```
── Push to GitHub ──────────────────────────────────────────────────────
GitHub push event
    → POST /api/v1/github/sync  (HMAC-verified webhook)
    → fetch changed files from GitHub Contents API
    → update Convex: apiConfigs / ontologyConfigs / pipelineConfigs
    → if pipeline config changed: trigger hydration job automatically

── Platform → GitHub ───────────────────────────────────────────────────
User edits config on platform (Convex mutation)
    → POST /api/v1/github/publish
    → commit changed configs to project repo (default branch)
    → GitHub push fires webhook → platform echoes back (idempotent, no re-hydrate on same content)
```

## Data Flow — Ontology Queries

```
Browser → lib/api.ts → GET /api/v1/ontology/*     → ontology_service (owlready2 + onto.db)
Browser → lib/api.ts → POST /api/v1/analysis/...  → analysis_runner (owlready2, in-proc)
Browser → lib/api.ts → POST /api/v1/sql           → sql_service (DuckDB onto.duckdb)
Browser → lib/api.ts → POST /api/v1/execute       → code_runner (inproc exec or subprocess)
```

## Data Flow — AI Agent (Domain-scoped)

Each project has its own agent scoped to that project's ontology, configs, and action catalog.

```
Browser → POST /api/v1/agent/chat?project={slug} (SSE) → agent_service.run_chat()
                                                              │
                                              ┌───────────────┴──────────────┐
                                              │ Assemble context snapshot     │
                                              │  from project ontology:       │
                                              │  available_classes            │
                                              │  available_series             │
                                              │  pipeline_summary             │
                                              │  schema_ddl                   │
                                              └───────────────┬──────────────┘
                                                              │
                                                  LiteLLM (any provider)
                                                              │ tool calls (governed by action catalog)
                                              ┌───────────────┴──────────────┐
                                              │ discover_sources              │ → connectorTemplates (Convex)
                                              │ list_configs                  │ → project configs (Convex)
                                              │ create_config                 │ → Convex mutation
                                              │ run_pipeline                  │ → jobs._trigger_job()
                                              │ query_ontology                │ → ontology_service
                                              │ run_sql                       │ → sql_service
                                              │ get_sql_schema                │ → sql_service
                                              │ execute_python                │ → code_runner
                                              │ get_series_data               │ → ontology_service
                                              │ search_entities               │ → ontology_service
                                              │ generate_report               │ → artifact storage
                                              │ publish_to_github             │ → github service
                                              └──────────────────────────────┘
                                                              │
                                              SSE events streamed back to browser:
                                              text_delta, tool_call, tool_result, done
```

## Data Flow — Config Management

```
Browser → Convex reactive queries → apiConfigs / ontologyConfigs / pipelineConfigs / connectorTemplates / ontologyTemplates
Browser → Convex mutations → create / update / delete any config or template
FastAPI  → POST /api/v1/configs/validate → yaml_service.validate()
```

## Convex Project

- **Project URL:** `https://animated-caterpillar-927.convex.cloud`
- **Tables:** see table list above
- **Server-side access:** `Authorization: Convex <deploy_key>` header; never exposed to the browser
- **Client-side access:** `NEXT_PUBLIC_CONVEX_URL` via `ConvexProvider`; uses generated type-safe `api.*` hooks

## Environment Variables

All env vars live in `.env` (repo root); the Makefile `-include .env; export` forwards them to every sub-process.

| Variable | Used by | Purpose |
|----------|---------|---------|
| `CONVEX_URL` | API, seed script | Convex project HTTP endpoint |
| `CONVEX_DEPLOY_KEY` | API, seed script | Server-side auth for Convex HTTP API |
| `FRED_API_KEY` | Engine (via API) | Federal Reserve Economic Data API key |
| `ENGINE_ROOT` | API | Absolute path to `packages/engine/` |
| `RAIL_ANALYSIS_DIR` | API | Absolute path to `packages/engine/analysis/` |
| `RAIL_TRANSFORM_DIR` | API | Absolute path to `packages/engine/transforms/` |
| `NEXT_PUBLIC_CONVEX_URL` | Web (browser) | Convex WebSocket endpoint for `ConvexProvider` |
| `NEXT_PUBLIC_API_URL` | Web (browser) | FastAPI base URL, default `http://localhost:8000/api/v1` |
| `AI_MODEL` | API | LiteLLM model string, default `claude-sonnet-4-6` |
| `AI_TEMPERATURE` | API | LLM temperature, default `0.3` |
| `AI_MAX_TOKENS` | API | LLM max tokens, default `8192` |
| `ANTHROPIC_API_KEY` | API (LiteLLM) | Anthropic Claude models |
| `OPENAI_API_KEY` | API (LiteLLM) | OpenAI GPT models |
| `GOOGLE_API_KEY` | API (LiteLLM) | Google Gemini models |
| `OPENROUTER_API_KEY` | API (LiteLLM) | OpenRouter proxy for any model |
| `GITHUB_APP_ID` | API | GitHub App for repo read/write access |
| `GITHUB_APP_PRIVATE_KEY` | API | GitHub App private key (PEM) |
| `GITHUB_WEBHOOK_SECRET` | API | HMAC secret for verifying push webhooks |

## Key Design Decisions

**Data OS, not data warehouse.** RAIL doesn't store raw data — it stores structured knowledge. The ontology is the type system. Pipelines are processes that transform raw data into typed individuals. Agents are programs that operate on the resulting knowledge graph.

**Engine unchanged.** The Python engine is used as-is; no modifications to its core hydration logic. The API service adds it to `sys.path` at startup and imports from it directly.

**Convex as source of truth for config.** All YAML configs live in Convex. The hydration worker fetches them at job start, resolves connector template `extends`, writes merged YAMLs to a `tempfile.TemporaryDirectory`, and runs the engine against that tmpdir. The engine never reads from Convex directly.

**Connector templates resolved at hydration time.** Templates are fetched from Convex and deep-merged with the project config in the hydration worker. The engine receives a fully resolved YAML with no `extends` fields. This keeps the engine oblivious to the template system.

**Kernel properties injected at hydration time.** The hydration worker prepends the kernel ontology module to the pipeline's ontology config before writing to tmpdir. Projects never need to declare kernel properties explicitly.

**owlready2 single-thread executor.** owlready2's SQLite backend is not thread-safe. `ontology_service` uses `ThreadPoolExecutor(max_workers=1)` so all OWL reads share one thread.

**DuckDB as SQL mirror.** After every hydration, `ontology_service.export_to_duckdb()` writes each OWL class to a DuckDB table. This file is used for all SQL queries and injected into the Python code execution sandbox.

**Ontology hot-swap.** When a hydration job completes, `hydration_worker` calls `ontology_service.load(new_db_path)`, replacing the in-memory World without a server restart.

**Domain agents before platform agent.** Each project has its own agent scoped to its ontology, data, and action catalog. Context assembly is tight and deterministic. A platform-wide routing agent is a future concern.

**Provider-agnostic LLM.** `llm_service` wraps LiteLLM so any model string works: `claude-sonnet-4-6`, `gemini/gemini-2.0-flash`, `openrouter/meta-llama/llama-3.1-70b-instruct`, etc.

**GitHub is the durable store for project configs.** Convex is the operational cache that powers the UI. GitHub is the source of truth for project definition. Either side can initiate an update; the sync is bidirectional and idempotent.
