# Layer State

Current implementation state of each architectural layer against the specs.

---

## Engine — `packages/engine/`

**Spec:** `specs/engine.md`, `specs/plugins.md`, `specs/yaml-config.md`

| Component | Status | Notes |
|-----------|--------|-------|
| `api_runner.py` | ✅ | Fully implemented — REST, CSV, Excel, foreach, caching, field mapping |
| `ontology_builder.py` | ✅ | Fully implemented — build_from_yaml, load_from_owl, classes/properties |
| `pipeline_runner.py` | ✅ | Fully implemented — full hydration loop, relationships, post-transforms |
| `transform_runner.py` | ✅ | Fully implemented — module::function notation, DataFrame + ontology transforms |
| `analysis_runner.py` | ✅ | Fully implemented — discover + run plugin interface |
| `pipeline_runner_cli.py` | ✅ | Subprocess entrypoint |
| `code_subprocess_cli.py` | ✅ | Sandboxed Python execution entrypoint |
| `scrape_runner.py` | 🔵 | Web scraping support — not yet in spec |
| `stream_runner.py` | 🔵 | Live data stream simulation — not yet in spec |
| `kernel.yaml` | ❌ | Kernel ontology module — not created |
| `hydration_mode: incremental` | ❌ | Engine does not yet support incremental mode (always drops onto.db) |
| `extends` resolution | ❌ | Connector template inheritance not handled by engine (handled by worker) |
| Kernel injection | ❌ | Hydration worker does not yet prepend kernel.yaml to project ontology |

**Transforms** (`packages/engine/transforms/`):
| File | Status |
|------|--------|
| `census_clean.py` | ✅ strip_state_suffix, add_state_abbreviations |

**Analysis plugins** (`packages/engine/analysis/`):
| File | Status |
|------|--------|
| `unemployment_trends.py` | ✅ |
| `example_basic_analysis.py` | ✅ |
| `builtins.py` | 🔵 Not in spec |

---

## API — `packages/api/`

**Spec:** `specs/api.md`

### Routers

| Router | Spec status | Impl status | Notes |
|--------|------------|-------------|-------|
| `/ontology` | ✅ Specced | ✅ Built | All endpoints match spec |
| `/analysis` | ✅ Specced | ✅ Built | Plugins + run-code + artifacts |
| `/configs` | ✅ Specced | ✅ Built | CRUD + validate + scrape-preview + doc-preview |
| `/jobs` | ✅ Specced | ✅ Built | CRUD + logs + cancel |
| `/sql` | ✅ Specced | ✅ Built | query + translate + schema + tables |
| `/execute` | ✅ Specced | ✅ Built | inproc + subprocess + Docker modes |
| `/agent` | ✅ Specced | 🟡 Partial | Missing project scoping (`?project=`), missing `discover_sources` / `generate_report` / `publish_to_github` tools |
| `/quality` | ✅ Specced | ✅ Built | report + snapshot + diff |
| `/projects` | ✅ Specced | 🟡 Partial | Basic CRUD exists; missing `/context` endpoint, `hydrate` delegation, template application |
| `/connectors` | ✅ Specced | ❌ Not built | `dataSourceRegistry` is a related but different concept (catalog, not YAML templates) |
| `/ontology-templates` | ✅ Specced | ❌ Not built | |
| `/github` | ✅ Specced | ❌ Not built | No webhook, no publish, no sync |
| `/schedules` | ✅ Specced | ❌ Not built | |
| `/registry` | 🔵 Not in spec | 🔵 Built | Data source catalog (provider/sourceId/description/tags/exampleYaml) — different from connector templates |
| `/project-agent` | 🔵 Not in spec | 🔵 Built | Project-scoped agent with different tool set (link_ontology, run_hydration, get_job_logs, etc.) |
| `/context` | 🔵 Not in spec | 🔵 Built | Context/knowledge base document management |
| `/questions` | 🔵 Not in spec | 🔵 Built | Q&A with structured response blocks |
| `/storage` | 🔵 Not in spec | 🔵 Built | File upload/download |

### Services

