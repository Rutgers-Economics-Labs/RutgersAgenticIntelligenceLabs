# Platform Architecture

RAIL is a monorepo containing three packages that work together to provide a YAML-driven ontology hydration platform with a real-time web interface.

## Monorepo Layout

```
packages/
  engine/               Python hydration engine (owlready2 + SQLite)
  api/                  FastAPI service (wraps engine, exposes REST)
  web/                  Next.js frontend + Convex backend-as-a-service
scripts/
  seed_convex.py        One-shot script: load local YAMLs into Convex
Makefile                Root orchestration (install, dev, hydrate, seed, …)
.env                    Copied from .env.example; not committed
```

## Package Responsibilities

| Package | Runtime | Role |
|---------|---------|------|
| `packages/engine/` | Python 3.11+ | OWL ontology builder and pipeline orchestrator; no web dependencies |
| `packages/api/` | Python + uvicorn | HTTP bridge: wraps engine modules, owns Convex mutations for jobs, exposes REST to the web |
| `packages/web/` | Node.js + Next.js 15 | React frontend; Convex for real-time config/job state; calls FastAPI for ontology data |

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
                              Background task: hydration_worker.run()
                                        │
                              ┌─────────┴──────────────────────────┐
                              │ Write YAMLs to tmpdir               │
                              │ Spawn: pipeline_runner_cli.py       │
                              │ Stream stdout → Convex jobLogs      │
                              │ On success: reload ontology_service │
                              └─────────────────────────────────────┘

Browser (jobs page) → useQuery(api.jobs.list) ← Convex reactive push
Browser (jobs page) → GET /api/v1/jobs/{id}/logs ← FastAPI polls Convex
```

## Data Flow — Ontology Queries

```
Browser → lib/api.ts → GET /api/v1/ontology/* → ontology_service (owlready2 + onto.db)
Browser → lib/api.ts → POST /api/v1/analysis/plugins/{slug}/run → analysis_runner
```

## Data Flow — Config Management

```
Browser → Convex reactive queries → apiConfigs / ontologyConfigs / pipelineConfigs
Browser → Convex mutations → create / update / delete configs
FastAPI  → POST /api/v1/configs/validate → yaml_service.validate()
```

## Convex Project

- **Project URL:** `https://colorless-elephant-150.convex.cloud`
- **Tables:** `apiConfigs`, `ontologyConfigs`, `pipelineConfigs`, `hydrationJobs`, `jobLogs`
- **Environment:** deploy key is a dev-environment key (`dev:colorless-elephant-150|…`)
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

## Key Design Decisions

**Engine unchanged.** The Python engine is used as-is; no modifications to its core hydration logic. The API service adds it to `sys.path` at startup and imports from it directly.

**Convex as source of truth for config.** All YAML configs live in Convex. The hydration worker fetches them at job start, writes them to a `tempfile.TemporaryDirectory`, and runs the engine against that tmpdir. The engine never reads from Convex directly.

**owlready2 single-thread executor.** owlready2's SQLite backend is not thread-safe. `ontology_service` uses `ThreadPoolExecutor(max_workers=1)` so all OWL reads share one thread.

**Ontology hot-swap.** When a hydration job completes, `hydration_worker` calls `ontology_service.load(new_db_path)`, replacing the in-memory World. Subsequent API requests see the new data without a server restart.

**Real-time job progress.** The worker streams `print()` output from the engine subprocess line-by-line to Convex `jobLogs`. The browser subscribes via `useQuery(api.jobs.list)` — Convex pushes updates automatically; no polling required.
