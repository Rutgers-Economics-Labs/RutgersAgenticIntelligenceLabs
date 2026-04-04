# Build Queue

Ordered list of what needs to be built, grouped by phase. Each item references the spec it implements. Items within a phase are roughly ordered by dependency.

---

## Phase 0 — Foundation (unblocks everything else)

These items are prerequisites for most other phases.

### 0.1 — Ontology Kernel YAML
**Spec:** `specs/ontology-kernel.md`
- Create `packages/engine/ontology/kernel.yaml` with 6 universal properties
- Update `hydration_worker.py` to prepend kernel YAML to every project ontology before writing to tmpdir
- Update `yaml_service.validate()` to ignore kernel property names in project configs
- **Blocks:** platform-objects template, IRI conventions, any project using the new architecture

### 0.2 — Connector `extends` Resolution
**Spec:** `specs/connectors.md`, `specs/yaml-config.md`
- Add `connectorTemplates` table to `convex/schema.ts`
- Create `convex/connectors.ts` with CRUD functions
- Create `packages/api/app/services/connector_service.py` — `resolve(base_content, extends_slug)`
- Update `hydration_worker.py` to call `connector_service.resolve()` on any API config with `extends`
- Update `yaml_service.validate()` to allow `extends` and `fields_append` fields
- Seed initial connector templates via `scripts/seed_convex.py`
- **Blocks:** connector gallery UI, any project using shared connectors

### 0.3 — Projects Schema Update
**Spec:** `specs/projects.md`
- Add missing fields to `convex/schema.ts` `projects` table: `github`, `defaultBranch`, `ontologyTemplates`, `agentModel`, `agentAllowedActions`, `lastHydratedAt`
- Update `convex/projects.ts` CRUD to handle new fields
- Update `packages/api/app/routers/projects.py` to expose `/context` endpoint (returns agent context snapshot)
- **Blocks:** GitHub sync, domain agent scoping, project creation flow

---

## Phase 1 — Connector & Template Registry

### 1.1 — Connector Template UI
**Spec:** `specs/connectors.md`, `specs/frontend.md`
- Add `/registry` page redesign: two tabs (Connectors / Ontology Templates) with YAML card gallery
- Add `ConnectorEditor` component — YAML editor + validate + save
- "Use Template" button forks connector into project API config
- `/resolve` preview endpoint: `POST /api/v1/connectors/resolve`
- **Depends on:** 0.2

### 1.2 — Ontology Templates
**Spec:** `specs/ontology-kernel.md`
- Add `ontologyTemplates` table to `convex/schema.ts`
- Create `convex/ontologyTemplates.ts` with CRUD functions
- Create `packages/api/app/routers/ontology_templates.py`
- Seed initial templates (us-geography, economic-indicators, demographics, platform-objects)
- Template picker in project creation flow
- **Depends on:** 0.3

---

## Phase 2 — Project Navigation Redesign

### 2.1 — Top Bar + Project Switcher
**Spec:** `specs/frontend.md`
- Create `components/layout/TopBar.tsx` — platform name, `ProjectSwitcher` dropdown, "New Project" button
- Create `components/layout/ProjectSwitcher.tsx` — lists all projects with status badges
- Remove project links from current flat Sidebar

### 2.2 — Project-Scoped Route Layout
**Spec:** `specs/frontend.md`
- Create `app/[project]/layout.tsx` — project shell with TopBar + project-scoped Sidebar
- Migrate existing pages under `[project]/` route segment:
  - `/explorer` → `/[project]/ontology/classes`
  - `/graph` → `/[project]/ontology/graph`
  - `/sql` → `/[project]/sql`
  - `/analysis` → `/[project]/analysis`
  - `/jobs` → `/[project]/jobs`
  - `/quality` → `/[project]/quality`
  - `/workspace` → `/[project]/agent`
- Keep existing flat routes as redirects during transition
- **Depends on:** 2.1

### 2.3 — New Project Pages
**Spec:** `specs/frontend.md`
- `/[project]/overview` — dashboard with metric cards, job history, class breakdown chart
- `/[project]/sources` — project data sources + connector gallery side-by-side
- `/[project]/ontology/schema` — merged ontology YAML viewer
- `/[project]/settings` — rail.yaml viewer, GitHub sync status, danger zone
- **Depends on:** 2.2

---

## Phase 3 — GitHub Sync

### 3.1 — GitHub App Service
**Spec:** `specs/api.md` (github_service), `specs/projects.md`
- Add `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` to `config.py`
- Create `packages/api/app/services/github_service.py` — installation token, get_file, put_file, list_changed_files

