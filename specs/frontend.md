# Frontend

The frontend is a Next.js 15 App Router application in `packages/web/`. It has two data sources:
- **Convex** (`convex/react` `useQuery`) — real-time config tables and job status.
- **FastAPI** (`lib/api.ts` typed fetch client) — ontology data and analysis results.

## Directory Layout

```
packages/web/
  app/
    layout.tsx                  Root layout — sets up ConvexProvider and dark theme
    convex-provider.tsx         "use client" wrapper around ConvexProvider
    page.tsx                    Root redirect → /explorer
    (dashboard)/
      layout.tsx                Dashboard shell with Sidebar
      explorer/page.tsx         Paginated entity browser
      graph/page.tsx            Force-directed graph
      analysis/page.tsx         Plugin runner
      jobs/page.tsx             Hydration job list
      configs/page.tsx          Config library (3 tabs: APIs, Ontologies, Pipelines)
      pipelines/page.tsx        Pipeline cards with "Run" button
  components/
    layout/
      Sidebar.tsx               Left-nav sidebar
  convex/
    schema.ts                   Convex table definitions
    configs.ts                  Convex query/mutation functions for config tables
    jobs.ts                     Convex query/mutation functions for job tables
    _generated/                 Auto-generated Convex types (not edited manually)
  lib/
    api.ts                      Typed fetch client for FastAPI
  public/                       Static assets
  .env.local                    NEXT_PUBLIC_CONVEX_URL, NEXT_PUBLIC_API_URL
```

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

## lib/api.ts — FastAPI Fetch Client

Base URL: `process.env.NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`).

All functions throw `Error("API {status}: {body}")` on non-2xx responses.

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
```

### Namespaces

**`ontology`**: `classes()`, `instances(cls, page, limit, search)`, `entity(uri)`, `entityGraph(uri)`, `graph(types[], stateFips?, limit)`, `search(q, types?)`, `series()`, `seriesData(id)`

**`analysis`**: `plugins()`, `run(slug, config?)`

**`configs`**: `validate(config_type, content)` → `{valid, errors}`

**`jobs`**: `trigger(pipeline_slug)` → `{jobId, status}`

## Pages

### `/explorer` — `app/(dashboard)/explorer/page.tsx`

- Fetches class list on mount via `ontology.classes()`.
- Renders a tab per class; active tab fetches instances with `ontology.instances(cls, page, limit, search)`.
- Search input triggers re-fetch with `search` param.
- Pagination: prev/next buttons; shows `page / ceil(total/limit)`.
- Entity cards show `id`, `class`, and all `properties` entries as key/value pills.
- Clicking an entity navigates to `/explorer/{id}` (detail view not yet implemented as a separate route; currently fetches `ontology.entity(id)` inline).

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
- "View →" link to `/jobs/{_id}` (detail page not yet implemented).

### `/configs` — `app/(dashboard)/configs/page.tsx`

- Three tabs: "API Sources", "Ontologies", "Pipelines".
- Each tab uses `useQuery(api.configs.listApis/listOntologies/listPipelines)` — reactive.
- Cards show name, slug, source type (APIs), tags, `isPublic` badge, `createdAt`.
- "Validate" button opens a modal with a YAML textarea; calls `configs.validate()` and shows errors inline.

### `/pipelines` — `app/(dashboard)/pipelines/page.tsx`

- Uses `useQuery(api.configs.listPipelines)` — reactive.
- Pipeline cards show name, slug, referenced API count, tags.
- "Run" button calls `jobs.trigger(pipeline_slug)` then navigates to `/jobs`.

## Sidebar — `components/layout/Sidebar.tsx`

Navigation links:

| Label | Route |
|-------|-------|
| Dashboard | `/` |
| Explorer | `/explorer` |
| Graph | `/graph` |
| Analysis | `/analysis` |
| Data Sources | `/configs` |
| Pipelines | `/pipelines` |
| Jobs | `/jobs` |

Active link highlighted via `usePathname()`.

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
