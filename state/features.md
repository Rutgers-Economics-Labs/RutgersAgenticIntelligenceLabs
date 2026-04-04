# Feature State

Cross-cutting feature status. Each feature may span Engine, API, Convex, and Frontend.

---

## Core Hydration Pipeline

**Spec:** `specs/engine.md`, `specs/yaml-config.md`, `specs/architecture.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Fetch REST API data | ✅ | api_runner, foreach, caching |
| Fetch CSV / Excel | ✅ | |
| Build OWL ontology from YAML | ✅ | ontology_builder |
| Map data rows to OWL individuals | ✅ | pipeline_runner |
| Object property relationships | ✅ | |
| DataFrame transforms | ✅ | transform_runner |
| Post-hydration ontology transforms | ✅ | |
| Export OWL to DuckDB | ✅ | ontology_service.export_to_duckdb |
| Hot-swap ontology on job completion | ✅ | |
| Real-time log streaming to Convex | ✅ | hydration_worker → Convex jobLogs |
| Trigger hydration from UI | ✅ | |
| Kernel YAML injection | ❌ | `kernel.yaml` not created; worker doesn't prepend it |
| Connector `extends` resolution | ❌ | hydration_worker doesn't fetch/merge connector templates |
| Incremental hydration mode | ❌ | Engine always drops onto.db; `hydration_mode` field not supported |
| Quality snapshot on job completion | 🟡 | ontologySnapshots table exists; worker doesn't auto-snapshot yet |

---

## Ontology Kernel & Templates

**Spec:** `specs/ontology-kernel.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `kernel.yaml` file | ❌ | Not created at `packages/engine/ontology/kernel.yaml` |
| Kernel injection in worker | ❌ | |
| `ontologyTemplates` Convex table | ❌ | |
| Template gallery in UI | ❌ | |
| Template application at project creation | ❌ | |
| `platform-objects` OWL template | ❌ | Pipeline/DataSource/Agent individuals not written to ontology |
| IRI namespace conventions | 🟡 | IRIs use `http://example.org/rutgers_ontology.owl` — needs update to `http://rail.rutgers.edu/ontology/` |

---

## Connector Templates

**Spec:** `specs/connectors.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `connectorTemplates` Convex table | ❌ | `dataSourceRegistry` exists but is a different concept — catalog of known series, not inheritable YAML templates |
| `extends` field in API configs | ❌ | Not in yaml_service validation |
| `fields_append` field | ❌ | |
| Deep-merge resolution in worker | ❌ | |
| Connector gallery in UI | 🟡 | `/registry` page shows `dataSourceRegistry` entries — not YAML templates with inheritance |
| "Use Template" fork to project | ❌ | |
| Connector validation endpoint | ❌ | |
| `/resolve` preview endpoint | ❌ | |
| Initial connector seed (15+ templates) | ❌ | `dataSourceRegistry` has different shape; needs migration or parallel table |

**Note:** `dataSourceRegistry` and `connectorTemplates` are related but distinct concepts. `dataSourceRegistry` is a searchable catalog of known data series (FRED/Census/BLS series with metadata and example YAML). `connectorTemplates` are full YAML templates that projects `extends` to inherit connection boilerplate. Both are valuable — they may eventually be merged or linked, but for now they are separate concerns. The spec's connector template system needs to be built from scratch.

---

## Projects

**Spec:** `specs/projects.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Project CRUD (Convex) | ✅ | projects table + CRUD functions |
| Project gallery UI | 🟡 | Exists at `/projects`; flat design, not new card spec |
| `rail.yaml` manifest parsing | ❌ | `rail.yaml` format not defined in code; project manifest fields not synced |
| GitHub repo field on project | ❌ | Not in current schema |
| `ontologyTemplates` selection at creation | ❌ | |
| `agentModel` / `agentAllowedActions` fields | ❌ | Not in current schema |
| Project lifecycle state machine | 🟡 | `draft`/`ready`/`hydrated` states exist; auto-transition logic not implemented |
| Project-scoped ontology/DuckDB paths | ✅ | `activeOntologyDbPath`, `activeOntologyDuckdbPath` fields exist |
| `/api/v1/projects/{slug}/context` | ❌ | `/context` router exists but different concept (knowledge base docs) |

---

## GitHub Sync

**Spec:** `specs/projects.md` (GitHub Sync section), `specs/api.md` (/github router)

| Capability | Status | Notes |
|------------|--------|-------|
| GitHub App credentials in config | ❌ | `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` not in Settings |
| `github_service.py` | ❌ | Not created |
| `POST /api/v1/github/sync` (webhook) | ❌ | Not created |
| `POST /api/v1/github/publish` | ❌ | Not created |
| `GET /api/v1/github/status/{slug}` | ❌ | Not created |
| `POST /api/v1/github/link` | ❌ | Not created |
| Webhook processing (update Convex on push) | ❌ | |
| Auto-trigger hydration on push | ❌ | |
| Commit platform edits back to GitHub | ❌ | |

---

