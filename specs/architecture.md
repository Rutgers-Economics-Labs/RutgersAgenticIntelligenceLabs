# Platform Architecture

RAIL is a monorepo containing three packages that work together to provide a YAML-driven ontology hydration platform with a real-time web interface and an AI research agent.

## Monorepo Layout

```
packages/
  engine/               Python hydration engine (owlready2 + SQLite)
  api/                  FastAPI service (wraps engine, exposes REST)
  web/                  Next.js frontend + Convex backend-as-a-service
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

## Detailed Specifications

- [API Service](api.md) — FastAPI endpoints and Convex client.
- [Frontend](frontend.md) — Next.js App Router and local state.
- [Hydration Engine](engine.md) — Python pipeline orchestrator and owlready2 interactions.
- [Engine Plugins](plugins.md) — Transform and analysis plugin architecture.
- [YAML Config Schemas](yaml-config.md) — Definitions for API sources, Ontology, and Pipelines.
- [Engine Standalone UI](engine-ui.md) — Streamlit explorer app (`app.py`).

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
                              │ Write YAMLs to tmpdir                   │
                              │ Spawn: pipeline_runner_cli.py           │
                              │ Stream stdout → Convex jobLogs          │
                              │ On success: reload ontology_service     │
                              │             export to DuckDB            │
                              │             update sql_service path     │
                              └────────────────────────────────────────┘

Browser (jobs page) → useQuery(api.jobs.list) ← Convex reactive push
Browser (jobs page) → GET /api/v1/jobs/{id}/logs ← FastAPI polls Convex
```

## Data Flow — Ontology Queries

```
Browser → lib/api.ts → GET /api/v1/ontology/* → ontology_service (owlready2 + onto.db)
Browser → lib/api.ts → POST /api/v1/analysis/plugins/{slug}/run → analysis_runner (owlready2, in-proc)
Browser → lib/api.ts → POST /api/v1/analysis/run-code → subprocess_code_runner + StorageService (artifacts)
Browser → lib/api.ts → POST /api/v1/sql → sql_service (DuckDB onto.duckdb)
Browser → lib/api.ts → POST /api/v1/execute → code_runner (inproc exec or subprocess per RAIL_EXECUTE_MODE)
```

## Data Flow — AI Agent

```
Browser → POST /api/v1/agent/chat (SSE) → agent_service.run_chat()
                                                │
                                    ┌───────────┴───────────┐
                                    │ LiteLLM (any provider) │
                                    │  model: AI_MODEL env   │
                                    └───────────┬───────────┘
                                                │ tool calls
                                    ┌───────────┴───────────┐
                                    │ list_configs           │ → Convex query
                                    │ create_config          │ → Convex mutation
                                    │ run_pipeline           │ → jobs._trigger_job()
                                    │ query_ontology         │ → ontology_service
                                    │ run_sql                │ → sql_service
                                    │ get_sql_schema         │ → sql_service
                                    │ execute_python         │ → code_runner
                                    │ get_series_data        │ → ontology_service
                                    │ search_entities        │ → ontology_service
                                    └───────────────────────┘
                                                │
                              SSE events streamed back to browser:
                              text_delta, tool_call, tool_result, done
```

## Data Flow — Config Management

```
Browser → Convex reactive queries → apiConfigs / ontologyConfigs / pipelineConfigs
Browser → Convex mutations → create / update / delete configs
FastAPI  → POST /api/v1/configs/validate → yaml_service.validate()
```

## Convex Project

- **Project URL:** `https://animated-caterpillar-927.convex.cloud`
- **Tables:** `apiConfigs`, `ontologyConfigs`, `pipelineConfigs`, `hydrationJobs`, `jobLogs`, `projects`, `agentSessions`, `workspaces`
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

## Key Design Decisions

**Engine unchanged.** The Python engine is used as-is; no modifications to its core hydration logic. The API service adds it to `sys.path` at startup and imports from it directly.

**Convex as source of truth for config.** All YAML configs live in Convex. The hydration worker fetches them at job start, writes them to a `tempfile.TemporaryDirectory`, and runs the engine against that tmpdir. The engine never reads from Convex directly.

**owlready2 single-thread executor.** owlready2's SQLite backend is not thread-safe. `ontology_service` uses `ThreadPoolExecutor(max_workers=1)` so all OWL reads share one thread. The DuckDB export also runs in this executor to avoid concurrent SQLite access.

**DuckDB as SQL mirror.** After every hydration, `ontology_service.export_to_duckdb()` writes each OWL class to a DuckDB table at `{engine_root}/ontology/onto.duckdb`. This file is used for all SQL queries and is also injected into the Python code execution sandbox.

**Ontology hot-swap.** When a hydration job completes, `hydration_worker` calls `ontology_service.load(new_db_path)`, replacing the in-memory World. Subsequent API requests see the new data without a server restart. The DuckDB file is also regenerated at this point.

**Provider-agnostic LLM.** `llm_service` wraps LiteLLM so any model string it supports works: `claude-sonnet-4-6`, `gemini/gemini-2.0-flash`, `openrouter/meta-llama/llama-3.1-70b-instruct`, etc. The model is configured via `AI_MODEL` env var and can be overridden per-request.

**Agent tool loop.** The agent uses OpenAI function-calling format (LiteLLM normalizes for each provider). The loop runs up to 10 turns; each turn streams via SSE. Tool calls are executed server-side between turns; results are fed back into the message history before the next LLM call.

**Real-time job progress.** The worker streams `print()` output from the engine subprocess line-by-line to Convex `jobLogs`. The browser subscribes via `useQuery(api.jobs.list)` — Convex pushes updates automatically; no polling required.
