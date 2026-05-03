# RAIL Platform — Agent Guide

RAIL (Rutgers Agentic Intelligence Labs) is a research platform for building structured, reproducible
economic and policy research. It organizes data as an **ontology** (typed entities + time-series),
runs **hydration pipelines** to populate it from external sources, and maintains a **research
integrity ledger** that tracks assumptions, sources, and empirical claims.

---

## Connecting to a project

### Cloud mode (API)

```python
import rail

project = rail.connect(
    slug="nj-housing-analysis",          # project slug
    api_url="http://localhost:8000/api/v1",  # RAIL_API_URL env var
    api_key="sk-...",                    # RAIL_API_KEY env var (optional locally)
)
```

### Local mode (from repo checkout)

```python
project = rail.local(path=".")          # reads rail.yaml in current dir
```

### Environment variables

| Variable | Description |
|---|---|
| `RAIL_PROJECT` | Project slug (cloud mode) |
| `RAIL_API_URL` | API base URL (default: `http://localhost:8000/api/v1`) |
| `RAIL_API_KEY` | Bearer token |
| `RAIL_LOCAL` | Set to `"1"` to load from disk instead of API |
| `RAIL_PATH` | Local project path (default: `.`) |

---

## MCP Server (recommended for agents)

The MCP server exposes all platform capabilities as first-class tools. Any MCP-compatible
agent (Claude Code, Claude Desktop, Cursor, etc.) can use it without writing HTTP calls.

### Install

```bash
pip install -e packages/mcp-server
```

### Run (stdio transport)

```bash
RAIL_PROJECT=nj-housing-analysis RAIL_API_URL=http://localhost:8000/api/v1 rail-mcp
```

For local mode:

```bash
RAIL_LOCAL=1 RAIL_PATH=/path/to/project rail-mcp
```

### Add to Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "rail": {
      "command": "rail-mcp",
      "env": {
        "RAIL_PROJECT": "nj-housing-analysis",
        "RAIL_API_URL": "http://localhost:8000/api/v1"
      }
    }
  }
}
```

### Add to Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "rail": {
      "command": "rail-mcp",
      "env": {
        "RAIL_PROJECT": "nj-housing-analysis",
        "RAIL_API_URL": "http://localhost:8000/api/v1"
      }
    }
  }
}
```

---

## Available MCP tools

### Ontology / knowledge graph

| Tool | Description |
|---|---|
| `list_classes` | List all typed entity classes in the project (County, Indicator, Policy, …) |
| `get_entities(class_name, limit)` | Fetch up to N instances of a class |
| `search_entities(query)` | Full-text search across all entities |
| `get_series(series_id)` | Fetch a named time-series as (date, value) rows |

### Querying

| Tool | Description |
|---|---|
| `query_sql(sql)` | Run DuckDB SQL against the artifact database. Tables = ontology class names (snake_case). |

### Code execution

| Tool | Description |
|---|---|
| `execute_python(code, timeout)` | Run Python in the project sandbox. Returns stdout, dataframes, figures. Sandbox has pandas, numpy, matplotlib, statsmodels, and a pre-connected `db` DuckDB handle. |

### Data catalog

| Tool | Description |
|---|---|
| `search_registry(query, provider, geography)` | Search available datasets (BLS, Census, FRED, …) |
| `discover_templates(query, tags)` | Find connector templates that can be added to the project |

### Pipelines

| Tool | Description |
|---|---|
| `hydrate(pipeline_slug)` | Trigger a data hydration pipeline. Omit slug to run the default. |

### Research integrity

| Tool | Description |
|---|---|
| `integrity_status` | Full integrity report: assumptions, sources, claims |
| `integrity_assumptions` | List recorded assumptions and their verification status |
| `integrity_sources` | List evidence sources cited in the project |
| `integrity_claims` | List empirical claims and their supporting evidence |
| `integrity_rerun_plan(assumption_key, apply)` | Preview or apply rerun tasks triggered by an assumption change |

### Secrets

| Tool | Description |
|---|---|
| `list_secrets` | List secret key names (values never returned) |
| `set_secret(key, value)` | Store an API key in the project vault |

---

## Direct HTTP API

All tools map to REST endpoints at `RAIL_API_URL` (`/api/v1` by default).

```
GET  /ontology/classes
GET  /ontology/classes/{class}/instances?limit=N
GET  /ontology/search?q=...
GET  /ontology/series/{series_id}/data
POST /sql                              {"query": "SELECT ..."}
POST /execute                          {"code": "...", "timeout": 60}
POST /analysis/plugins/{slug}/run      {"config": {...}}
GET  /registry/search?query=...
GET  /connectors/templates?query=...
POST /jobs                             {"pipeline_slug": "..."}
GET  /projects/{slug}/integrity
GET  /projects/{slug}/integrity/assumptions
GET  /projects/{slug}/integrity/sources
GET  /projects/{slug}/integrity/claims
POST /projects/{slug}/integrity/rerun-plan        {"assumptionKey": "..."}
POST /projects/{slug}/integrity/rerun-plan/apply  {"assumptionKey": "..."}
GET  /projects/{slug}/settings/secrets
POST /projects/{slug}/settings/secrets            {"keyName": "...", "plaintextValue": "..."}
```

---

## rail CLI (quick reference)

```bash
# Query
rail --project nj-housing query sql "SELECT * FROM county LIMIT 5"
rail --project nj-housing query classes
rail --project nj-housing query entities County --limit 10
rail --project nj-housing series unemployment_rate_nj_2010_2024

# Search
rail --project nj-housing search "housing price index" --type registry
rail --project nj-housing search "census income" --type templates

# Pipelines
rail --project nj-housing hydrate --pipeline census-acs

# Integrity
rail --project nj-housing integrity status
rail --project nj-housing integrity rerun vintage_year --apply

# Secrets
rail --project nj-housing secrets list
rail --project nj-housing secrets set FRED_API_KEY abc123
```

In local mode, replace `--project nj-housing` with `--local` (or just `cd` into a project
directory that contains `rail.yaml`).

---

## Typical agent workflow

```
1. list_classes                           → understand what data exists
2. get_entities("County", limit=5)        → inspect a sample
3. query_sql("SELECT ...")                → explore relationships
4. integrity_status()                     → check data quality before analysis
5. execute_python("import pandas ...")    → run statistical analysis
6. search_registry("unemployment NJ")    → find additional data sources
7. hydrate()                              → refresh data if needed
```
