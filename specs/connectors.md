# Connectors

A **connector template** is a reusable, parameterized data source definition stored in the Convex `connectorTemplates` table. It captures the boilerplate for connecting to a data provider — authentication patterns, URL structure, response format, pagination, and canonical field conventions — so project-level configs only specify what is unique to their request (series IDs, geographic filters, date ranges).

Connector templates are shared across all projects. Any platform user can create, edit, or fork a template. No deployment is required to add a new template.

---

## Connector vs. API Config

| | Connector Template | Project API Config |
|--|-------------------|--------------------|
| Scope | Platform-wide, shared | Project-scoped |
| Stored in | Convex `connectorTemplates` | Convex `apiConfigs` + GitHub repo |
| Who edits | Any platform user | Project team |
| Purpose | Boilerplate for a data provider | Specific data request |
| `extends` | — | References a connector by slug |

A project API config that uses `extends` is a **connector instance** — it inherits the template and overrides only the fields specific to the data it requests.

---

## Template YAML Structure

Connector templates use the same YAML structure as project API configs (see `specs/yaml-config.md`) plus a small set of metadata fields at the top:

```yaml
# Connector template — stored as `content` string in Convex connectorTemplates table
slug: fred-observations
name: FRED Series Observations
description: "Fetch observations for any FRED series via the St. Louis Fed API"
version: "1.1"
tags: [economics, time-series, fred, federal-reserve]
---
# Below is the actual connector YAML (the `content` field):
name: fred_base                          # overridden by project config
type: api
url: "https://api.stlouisfed.org/fred/series/observations"
params:
  api_key: "${FRED_API_KEY}"
  file_type: json
  observation_start: "2000-01-01"        # default; project can override
response_format: json
response_path: observations
fields:
  - source: date
    alias: date
  - source: value
    alias: value
    cast: float
```

### Metadata Fields (top of template, before `---`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | string | yes | Unique identifier, indexed in Convex |
| `name` | string | yes | Display name in the connector gallery |
| `description` | string | yes | One-sentence description of the data provider |
| `version` | string | yes | Semver. Increment on breaking changes. |
| `tags` | string[] | no | For filtering in the UI (`economics`, `census`, `real-time`, etc.) |

---

## Connector Resolution (`extends`)

When a project API config declares `extends: <connector-slug>`, the hydration worker resolves it before writing YAMLs to the tmpdir:

### Resolution Rules

1. Fetch the connector template from Convex by slug.
2. Parse both the template YAML and the project config YAML.
3. **Deep merge** — project config fields override template fields at every level:
   - Scalar fields: project wins.
   - `params` maps: merged key-by-key, project keys override template keys, non-conflicting keys from both are kept.
   - `fields` lists: project list **replaces** template list entirely if present; if absent, template list is used. Use `fields_append` to add fields without replacing.
   - `foreach`: project wins entirely if present.
4. Remove the `extends` key from the merged result.
5. Write the fully resolved YAML to the tmpdir `configs/apis/` directory.

The engine receives a standard API config YAML with no `extends` field. Connector resolution is invisible to the engine.

### Example

```yaml
# Connector template: fred-observations (simplified)
name: fred_base
type: api
url: "https://api.stlouisfed.org/fred/series/observations"
params:
  api_key: "${FRED_API_KEY}"
  file_type: json
response_format: json
response_path: observations
fields:
  - source: date
    alias: date
  - source: value
    alias: value
    cast: float

# Project config: nj_unemployment.yaml
extends: fred-observations
name: nj_unemployment
params:
  series_id: NJURN
  observation_start: "2010-01-01"
  frequency: m
fields_append:
  - source: realtime_start
    alias: realtime_start

# Resolved YAML (what the engine sees):
name: nj_unemployment
type: api
url: "https://api.stlouisfed.org/fred/series/observations"
params:
  api_key: "${FRED_API_KEY}"
  file_type: json
  series_id: NJURN
  observation_start: "2010-01-01"
  frequency: m
response_format: json
response_path: observations
fields:
  - source: date
    alias: date
  - source: value
    alias: value
    cast: float
  - source: realtime_start
    alias: realtime_start
```

---

## Connector Types

Connectors inherit the engine's `type` field — only `type: api`, `type: csv`, and `type: excel` are supported now. New connector types that require engine code changes (e.g., GraphQL, S3, database connections) are added via PR to the platform repo. The YAML-level connector template system handles any data source expressible in the existing type system without a deploy.

### Planned Connector Types (future engine additions)