## Domain Agents

**Spec:** `specs/agents.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Base agent loop (multi-turn, SSE) | ✅ | `agent_service.py` + `/agent/chat` |
| Provider-agnostic LLM (LiteLLM) | ✅ | |
| Project-scoped agent (`?project=`) | 🟡 | `/project-agent` router exists with project scoping, but different tool set |
| Context snapshot assembly | 🟡 | `/project-agent` has `get_project_info` tool; spec's structured context snapshot not yet assembled |
| `allowed_actions` catalog enforcement | ❌ | No per-project action filtering |
| Tool: `discover_sources` | ❌ | Not in agent tool set |
| Tool: `list_configs` | ✅ | |
| Tool: `create_config` | ✅ | |
| Tool: `run_pipeline` | ✅ | |
| Tool: `query_ontology` | ✅ | |
| Tool: `run_sql` | ✅ | |
| Tool: `get_sql_schema` | ✅ | |
| Tool: `execute_python` | ✅ | |
| Tool: `get_series_data` | ✅ | |
| Tool: `search_entities` | ✅ | |
| Tool: `generate_report` | ❌ | Not implemented |
| Tool: `publish_to_github` | ❌ | Not implemented (depends on GitHub sync) |
| `context_snapshot` SSE event | ❌ | Not emitted |
| Agent page with session list panel | ❌ | Current `/workspace` has no session browser |
| `ContextSnapshot` card in UI | ❌ | |
| Project chat sessions (`projectChats`) | 🔵 | Exists — separate from spec's `agentSessions` scoped to project |

---

## Scheduled Pipelines & Live Data

**Spec:** `specs/schedule.md`, `specs/yaml-config.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `schedule` field in pipeline YAML | ❌ | |
| `hydration_mode: incremental` YAML field | ❌ | |
| `scheduledPipelines` Convex table | ❌ | |
| `scheduler_service.py` | ❌ | `stream_runner.py` exists in engine (simulation only) — different concept |
| `/api/v1/schedules` router | ❌ | |
| Schedule UI on pipelines page | ❌ | |
| Active collection badge on pipeline cards | ❌ | |
| Auto-snapshot after incremental run | ❌ | |

---

## Data Quality

**Spec:** `specs/data-quality.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `GET /quality/report` | ✅ | Full implementation — per-table metrics, column stats, freshness |
| `POST /quality/snapshot` | ✅ | Saves to `ontologySnapshots` (spec calls it `qualitySnapshots` — same thing) |
| `GET /quality/diff` | ✅ | Two-snapshot comparison, table and column drift |
| Quality page UI | ✅ | Full implementation — summary cards, TableCard, DiffView |
| Auto-snapshot on hydration | ❌ | Worker doesn't call snapshot yet |
| Quality link from jobs page | ❌ | |
| `project_id` scoping | 🟡 | Parameter accepted; resolves via project's `activeOntologyDuckdbPath` |

---

## SQL & Code Execution

**Spec:** `specs/api.md`

| Capability | Status | Notes |
|------------|--------|-------|
| DuckDB SQL queries | ✅ | |
| NL→SQL translation | ✅ | |
| Schema browser | ✅ | |
| Python sandbox (inproc) | ✅ | |
| Python sandbox (subprocess) | ✅ | |
| Python sandbox (Docker) | ✅ | |
| Object property join tables in DuckDB | ❌ | Planned in `specs/improvements.md` — not yet built |
| Artifact upload from run-code | ✅ | |
| Execution job tracking (`executionJobs`) | 🔵 | Built but not in spec |

---

## rail-py Package

**Spec:** `specs/rail-py.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Package skeleton | ❌ | `packages/rail-py/` directory doesn't exist |
| `rail.connect()` cloud mode | ❌ | |
| `rail.local()` local engine mode | ❌ | |
| `Project.query()` | ❌ | |
| `Project.hydrate()` | ❌ | |
| `Project.ontology()` → OntologyView | ❌ | |
| `Project.agent` → AgentClient | ❌ | |
| Internal GitHub install instructions | ❌ | |

---

## Unspecced Features (Built but Not in Spec)

These exist in the codebase and work. Previously-unspecced items have been documented:

| Feature | Spec | Status |
|---------|------|--------|
| Data source registry | `specs/registry.md` | ✅ Now specced |
| Q&A interface | `specs/questions.md` | ✅ Now specced |
| Knowledge base / Context docs | `specs/context.md` | ✅ Now specced |
| Project setup agent | `specs/project-agent.md` | ✅ Now specced |
| Execution job tracking | Referenced in `specs/project-agent.md` (autonomous task endpoint) | ✅ Partially specced |
| Web scraping | `scrape_service.py`, `scrape_runner.py` | 🔵 Still unspecced |
| Stream simulation | `stream_runner.py` | 🔵 Still unspecced — not production-ready |
| Analysis scripts management | `analysisScripts` Convex table | 🔵 Still unspecced |
| Tools page | `/tools` frontend page | 🔵 Still unspecced — purpose unclear |
