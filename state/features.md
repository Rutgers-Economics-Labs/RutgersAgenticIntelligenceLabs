# Feature State

Cross-cutting feature status for the current `yaml-driven-hydration` branch.

Legend:
- `✅` implemented and working in this branch
- `🟡` implemented but partial, rough, or missing follow-through
- `❌` not implemented yet

---

## Core Hydration Pipeline

**Spec:** `specs/engine.md`, `specs/yaml-config.md`, `specs/architecture.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Fetch REST API data | ✅ | `api_runner`, foreach support, caching |
| Fetch CSV / Excel | ✅ | |
| Uploaded file hydration | ✅ | `storage_key` is resolved to local temp files before engine run |
| PDF / DOCX hydration inputs | ✅ | Document `storage_key` resolution works in worker |
| Build OWL ontology from YAML | ✅ | `ontology_builder` |
| Map rows to OWL individuals | ✅ | `pipeline_runner` |
| Object property relationships | ✅ | |
| DataFrame transforms | ✅ | |
| Post-hydration ontology transforms | ✅ | |
| Kernel YAML injection | ✅ | `packages/engine/ontology/kernel.yaml` + worker merge |
| Connector `extends` resolution | ✅ | `connector_service.resolve()` in worker |
| Incremental hydration mode | ✅ | `hydration_mode` validated and passed through |
| Export OWL to DuckDB | ✅ | |
| Hot-swap ontology on job completion | ✅ | |
| Semantic index build | 🟡 | Built on success; failures are logged as non-fatal |
| Real-time log streaming to Convex | ✅ | |
| Trigger hydration from UI | ✅ | |
| Auto quality snapshot on hydration | ❌ | Quality APIs exist, but hydration does not auto-snapshot yet |

---

## Ontology Kernel & Templates

**Spec:** `specs/ontology-kernel.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `kernel.yaml` file | ✅ | Present at `packages/engine/ontology/kernel.yaml` |
| Kernel injection in worker | ✅ | |
| `ontologyTemplates` Convex table | ✅ | |
| Ontology template CRUD API | ✅ | |
| Ontology template UI | ✅ | Registry pages exist |
| Template application at project creation | 🟡 | Project schema supports template slugs; creation flow is still basic |
| `platform-objects` OWL template | ❌ | Not yet surfaced as a seeded template/module |
| IRI namespace conventions | 🟡 | Legacy/example IRIs still appear in places; migration is not complete |

---

## Connector Templates

**Spec:** `specs/connectors.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `connectorTemplates` Convex table | ✅ | |
| `extends` field in API configs | ✅ | Validation supports it |
| `fields_append` field | ✅ | Merge helper supports append semantics |
| Deep-merge resolution in worker | ✅ | |
| Connector CRUD API | ✅ | `/api/v1/connectors` |
| Connector gallery in UI | ✅ | Registry and project sources UI |
| "Use Template" fork to project | ✅ | Sources page can create project configs from templates |
| Connector validation endpoint | ✅ | |
| `/resolve` preview endpoint | ✅ | |
| Seeded connector catalog depth | 🟡 | Structure exists; template catalog still needs stronger seed coverage |

---

## Projects & GitHub Sync

**Spec:** `specs/projects.md`, `specs/api.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Project CRUD (Convex) | ✅ | |
| Project gallery UI | ✅ | Current card-based page |
| Project-scoped routes/layout | ✅ | `[project]` routes are live |
| Project context endpoint | ✅ | `/api/v1/projects/{slug}/context` |
| GitHub repo/default branch fields | ✅ | Present in schema |
| `agentModel` / `agentAllowedActions` fields | ✅ | Present in schema and used by agent |
| GitHub service/router | ✅ | `github_service.py` + `/github/*` routes exist |
| `POST /api/v1/github/sync` | ✅ | Webhook route exists |
| `POST /api/v1/github/publish` | ✅ | Publish route exists |
| `GET /api/v1/github/status/{slug}` | ✅ | Basic status endpoint exists |
| `POST /api/v1/github/link` | ✅ | |
| Webhook processing (update Convex on push) | 🟡 | Implemented, but sync semantics are still fairly lightweight |
| Auto-trigger hydration on push | 🟡 | Implemented for changed pipelines; broader sync robustness still needs work |
| `rail.yaml` manifest support | ❌ | Still not a real source of truth in the codebase |

---

## Domain Agent

**Spec:** `specs/agents.md`

| Capability | Status | Notes |
|------------|--------|-------|
| Base agent loop (multi-turn, SSE) | ✅ | |
| Provider-agnostic LLM (LiteLLM) | ✅ | |
| Project-scoped chat | ✅ | `project` query param + project UI route |
| Context snapshot assembly | ✅ | Snapshot is built and streamed |
| `context_snapshot` SSE event | ✅ | |
| `allowed_actions` filtering | ✅ | Filtered from project context |
| Tool: `discover_sources` | ✅ | |
| Tool: `generate_report` | ✅ | |
| Tool: `publish_to_github` | ✅ | |
| Agent page with session list panel | ✅ | `[project]/agent` |
| `ContextSnapshot` card in UI | ✅ | |
| Session persistence | ✅ | Project-scoped `agentSessions` usage |

---

## Scheduled Pipelines & Live Data

**Spec:** `specs/schedule.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `schedule` field in pipeline YAML | ✅ | Validation accepts it |
| `hydration_mode: incremental` | ✅ | |
| `scheduledPipelines` Convex table | ✅ | |
| Scheduler service | ✅ | |
| `/api/v1/schedules` router | ✅ | |
| Schedule UI on pipelines/jobs pages | ✅ | |
| Active collection badge/status | ✅ | |
| Auto-snapshot after incremental run | ❌ | Not wired yet |

---

## Data Quality

**Spec:** `specs/data-quality.md`

| Capability | Status | Notes |
|------------|--------|-------|
| `GET /quality/report` | ✅ | |
| `POST /quality/snapshot` | ✅ | |
| `GET /quality/diff` | ✅ | |
| Quality page UI | ✅ | |
| `project_id` scoping | ✅ | Project artifact paths are used |
| Auto-snapshot on hydration | ❌ | Still missing |

---

## SQL, Execution, and `rail-py`

| Capability | Status | Notes |
|------------|--------|-------|
| DuckDB SQL queries | ✅ | |
| NL→SQL translation | ✅ | |
| Python execution (inproc/subprocess/docker) | ✅ | |
| Artifact upload from analysis run-code | ✅ | |
| `executionJobs` tracking | ✅ | |
| `packages/rail-py` package skeleton | ✅ | |
| `rail.connect()` | ✅ | |
| `rail.local()` | ✅ | |
| `Project.query()` / `hydrate()` / `ontology()` / `agent` | ✅ | Core surface exists |
| Local repo install/documentation for `rail` | 🟡 | README now documents editable install; packaging ergonomics can still improve |

---

## Current Cleanup Focus

These items are implemented but still active cleanup targets:

| Item | Status | Notes |
|------|--------|-------|
| Hydration compatibility validation | ✅ | Pipeline validator now accepts current checked-in pipeline shape |
| Python test drift | 🟡 | Suite mostly passes; keep an eye on environment parity |
| Frontend route/test drift | 🟡 | Tests updated to current agent route model |
| State docs accuracy | 🟡 | This file and `state/gap.md` now reflect the branch; keep them current as features land |