| Type | Description | Notes |
|------|-------------|-------|
| `graphql` | GraphQL endpoint with query template | Requires response flattening conventions |
| `s3` | S3 bucket or prefix | Supports CSV/JSON/Parquet via DuckDB |
| `sql` | Direct database query (Postgres, SQLite) | Via SQLAlchemy |
| `websocket` | Live WebSocket feed | Incremental hydration mode only |
| `unstructured` | Document/PDF ingestion | See `specs/improvements.md` §5 |

---

## Convex Schema — `connectorTemplates`

| Field | Type | Notes |
|-------|------|-------|
| `slug` | string | Unique, indexed `by_slug` |
| `name` | string | Display name |
| `description` | string | |
| `version` | string | Semver |
| `tags` | string[] | For gallery filtering |
| `content` | string | Full YAML including metadata header and connector body |
| `usageCount` | number | How many active project configs reference this template (denormalized, updated on create/delete of apiConfigs) |
| `createdBy` | string | Platform user identifier |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## Available Connector Templates (Initial Set)

The following templates are seeded into Convex on first deploy via `scripts/seed_convex.py`.

### Economics & Finance

| Slug | Provider | What it fetches |
|------|----------|----------------|
| `fred-observations` | Federal Reserve (FRED) | Time series observations for any series ID |
| `fred-series-search` | Federal Reserve (FRED) | Search FRED series catalog by keyword |
| `census-acs5` | US Census Bureau | American Community Survey 5-year estimates (any table) |
| `census-decennial` | US Census Bureau | Decennial census summary tables |
| `census-population` | US Census Bureau | Annual population estimates by geography |
| `bls-series` | Bureau of Labor Statistics | Any BLS series (CPS, CES, JOLTS, etc.) |
| `bea-nipa` | Bureau of Economic Analysis | NIPA tables (GDP, income, expenditures) |
| `bea-regional` | Bureau of Economic Analysis | Regional economic accounts |
| `world-bank-indicator` | World Bank | Any World Development Indicator |
| `oecd-dataset` | OECD.Stat | Any OECD dataset via SDMX |

### Geography & Demographics

| Slug | Provider | What it fetches |
|------|----------|----------------|
| `census-tigerweb-states` | Census TIGER/Web | State geometries and FIPS codes |
| `census-tigerweb-counties` | Census TIGER/Web | County geometries and FIPS codes |
| `census-tigerweb-places` | Census TIGER/Web | Incorporated places (municipalities) |
| `census-tigerweb-tracts` | Census TIGER/Web | Census tracts |
| `hud-crosswalk` | HUD | ZIP→Tract→County→CBSA crosswalk |

### Files

| Slug | Type | What it handles |
|------|------|----------------|
| `local-csv` | csv | Local CSV file with standard field mapping |
| `local-excel` | excel | Local Excel file with sheet selection |

---

## Adding a New Connector

Any platform user can add a connector via the platform UI (Registry → Connectors → New):

1. Enter the metadata fields (name, slug, description, tags).
2. Write or paste the connector YAML body in the editor.
3. Click "Validate" — calls `POST /api/v1/configs/validate` with `config_type: "api"`.
4. Click "Save" — creates a new `connectorTemplates` record in Convex.
5. The connector is immediately available to all projects.

To add a connector that requires a new `type` (new engine code):
1. Add the type handler to `packages/engine/engine/api_runner.py`.
2. Add validation rules for the new type to `packages/api/app/services/yaml_service.py`.
3. PR to the platform repo.
4. After merge and deploy, create the connector template via the UI as normal.

---

## Connector Versioning

When a connector template is updated (breaking change), increment `version`. Existing project configs that `extends` this connector continue to resolve against the version that was current when the project last hydrated — the resolved YAML is written to tmpdir at hydration time, so the engine always sees the current merged result.

**Version pinning** — project API configs can optionally pin to a connector version:
```yaml
extends: fred-observations@1.0    # pin to version 1.0
```

If no version is pinned, the project always uses the latest connector template.

---

## Connector as a Platform Object

Each connector template that is instantiated in a project becomes a `DataSource` individual in that project's ontology (via the `platform-objects` template). The `DataSource` individual has:
- `hasName` — the project config's `name` field
- `hasSlug` — the api config slug
- `hasConnectorTemplate` — the connector template slug
- `hasSourceURL` — the resolved URL (with env vars substituted, sensitive params redacted)
- `hasProjectSlug` — the project slug

This means the agent can query `SELECT * FROM DataSource` to discover what data sources exist in the current project, and `hasConnectorTemplate` links back to the shared registry.
