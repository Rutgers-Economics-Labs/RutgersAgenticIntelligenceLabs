# Data Source Registry

The **data source registry** is a searchable catalog of known public data series available on the RAIL platform. It is distinct from connector templates — where connector templates provide inheritable YAML configuration boilerplate, the registry is a discovery layer that tells researchers what data exists, where it comes from, and how to use it.

---

## Purpose

When a researcher wants to add new data to a project, they face two questions:
1. What data is available that's relevant to my topic?
2. How do I configure it?

The registry answers question 1. It is the "app store" of known datasets — browsable, searchable, tagged by provider, geography, and topic. Each entry links to an `exampleYaml` that shows how to configure it as a project API config (optionally using a connector template via `extends`).

The registry does not run pipelines or fetch data itself — it is purely a catalog.

---

## Convex Table — `dataSourceRegistry`

| Field | Type | Notes |
|-------|------|-------|
| `provider` | string | Source organization: `"fred"`, `"census"`, `"bls"`, `"bea"`, `"worldbank"`, `"oecd"`, etc. Indexed `by_provider`. |
| `sourceId` | string | Provider-specific identifier (e.g. FRED series ID `"NJURN"`, Census table `"B23025"`). Indexed `by_provider_source` (unique). |
| `name` | string | Human-readable name: `"NJ Unemployment Rate"` |
| `description` | string | One-sentence description of what this series measures |
| `unit` | string | Units of measure: `"%"`, `"$"`, `"index"`, `"persons"`, etc. |
| `frequency` | string | `"monthly"`, `"quarterly"`, `"annual"`, `"decennial"` |
| `geography` | string | Geographic coverage: `"US"`, `"state"`, `"county"`, `"New Jersey"`, etc. |
| `tags` | string[] | Topic tags: `["labor", "unemployment", "NJ"]` |
| `exampleYaml` | string | A ready-to-use YAML config string (may use `extends: fred-observations`) |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## API Routes — `/api/v1/registry`

Router: `packages/api/app/routers/registry.py`

| Method | Path | Params / Body | Returns |
|--------|------|--------------|---------|
| GET | `/search` | `q?`, `provider?`, `geography?`, `limit` (default 20, max 100) | list of matching registry entries |
| GET | `/{provider}/{source_id}` | — | single registry entry or 404 |
| POST | `` | `{provider, id, name, description, unit, frequency, geography, tags?, exampleYaml}` | created entry |

### Search Behavior

`GET /search` performs case-insensitive substring matching across `name`, `description`, `provider`, `geography`, and `tags`. Filters:
- `provider` — exact match on the `provider` field
- `geography` — substring match on the `geography` field
- `q` — matches any of: name, description, sourceId, tags

Results are returned in order of relevance (tag + name matches ranked higher than description matches).

---

## Registry Service — `app/services/registry_service.py`

```python
async def search_registry_entries(
    query_text: str,
    provider: str | None = None,
    geography: str | None = None,
    limit: int = 20,
) -> list[dict]
    # Queries Convex dataSourceRegistry with filters and full-text matching

async def get_registry_entry(provider: str, source_id: str) -> dict | None
    # Returns a single entry by provider + sourceId

async def create_registry_entry(data: dict) -> dict
    # Creates a new entry in Convex
```

---

## Relationship to Connector Templates

Registry entries and connector templates complement each other:

| | Registry Entry | Connector Template |
|--|---------------|-------------------|
| What it is | Metadata about a specific dataset/series | Reusable YAML config boilerplate |
| Stored as | Structured fields (name, unit, geography, tags) | Raw YAML string |
| Used for | Discovery — "what data exists?" | Configuration — "how do I fetch it?" |
| `exampleYaml` | Points to a connector template via `extends` | Is the template |

A registry entry's `exampleYaml` typically looks like:

```yaml
extends: fred-observations       # uses the fred connector template
name: nj_unemployment
params:
  series_id: NJURN
  observation_start: "2000-01-01"
```

This tells a researcher exactly what to put in their `configs/apis/` directory. When connected to the platform, the "Use" button on a registry entry creates this config directly in the project.

---

## Agent Integration

Both the **project setup agent** (`/project-agent`) and the **Q&A agent** (`/questions`) use the registry via the `search_data_registry` tool:

```json
{
  "name": "search_data_registry",
  "args": {
    "query": "unemployment rate",
    "provider": "fred",
    "geography": "New Jersey",
    "limit": 10
  }
}
```

The agent uses registry results to suggest data sources to add to a project and to explain what data is available when a Q&A question cannot be answered with existing project data.

---

## Frontend — `/registry`

The registry page at `/registry` (platform-level, accessible from all projects) provides a searchable interface for the catalog.

**Current implementation:** Shows `dataSourceRegistry` entries with provider badges, geography chips, description, unit, frequency, and the example YAML in an expandable code block.

**Planned extension (per `specs/connectors.md`):** The registry page will be expanded into two tabs — **Data Catalog** (registry entries, current) and **Connector Templates** (YAML templates, new). The two concepts will be surfaced together but remain distinct: the data catalog helps you find data, the connector templates help you configure it.

---

## Initial Registry Content

The registry is seeded via `scripts/seed_convex.py` on first deploy. Initial entries include:

| Provider | Source ID | Name | Geography | Frequency |
|----------|-----------|------|-----------|-----------|
| fred | NJURN | NJ Unemployment Rate | New Jersey | monthly |
| fred | UNRATE | US Unemployment Rate | US | monthly |
| fred | STHPI | House Price Index (state) | state | quarterly |
| fred | MEHOINUS*A646N | Median Household Income | state | annual |
| census | B23025 | Employment Status (ACS5) | county | annual |
| census | B01003 | Total Population (ACS5) | county/tract | annual |
| census | B19013 | Median Household Income (ACS5) | county | annual |
| bls | LAU | Local Area Unemployment Statistics | county | monthly |
| worldbank | NY.GDP.MKTP.CD | GDP (current USD) | country | annual |
| worldbank | SL.UEM.TOTL.ZS | Unemployment, total (% labor force) | country | annual |
