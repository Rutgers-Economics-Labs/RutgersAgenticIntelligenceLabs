# Frontend

The frontend is a Next.js 15 App Router application in `packages/web/`. It has two data sources:
- **Convex** (`convex/react` `useQuery`) — real-time config tables, job status, and shared registries.
- **FastAPI** (`lib/api.ts` typed fetch client) — ontology data, analysis results, SQL, code execution, and agent chat.

## Navigation Model

The UI has two contexts: **platform level** (projects gallery and shared registry) and **project level** (everything scoped to one project). A project switcher in the top bar moves between projects. The sidebar changes to reflect the active project context.

```
Top bar:   [RAIL]  [project switcher ▾]                    [+ New Project]

Sidebar (platform):          Sidebar (inside a project):
  Projects                     Overview
  Registry                     Ontology
    └ Connectors                 └ Classes
    └ Ontology Templates         └ Graph
                                 └ Schema
                               Sources
                               Pipelines
                               SQL
                               Agent
                               Analysis
                               Jobs
                               ─────────
                               Registry   (shared, same as platform)
                               Settings
```

## Directory Layout

```
packages/web/
  app/
    layout.tsx                        Root layout — ConvexProvider, dark theme
    convex-provider.tsx               "use client" wrapper around ConvexProvider
    page.tsx                          Root redirect → /projects
    (platform)/
      layout.tsx                      Platform shell with top bar only (no sidebar)
      projects/page.tsx               Project gallery
      registry/
        page.tsx                      Registry landing (tabs: Connectors, Ontology Templates)
        connectors/page.tsx           Connector template gallery + editor
        ontology-templates/page.tsx   Ontology template gallery + editor
    [project]/
      layout.tsx                      Project shell — top bar + project-scoped sidebar
      overview/page.tsx               Project dashboard
      ontology/
        page.tsx                      Ontology landing — redirects to /classes
        classes/page.tsx              Class tree + paginated instance browser
        graph/page.tsx                Force-directed graph
        schema/page.tsx               Merged ontology YAML viewer
      sources/page.tsx                Data source configs + connector template picker
      pipelines/page.tsx              Pipeline configs + run history
      sql/page.tsx                    DuckDB SQL editor with NL→SQL
      agent/page.tsx                  Domain agent chat
      analysis/page.tsx               Analysis plugin runner
      jobs/page.tsx                   Hydration job list + live logs
      settings/page.tsx               rail.yaml viewer, GitHub sync status
  components/
    layout/
      TopBar.tsx                      Project switcher, platform nav
      Sidebar.tsx                     Project-scoped left nav
      ProjectSwitcher.tsx             Dropdown — lists all projects with status badges
    registry/
      ConnectorCard.tsx               Connector template card with "Use" button
      OntologyTemplateCard.tsx        Ontology template card with "Apply" button
      ConnectorEditor.tsx             YAML editor + validate + save for connector templates
    ontology/
      ClassTree.tsx                   Hierarchical class list with instance counts
      EntityTable.tsx                 Paginated instance table with search
      EntityDetailPanel.tsx           Slide-in panel: properties + relationships
      GraphView.tsx                   react-force-graph-2d wrapper
    agent/
      AgentChat.tsx                   Message list + streaming text
      ToolCallCard.tsx                Collapsible tool call with args + result
      ContextSnapshot.tsx             "I have access to: N classes, M entities" card
      SessionList.tsx                 Left panel: previous conversations
    shared/
      YamlEditor.tsx                  Monaco-style YAML editor with live validation
      StatusBadge.tsx                 Colored status chip (draft/ready/hydrated/running/etc.)
      SplitPane.tsx                   Resizable two-panel layout
  convex/
    schema.ts                         Convex table definitions
    configs.ts                        apiConfigs, ontologyConfigs, pipelineConfigs CRUD
    jobs.ts                           hydrationJobs, jobLogs CRUD
    agent.ts                          agentSessions CRUD
    workspaces.ts                     workspaces CRUD
    projects.ts                       projects CRUD
    connectors.ts                     connectorTemplates CRUD
    ontologyTemplates.ts              ontologyTemplates CRUD
    _generated/                       Auto-generated Convex types (not edited manually)
  lib/
    api.ts                            Typed fetch client for FastAPI
  public/                             Static assets
  .env.local                          NEXT_PUBLIC_CONVEX_URL, NEXT_PUBLIC_API_URL
```