| Service | Status | Notes |
|---------|--------|-------|
| `ontology_service.py` | ✅ | Full implementation |
| `hydration_worker.py` | 🟡 | Exists; missing: kernel injection, `extends` resolution, incremental mode, quality snapshot on completion |
| `sql_service.py` | ✅ | Full implementation |
| `agent_service.py` | 🟡 | Exists; missing project scoping + 3 new tools |
| `llm_service.py` | ✅ | Full implementation |
| `code_runner.py` | ✅ | Full implementation |
| `subprocess_code_runner.py` | ✅ | Full implementation |
| `storage_service.py` | ✅ | Local + S3 modes |
| `yaml_service.py` | 🟡 | Exists; missing validation for `extends`, `schedule`, `hydration_mode` fields |
| `embedding_service.py` | ✅ | Full implementation |
| `convex_client.py` | ✅ | Full implementation |
| `github_service.py` | ❌ | Not built |
| `connector_service.py` | ❌ | Not built |
| `scheduler_service.py` | ❌ | Not built |
| `registry_service.py` | 🔵 | Exists — manages `dataSourceRegistry` Convex table |
| `document_service.py` | 🔵 | Exists — PDF/text/URL extraction |
| `scrape_service.py` | 🔵 | Exists — web scraping |
| `pipeline_validate.py` | 🔵 | Exists — pipeline validation helpers |
| `project_artifacts_service.py` | 🔵 | Exists — per-project artifact management |
| `execution_manager.py` | 🔵 | Exists — manages async execution jobs |

---

## Convex Schema — `packages/web/convex/schema.ts`

**Spec:** `specs/architecture.md` (Convex Tables section), `specs/projects.md`, `specs/connectors.md`, `specs/schedule.md`, `specs/data-quality.md`

| Table | Status | Notes |
|-------|--------|-------|
| `apiConfigs` | ✅ | Matches spec |
| `ontologyConfigs` | ✅ | Matches spec |
| `pipelineConfigs` | ✅ | Matches spec |
| `hydrationJobs` | ✅ | Matches spec; also has `projectId` foreign key (ahead of spec) |
| `jobLogs` | ✅ | Matches spec; also supports `stdout`/`stderr` log levels |
| `projects` | 🟡 | Exists but missing: `github`, `defaultBranch`, `ontologyTemplates`, `agentModel`, `agentAllowedActions`, `lastHydratedAt` fields. Has `approach` (data-first/ontology-first) not in new spec. |
| `agentSessions` | ✅ | Matches spec |
| `workspaces` | ✅ | Matches spec |
| `connectorTemplates` | ❌ | Not created — `dataSourceRegistry` is a different concept |
| `ontologyTemplates` | ❌ | Not created |
| `scheduledPipelines` | ❌ | Not created |
| `executionJobs` | 🔵 | Not in spec — tracks async SQL/code execution jobs |
| `projectChats` | 🔵 | Not in spec — project-scoped agent chat sessions (separate from agentSessions) |
| `analysisScripts` | 🔵 | Not in spec — saved analysis scripts per project |
| `contextDocuments` | 🔵 | Not in spec — knowledge base documents per project |
| `ontologySnapshots` | 🟡 | Exists as spec's `qualitySnapshots` — same concept, different name. Spec should be updated to match. |
| `questionSessions` | 🔵 | Not in spec — Q&A history per project |
| `dataSourceRegistry` | 🔵 | Not in spec — searchable catalog of known data series (different from connectorTemplates) |

---

## Frontend — `packages/web/`

**Spec:** `specs/frontend.md`

### Navigation & Layout

| Component | Status | Notes |
|-----------|--------|-------|
| Flat sidebar (current) | ✅ Built | Exists and works |
| `TopBar` with project switcher | ❌ | Not built — current nav has no project context at top level |
| Project-scoped `Sidebar` | ❌ | Not built — current sidebar is platform-flat |
| `ProjectSwitcher` dropdown | ❌ | Not built |
| `[project]` route segment | ❌ | All pages are currently flat under `(dashboard)/` |

### Pages

