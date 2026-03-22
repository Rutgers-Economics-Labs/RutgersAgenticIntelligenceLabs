# Work Order 14 — Data Source Registry

## Layer
2 — Ingestion Expansion

## Goal
Build a searchable catalog of known public data sources (Census variables, FRED series, World Bank indicators, BLS codes) that the AI agent can query instead of hallucinating API endpoints.

## Background
The agent's biggest failure mode when asked to fetch new data is inventing plausible-sounding but wrong API endpoints or series IDs. A structured registry gives the agent a ground-truth lookup so it can find real, working data sources.

## Steps

### 1. Define the registry schema
New Convex table: `dataSourceRegistry`

| Field | Type | Description |
|-------|------|-------------|
| `provider` | string | "census", "fred", "worldbank", "bls", "custom" |
| `id` | string | Provider-specific ID (e.g. FRED series "UNRATE", Census variable "B01003_001E") |
| `name` | string | Human-readable name ("Unemployment Rate") |
| `description` | string | One-sentence description |
| `unit` | string | "percent", "dollars", "persons", etc. |
| `frequency` | string | "annual", "monthly", "quarterly" |
| `geography` | string | "national", "state", "county", "msa" |
| `tags` | string[] | Searchable tags |
| `exampleYaml` | string | A minimal working API config YAML snippet |
| `updatedAt` | number | |

Indexes: `by_provider`, full-text search on `name` + `description` + `tags`.

### 2. Seed the registry
New script: `scripts/seed_registry.py`

Pre-populate with:
- ~50 FRED series (unemployment, housing, GDP, CPI, interest rates by state/national)
- ~20 Census ACS variables (population, income, education, poverty by geography)
- ~10 World Bank indicators (GDP per capita, population, trade)
- ~10 BLS series (CPI, PPI, employment by sector)

Each entry includes a working `exampleYaml` snippet that can be copy-pasted into a config.

### 3. Registry search API endpoint
File: `packages/api/app/routers/registry.py` — **create**

```
GET /api/v1/registry/search?q=...&provider=...&geography=...&limit=20
Returns: [{provider, id, name, description, unit, frequency, geography, tags, exampleYaml}]

GET /api/v1/registry/{provider}/{id}
Returns: full registry entry

POST /api/v1/registry
Body: registry entry object
Returns: created entry (for adding custom sources)
```

### 4. Add `search_data_registry` tool to agent
File: `packages/api/app/services/agent_service.py`

New tool:
```python
{
  "name": "search_data_registry",
  "description": "Search the catalog of known data sources by topic, geography, or provider. Use this before creating an API config to find the correct series ID or endpoint.",
  "parameters": {
    "query": "string",
    "provider": "string (optional: census, fred, worldbank, bls)",
    "geography": "string (optional: national, state, county)"
  }
}
```

Tool implementation calls `GET /api/v1/registry/search`.

### 5. Registry browser UI page
New page: `packages/web/app/(dashboard)/registry/page.tsx`

- Search bar with provider filter tabs (All / FRED / Census / World Bank / BLS)
- Results grid: name, provider badge, geography, frequency, description
- Clicking an entry shows the `exampleYaml` snippet with a "Use this" button that opens the Configs editor pre-filled

### 6. "Use this source" flow
When researcher clicks "Use this" on a registry entry:
- Open the Config editor (from WO-06 modal) pre-filled with `exampleYaml`
- Researcher edits name/slug and saves

### 7. Add registry link to Sidebar
Add "Registry" nav item between "Data Sources" and "Pipelines".

### 8. Registry auto-update (stretch goal, optional)
A background task that periodically checks FRED's `series/search` API and adds new series that match high-value keywords (unemployment, GDP, housing). Flag for later implementation.

## New Convex Functions — `convex/registry.ts`
- `search(query, provider?, geography?, limit?)` — query
- `get(provider, id)` — query
- `create(entry)` — mutation
- `list(limit?)` — query

## Affected Files
- `packages/web/convex/schema.ts` — add `dataSourceRegistry` table
- `packages/web/convex/registry.ts` — **create**
- `packages/api/app/routers/registry.py` — **create**
- `packages/api/app/main.py` — register registry router
- `packages/api/app/services/agent_service.py` — add `search_data_registry` tool
- `packages/web/app/(dashboard)/registry/page.tsx` — **create**
- `packages/web/components/layout/Sidebar.tsx` — add Registry link
- `packages/web/lib/api.ts` — add `registry` namespace
- `scripts/seed_registry.py` — **create**

## Acceptance Criteria
- [ ] Registry seeded with ≥50 FRED + ≥20 Census entries
- [ ] `GET /registry/search?q=unemployment&geography=state` returns relevant FRED series
- [ ] Agent uses `search_data_registry` before creating configs for new data requests
- [ ] Registry browser page shows searchable results with working "Use this" flow
- [ ] Custom entries can be added via the API