## New Convex Tables

### `connectorTemplates`
| Field | Type |
|-------|------|
| `slug` | string (indexed `by_slug`) |
| `name` | string |
| `description` | string |
| `version` | string |
| `tags` | string[] |
| `content` | string (raw YAML) |
| `usageCount` | number |
| `createdBy` | string |
| `createdAt` | number (ms) |
| `updatedAt` | number (ms) |

### `ontologyTemplates`
Same shape as `connectorTemplates`. `content` is an ontology YAML module.

## Convex Schema — `convex/schema.ts`

### `apiConfigs`
| Field | Type |
|-------|------|
| `name` | string |
| `slug` | string (indexed `by_slug`) |
| `content` | string (raw YAML) |
| `parsedSpec` | any |
| `sourceType` | string |
| `isPublic` | boolean (indexed `by_public`) |
| `tags` | string[] |
| `createdAt` | number (ms) |
| `updatedAt` | number (ms) |

### `ontologyConfigs`
Same as `apiConfigs` but without `sourceType`/`tags`; has `ontologyUri: string` instead.

### `pipelineConfigs`
Same as `apiConfigs`; adds `referencedApiSlugs: string[]`.

### `hydrationJobs`
| Field | Type |
|-------|------|
| `pipelineConfigId` | id("pipelineConfigs") |
| `pipelineSlug` | string |
| `status` | `"queued"` \| `"running"` \| `"success"` \| `"failed"` \| `"cancelled"` |
| `triggeredBy` | string? |
| `startedAt` | number? (ms) |
| `finishedAt` | number? (ms) |
| `errorMessage` | string? |
| `outputOwlPath` | string? |
| `outputDbPath` | string? |
| `stepResults` | `{stepName, status, rowCount?, errorMessage?, startedAt?, finishedAt?}[]` |
| `createdAt` | number (ms) |

Indexes: `by_pipeline` on `pipelineConfigId`, `by_status`, `by_created`.

### `jobLogs`
| Field | Type |
|-------|------|
| `jobId` | id("hydrationJobs") |
| `seq` | number |
| `level` | `"info"` \| `"warn"` \| `"error"` |
| `message` | string |
| `stepName` | string? |
| `timestamp` | number (ms) |

Indexes: `by_job` on `jobId`, `by_job_seq` on `[jobId, seq]`.

### `projects`
| Field | Type |
|-------|------|
| `name` | string |
| `slug` | string (indexed `by_slug`) |
| `description` | string? |
| `approach` | `"data-first"` \| `"ontology-first"` |
| `ontologyConfigSlug` | string? |
| `apiConfigSlugs` | string[] |
| `pipelineConfigSlug` | string? |
| `status` | `"draft"` \| `"ready"` \| `"hydrated"` (indexed `by_status`) |
| `lastJobId` | string? |
| `createdAt` | number (ms) |
| `updatedAt` | number (ms) |

### `agentSessions`
| Field | Type |
|-------|------|
| `title` | string |
| `model` | string |
| `messages` | `{role, content?, tool_calls?, tool_call_id?}[]` |
| `createdAt` | number (ms, indexed `by_created`) |
| `updatedAt` | number (ms) |

Message `role` is `"user"` \| `"assistant"` \| `"tool"`.

### `workspaces`
| Field | Type |
|-------|------|
| `title` | string |
| `sessionId` | string? |
| `pipelineSlug` | string? |
| `cells` | `{id, type, content, result?, role?}[]` |
| `createdAt` | number (ms, indexed `by_created`) |
| `updatedAt` | number (ms) |

Cell `type` is `"ai-text"` \| `"code"` \| `"sql"` \| `"table"` \| `"chart"` \| `"metric"`.

## Convex Functions — `convex/configs.ts`

| Export | Type | Description |
|--------|------|-------------|
| `listApis` | query | Returns all `apiConfigs` rows |
| `getApi` | query | Returns one row by `slug` |
| `createApi` | mutation | Inserts; sets `createdAt`/`updatedAt` to `Date.now()` |
| `updateApi` | mutation | Patches by `slug`; sets `updatedAt` |
| `deleteApi` | mutation | Deletes by `slug` |

