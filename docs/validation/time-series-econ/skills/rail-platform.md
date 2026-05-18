# RAIL Platform

Use this skill whenever the project requires data queries, analysis, hydration, or integrity checks.

This project is backed by the RAIL platform. Prefer RAIL MCP tools over manual scripting when working with project data.

## Adding the MCP server

### Option 1 — Local install (stdio)

Install once:

```bash
pip install -e packages/mcp-server   # from monorepo
# or: pip install rail-mcp           # from PyPI when published
```

Add to the project `.mcp.json` (or `~/.claude/claude_desktop_config.json` for Claude Desktop):

```json
{
  "mcpServers": {
    "rail": {
      "command": "rail-mcp",
      "env": {
        "RAIL_PROJECT": "your-project-slug",
        "RAIL_API_URL": "http://localhost:8000/api/v1"
      }
    }
  }
}
```

For a local repo checkout instead of a running API:

```json
{
  "mcpServers": {
    "rail": {
      "command": "rail-mcp",
      "args": ["--local", "--path", "/path/to/project"],
      "env": {}
    }
  }
}
```

### Option 2 — Remote URL (SSE / streamable-http)

When RAIL is deployed as a hosted service, the MCP server can run in HTTP mode:

```bash
rail-mcp --transport sse --host 0.0.0.0 --port 8001 --project your-slug
# or for the newer transport:
rail-mcp --transport streamable-http --port 8001 --project your-slug
```

Agents then connect by URL — no local install needed:

```json
{
  "mcpServers": {
    "rail": {
      "url": "http://your-rail-host:8001/sse"
    }
  }
}
```

For streamable-http:

```json
{
  "mcpServers": {
    "rail": {
      "url": "http://your-rail-host:8001/mcp"
    }
  }
}
```

## Available tools

| Tool | When to use |
|---|---|
| `list_classes` | First step — discover entity types in the ontology |
| `get_entities(class_name, limit)` | Browse instances of a class |
| `search_entities(query)` | Full-text search across all entities |
| `get_series(series_id)` | Fetch a named time-series |
| `query_sql(sql)` | DuckDB SQL against the artifact database |
| `execute_python(code)` | Run analysis; sandbox has pandas, statsmodels, duckdb |
| `run_analysis(plugin_slug)` | Run a registered analysis plugin |
| `search_registry(query)` | Find available datasets in the data catalog |
| `discover_templates(query)` | Find connector templates to add new data sources |
| `hydrate(pipeline_slug)` | Refresh project data from upstream sources |
| `integrity_status` | Full integrity report before publishing |
| `integrity_assumptions` | Check recorded assumptions |
| `integrity_sources` | List evidence sources |
| `integrity_claims` | List empirical claims and their evidence |
| `integrity_rerun_plan` | See what needs re-running after an assumption changes |
| `list_secrets` | Check which API keys are configured |
| `set_secret(key, value)` | Store a new API key |

## Typical workflow

```
1. list_classes                    → discover what data exists
2. get_entities("ClassName")       → inspect a sample
3. query_sql("SELECT ...")         → explore or aggregate
4. integrity_status()              → verify data quality before analysis
5. execute_python("import ...")    → run analysis in the sandbox
6. search_registry("...")          → find additional datasets if needed
7. hydrate()                       → refresh data when sources update
```