| Route (current) | Route (spec) | Status | Notes |
|----------------|-------------|--------|-------|
| `/projects` | `/projects` | 🟡 | Exists; flat gallery. Missing new card design with status badges, "New Project" modal, template picker. |
| `/projects/[slug]` | — | 🔵 | Project detail page exists — not in spec's new nav model |
| `/workspace` | `/[project]/agent` | 🟡 | Unscoped agent chat. Missing: session list panel, ContextSnapshot card, project binding. |
| `/explorer` | `/[project]/ontology/classes` | 🟡 | Works; needs project scoping, new URL structure |
| `/graph` | `/[project]/ontology/graph` | 🟡 | Works; needs project scoping |
| `/configs` | `/[project]/sources` + `/[project]/pipelines` | 🟡 | Combined configs page. Spec splits into Sources (with connector gallery) and Pipelines. |
| `/sql` | `/[project]/sql` | 🟡 | Works; needs project scoping |
| `/analysis` | `/[project]/analysis` | 🟡 | Works; needs project scoping |
| `/jobs` | `/[project]/jobs` | 🟡 | Works; needs project scoping |
| `/quality` | `/[project]/quality` | ✅ | Fully matches spec — best-implemented page |
| `/pipelines` | `/[project]/pipelines` | 🟡 | Works; to be merged into Sources/Pipelines split |
| — | `/[project]/overview` | ❌ | Not built |
| — | `/[project]/ontology/schema` | ❌ | Not built |
| — | `/[project]/sources` | ❌ | Not built (connector gallery + project sources split) |
| — | `/[project]/settings` | ❌ | Not built |
| `/registry` | `/registry` | 🟡 | Exists — shows `dataSourceRegistry` entries. Spec calls for connector YAML templates + ontology templates. Different concept. |
| `/questions` | — | 🔵 | Q&A interface — not in spec |
| `/context` | — | 🔵 | Knowledge base document manager — not in spec |
| `/tools` | — | 🔵 | Tools page — not in spec |

### Convex Functions

| File | Status | Notes |
|------|--------|-------|
| `configs.ts` | ✅ | Full CRUD for api/ontology/pipeline configs |
| `jobs.ts` | ✅ | Full job + log CRUD |
| `agent.ts` | ✅ | Full session CRUD |
| `workspaces.ts` | ✅ | Full workspace CRUD |
| `projects.ts` | 🟡 | Exists; missing fields per updated schema |
| `connectors.ts` | ❌ | Not created |
| `ontologyTemplates.ts` | ❌ | Not created |
| `registry.ts` | 🔵 | dataSourceRegistry CRUD — different from spec connectors |
| `quality.ts` | ✅ | Snapshot CRUD (as `ontologySnapshots`) |
| `projectChats.ts` | 🔵 | Not in spec |
| `questionSessions.ts` | 🔵 | Not in spec |
| `executions.ts` | 🔵 | Not in spec |
| `context.ts` | 🔵 | Not in spec |
| `analysis.ts` | 🔵 | Not in spec |

### `lib/api.ts`

| Namespace | Status | Notes |
|-----------|--------|-------|
| `ontology` | ✅ | Full implementation |
| `analysis` | ✅ | Full implementation |
| `configs` | ✅ | Full implementation |
| `jobs` | ✅ | Full implementation |
| `sql` | ✅ | Full implementation |
| `execute` | ✅ | Full implementation |
| `agent` | ✅ | Full implementation |
| `quality` | ✅ | Full implementation |
| `projects` | 🟡 | Partial — needs connector/template endpoints |
| `connectors` | ❌ | Not built |
| `ontologyTemplates` | ❌ | Not built |
| `github` | ❌ | Not built |
| `schedules` | ❌ | Not built |

---

## rail-py — `packages/rail-py/`

**Spec:** `specs/rail-py.md`

| Component | Status | Notes |
|-----------|--------|-------|
| Package directory | ❌ | `packages/rail-py/` does not exist |
| `rail.connect()` | ❌ | |
| `rail.local()` | ❌ | |
| `Project` class | ❌ | |
| `OntologyView` | ❌ | |
| `AgentClient` | ❌ | |
| `pyproject.toml` / `setup.py` | ❌ | |