Same pattern for `listOntologies/getOntology/createOntology/updateOntology/deleteOntology` and `listPipelines/getPipeline/createPipeline/updatePipeline/deletePipeline`.

## Convex Functions — `convex/jobs.ts`

| Export | Type | Description |
|--------|------|-------------|
| `create` | mutation | Inserts `hydrationJobs`; returns `{jobId}` |
| `updateJob` | mutation | Patches job fields by `jobId` (undefined fields skipped) |
| `updateStep` | mutation | Upserts a step in `stepResults` array by `stepName` |
| `appendLog` | mutation | Inserts one row into `jobLogs` |
| `list` | query | Returns up to `limit` jobs ordered by `createdAt` desc |
| `get` | query | Returns one job by `jobId` |
| `getLogs` | query | Returns log rows for a job; optional `afterSeq` cursor; `limit` default 200 |

## Convex Functions — `convex/agent.ts`

| Export | Type | Description |
|--------|------|-------------|
| `listSessions` | query | Returns up to `limit` sessions ordered by `createdAt` desc |
| `getSession` | query | Returns one session by `sessionId` |
| `createSession` | mutation | Inserts with empty `messages[]`; returns `{sessionId}` |
| `appendMessages` | mutation | Appends message objects to `session.messages` |
| `updateTitle` | mutation | Patches `title` by `sessionId` |
| `deleteSession` | mutation | Deletes by `sessionId` |

## Convex Functions — `convex/workspaces.ts`

| Export | Type | Description |
|--------|------|-------------|
| `listWorkspaces` | query | Returns up to `limit` workspaces ordered by `createdAt` desc |
| `getWorkspace` | query | Returns one workspace by `workspaceId` |
| `createWorkspace` | mutation | Inserts with empty `cells[]`; returns `{workspaceId}` |
| `updateCells` | mutation | Replaces full `cells` array by `workspaceId` |
| `updateTitle` | mutation | Patches `title` by `workspaceId` |
| `deleteWorkspace` | mutation | Deletes by `workspaceId` |

## lib/api.ts — FastAPI Fetch Client

Base URL: `process.env.NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`).

All non-streaming functions throw `Error("API {status}: {body}")` on non-2xx responses.

### Types

```typescript
OntologyClass   = { name: string; instanceCount: number }
EntitySummary   = { id, iri, class, properties: Record<string, unknown> }
EntityDetail    = EntitySummary & { relationships: {property, targetId, targetName}[] }
GraphData       = { nodes: {id, label, group, properties}[]; links: {source, target, label}[] }
SeriesPoint     = { date: string; value: number }
AnalysisPlugin  = { slug, name, description }
AnalysisResult  = { title, sections: AnalysisSection[] }
AnalysisSection = metrics | table | chart | text | divider | group
SqlResult       = { columns: string[]; rows: Record<string, unknown>[]; rowCount: number; sql?: string; explanation?: string }
ExecuteResult   = { stdout: string; stderr: string; dataframes: Record<string, {columns, rows, rowCount}>; figures: string[]; error: string | null }
AgentEvent      = text_delta | tool_call | tool_result | done | error
ModelInfo       = { id: string; label: string }
```

### Namespaces

**`ontology`**: `classes()`, `instances(cls, page, limit, search)`, `entity(uri)`, `entityGraph(uri)`, `graph(types[], stateFips?, limit)`, `search(q, types?)`, `series()`, `seriesData(id)`

**`analysis`**: `plugins()`, `run(slug, config?)`

**`configs`**: `validate(config_type, content)` → `{valid, errors}`

**`jobs`**: `trigger(pipeline_slug)` → `{jobId, status}`

**`sql`**: `query(query)`, `translate(question, model?)`, `schema()`, `tables()`

**`execute`**: `run(code, timeout?)` → `ExecuteResult`

**`agent`**: `models()`, `chat(message, history?, model?)` → `AsyncGenerator<AgentEvent>`, `inferSchema(sample?, description?, model?)`