### 3.2 — GitHub Webhook (GitHub → Platform)
**Spec:** `specs/api.md` (/github router), `specs/projects.md`
- Create `packages/api/app/routers/github.py`
- Implement `POST /github/sync` — HMAC verify, fetch changed files, update Convex, trigger hydration
- **Depends on:** 3.1, 0.3

### 3.3 — Publish to GitHub (Platform → GitHub)
**Spec:** `specs/api.md`, `specs/projects.md`
- Implement `POST /github/publish` — commit changed configs to project repo
- Add "Publish to GitHub" button on `/[project]/settings` page
- **Depends on:** 3.1, 3.2

---

## Phase 4 — Domain Agent Upgrade

### 4.1 — Project-Scoped Agent Context
**Spec:** `specs/agents.md`
- Update `agent_service.py` to accept `project_slug` parameter
- Implement context snapshot assembly: fetch classes, schema, sources, pipelines from project state
- Filter tool schemas to project's `allowed_actions`
- Emit `context_snapshot` SSE event at start of each conversation
- **Depends on:** 0.3

### 4.2 — New Agent Tools
**Spec:** `specs/agents.md`
- Add `discover_sources` tool — queries `connectorTemplates` by tag/query
- Add `generate_report` tool — stores artifact via storage_service
- Add `publish_to_github` tool — calls github_service (path-safety validated)
- **Depends on:** 0.2, 3.1, 4.1

### 4.3 — Agent UI Upgrade
**Spec:** `specs/frontend.md`
- Add session list left panel to `/[project]/agent` page
- Add `ContextSnapshot` card (shown before first message)
- Bind agent page to project context via URL
- **Depends on:** 4.1, 2.2

---

## Phase 5 — Scheduled Pipelines

### 5.1 — Incremental Hydration Mode
**Spec:** `specs/schedule.md`, `specs/engine.md`
- Add `hydration_mode` YAML field to `yaml_service.validate()`
- Update `pipeline_runner.py` to skip onto.db deletion when `hydration_mode: incremental`
- Pass `hydration_mode` through `hydration_worker.run()`

### 5.2 — Scheduler Service
**Spec:** `specs/schedule.md`
- Add `scheduledPipelines` table to `convex/schema.ts`
- Create `packages/api/app/services/scheduler_service.py`
- Register scheduler in FastAPI `lifespan` startup/shutdown
- Create `packages/api/app/routers/schedules.py` — full CRUD + pause/resume

### 5.3 — Schedule UI
**Spec:** `specs/schedule.md`, `specs/frontend.md`
- Schedule modal on pipeline cards (frequency + window + enable toggle)
- Active collection badge on pipeline cards
- Schedule status section on jobs page
- **Depends on:** 5.2

---

## Phase 6 — rail-py Package

### 6.1 — Package Skeleton
**Spec:** `specs/rail-py.md`
- Create `packages/rail-py/` with `pyproject.toml`, `rail/__init__.py`
- Implement `CloudClient` wrapping FastAPI HTTP endpoints
- Implement `LocalEngine` importing engine modules directly
- Implement `Project` unified interface

### 6.2 — OntologyView and AgentClient
**Spec:** `specs/rail-py.md`
- Implement `OntologyView` wrapping owlready2 World
- Implement `AgentClient` with `ask()` (blocking + streaming)
- Write example notebooks / README
- **Depends on:** 6.1

---

## Spec Alignment Items (not new features, just keeping spec accurate)

| Item | Status |
|------|--------|
| `ontologySnapshots` vs `qualitySnapshots` | ✅ Resolved — `specs/data-quality.md` updated to use `ontologySnapshots` |
| `dataSourceRegistry` | ✅ Resolved — `specs/registry.md` written; added to `specs/architecture.md` |
| `projectChats` | ✅ Resolved — added to `specs/architecture.md` Convex tables; covered by `specs/project-agent.md` |
| `executionJobs` | ✅ Resolved — added to `specs/architecture.md` Convex tables |
| Q&A interface (`/questions`) | ✅ Resolved — `specs/questions.md` written |
| Knowledge base (`/context`) | ✅ Resolved — `specs/context.md` written |
| `project_agent.py` tools | ✅ Resolved — `specs/project-agent.md` written; `specs/agents.md` updated to clarify two agent types |
| IRI namespace | ❌ Still open — decide: keep `http://example.org/rutgers_ontology.owl` or migrate to `http://rail.rutgers.edu/ontology/` |

---

## Midterm Improvements (post Phase 6)

See `specs/improvements.md` for full details. Rough order:

1. Object property join tables in DuckDB export (#2 in improvements.md)
2. Cross-project SQL via DuckDB ATTACH (#3)
3. Ontology migration system (#6)
4. Pluggable triple store backend (#1)
5. Unstructured data pipelines / GABRIEL integration (#5)
6. Historical snapshots (#7)
7. Streaming CSV (#8)