`agent.chat` uses `fetch` + `ReadableStream` to consume the SSE endpoint via POST (EventSource is GET-only). Parses `data: {...}` lines from the stream and yields typed `AgentEvent` objects.

## Pages

### `/workspace` — `app/(dashboard)/workspace/page.tsx`

Streaming AI research workspace. Chat-first interface with tool transparency.

- Header: model selector (populated from `GET /agent/models`) and "New" session button.
- Empty state: four example research prompts as clickable buttons.
- Message list: user bubbles (right-aligned) and assistant bubbles (left-aligned with bot icon).
- Tool call cards: collapsible per-tool card showing input args and result. SQL/table results rendered as scrollable tables. Python results show stdout, DataFrames, and base64 figures.
- Streaming: text arrives via `text_delta` events; cursor blinks while `streaming: true`.
- Conversation `history` maintained in a `useRef` and passed on each request.
- Input: textarea (Enter = send, Shift+Enter = newline), disabled while loading.

### `/sql` — `app/(dashboard)/sql/page.tsx`

Interactive SQL editor backed by DuckDB.

- NL→SQL bar: plain-English question → calls `sql.translate()`, populates the SQL editor with the generated query and shows the result.
- Example query buttons: "All states", "Top counties by population", "Measures with values", "Municipality count by state".
- SQL editor: `<textarea>` with monospace font; Cmd+Enter / Ctrl+Enter runs query.
- Schema panel: collapsible, shows table names and column names/types from `sql.schema()`.
- Results table: sticky header, alternating rows, truncated cells, row count footer.

### `/explorer` — `app/(dashboard)/explorer/page.tsx`

- Fetches class list on mount via `ontology.classes()`.
- Renders a tab per class; active tab fetches instances with `ontology.instances(cls, page, limit, search)`.
- Search input triggers re-fetch with `search` param.
- Pagination: prev/next buttons; shows `page / ceil(total/limit)`.
- Entity cards show `id`, `class`, and all `properties` entries as key/value pills.
- Clicking an entity navigates to `/explorer/{id}`.

### `/graph` — `app/(dashboard)/graph/page.tsx`

- Sidebar: checkbox group for `types` filter (State, County, Municipality, Individual); state FIPS selector.
- Calls `ontology.graph(types, stateFips, limit=500)`.
- Renders graph with `react-force-graph-2d` (dynamic import, SSR disabled).
- Node color determined by `group` (class name): State = `#58a6ff`, County = `#3fb950`, Municipality = `#e3b341`, Individual = `#bc8cff`, default = `#8b949e`.

### `/analysis` — `app/(dashboard)/analysis/page.tsx`

- Fetches plugin list via `analysis.plugins()` on mount.
- Plugin selector renders one card per plugin with name and description.
- "Run" button calls `analysis.run(slug)` and displays result sections:
  - `metrics`: grid of `{label, value}` cards.
  - `table`: scrollable table with `columns` header row and `data` rows.
  - `chart`: `recharts` `LineChart` (x/y specified in section).
  - `text`: rendered as `<p>`.
  - `divider`: `<hr>`.
  - `group`: titled section wrapping nested sections.

### `/jobs` — `app/(dashboard)/jobs/page.tsx`

- `useQuery(api.jobs.list, { limit: 50 })` — reactive; updates in real time as Convex pushes changes.
- Table columns: Pipeline (monospace slug), Status (colored badge), Steps (done/total), Started (relative time via `timeAgo()`).
- Status badge colors: queued/cancelled = `#8b949e`, running = `#58a6ff`, success = `#3fb950`, failed = `#f85149`.

### `/configs` — `app/(dashboard)/configs/page.tsx`

- Three tabs: "API Sources", "Ontologies", "Pipelines".
- Each tab uses `useQuery(api.configs.listApis/listOntologies/listPipelines)` — reactive.
- YAML editor panel: inline Monaco-style editor with live validation, slug auto-generation, public/private toggle, delete with confirmation.

### `/pipelines` — `app/(dashboard)/pipelines/page.tsx`

- Uses `useQuery(api.configs.listPipelines)` — reactive.
- Pipeline cards show name, slug, referenced API count, tags.
- "Run" button calls `jobs.trigger(pipeline_slug)` then navigates to `/jobs`.

## New and Updated Pages

### `/projects` — Project Gallery

Card grid of all projects. Each card: project name, description, status badge (`draft`/`ready`/`hydrated`), last hydration timestamp, entity count, GitHub repo link, "Open" button. Filter bar: status filter chips, search by name. "New Project" button opens a creation modal (name, slug, GitHub repo, ontology template picker).

### `/registry` — Shared Registry

Two tabs: **Connectors** and **Ontology Templates**. Each tab is a searchable card gallery with tag filter chips. Cards show name, description, version, usage count ("used by N projects"), and a "Use" / "Apply" button. Clicking a card opens a detail panel with the full YAML content and an edit button.

### `/[project]/overview` — Project Dashboard

Four metric cards: total entities, OWL classes, last hydration time, active jobs. Below: mini job history table (last 5 runs), class breakdown bar chart (entity count per class), recent agent sessions list with timestamps and first message preview.

### `/[project]/ontology/classes` — Class Browser

Left panel: class tree with instance counts. Expandable hierarchy (GeographicRegion → State → County → ...). Clicking a class loads the right panel: paginated entity table with search input. Column headers auto-derived from the class's data properties. Clicking any row slides in `EntityDetailPanel` from the right showing all properties and relationships. URL updates to `/[project]/ontology/classes/[class]` and `/[project]/ontology/classes/[class]/[entityId]` for deep linking.

### `/[project]/sources` — Data Sources

Split layout. Left: project's API source configs as cards (name, connector template badge if using `extends`, last fetched date). "New Source" button opens YAML editor pre-filled with template selector. Right: connector template gallery — browse shared connectors and click "Use Template" to fork one into the project.

### `/[project]/agent` — Domain Agent

Left panel (collapsible): session list — all past conversations for this project, ordered by recency, with auto-generated titles. Main area:
- Empty state: `ContextSnapshot` card ("In this project I have access to: 5 classes · 48,600 entities · 3 pipelines · 12 analysis plugins") + 4 example research prompt buttons.
- Active conversation: `AgentChat` with streaming text, `ToolCallCard` components for each tool call (collapsible, shows args + result inline), model selector in the header.

### `/[project]/settings` — Project Settings

Three sections:
1. **Manifest** — read-only view of `rail.yaml` with an "Edit" button that opens the YAML editor. Changes are committed to GitHub via `POST /api/v1/github/publish`.
2. **GitHub Sync** — last sync timestamp, last commit SHA, in-sync status badge. "Force Sync" button triggers `POST /api/v1/github/sync` manually. "Re-link Repo" for changing the GitHub repo.
3. **Danger Zone** — delete project (with confirmation modal).

## Top Bar — `components/layout/TopBar.tsx`

Always visible. Contains:
- Platform name / logo (links to `/projects`)
- `ProjectSwitcher` dropdown — lists all projects with status badges; click to navigate to `/{slug}/overview`. Includes "All Projects" option linking to `/projects`.
- Active project name (breadcrumb)
- "New Project" button (platform level only, hidden inside a project)

## Sidebar — `components/layout/Sidebar.tsx`

Project-scoped. Only visible when inside a `[project]` route. Navigation links:

| Label | Route |
|-------|-------|
| Overview | `/[project]/overview` |
| Ontology | `/[project]/ontology/classes` |
| Sources | `/[project]/sources` |
| Pipelines | `/[project]/pipelines` |
| SQL | `/[project]/sql` |
| Agent | `/[project]/agent` |
| Analysis | `/[project]/analysis` |
| Jobs | `/[project]/jobs` |
| ──── | |
| Registry | `/registry` |
| Settings | `/[project]/settings` |

Active link highlighted via `usePathname()`. Dark/light theme toggle at bottom.

## Theme

Dark GitHub-style: CSS custom properties set in `app/layout.tsx` global styles.

| Variable | Value |
|----------|-------|
| `--background` | `#0d1117` |
| `--foreground` | `#e6edf3` |
| `--muted` | `#161b22` |
| `--muted-foreground` | `#8b949e` |
| `--border` | `#30363d` |
| `--primary` | `#58a6ff` |
| `--primary-foreground` | `#0d1117` |
