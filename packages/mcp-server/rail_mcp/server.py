"""
RAIL MCP Server — exposes the RAIL platform as MCP tools for AI agents.

Configuration via environment variables:
  RAIL_PROJECT   Project slug (required unless --local)
  RAIL_API_URL   API base URL (default: http://localhost:8000/api/v1)
  RAIL_API_KEY   Bearer token (optional for local deployments)
  RAIL_LOCAL     Set to "1" to load the project from the current directory
  RAIL_PATH      Local project path (default: ".", only used when RAIL_LOCAL=1)
"""

import json
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

import rail

mcp = FastMCP("RAIL Platform")

# ---------------------------------------------------------------------------
# Lazy project singleton — resolved on first tool call
# ---------------------------------------------------------------------------

_project: rail.Project | None = None


def _get_project() -> rail.Project:
    global _project
    if _project is not None:
        return _project

    if os.environ.get("RAIL_LOCAL", "") == "1":
        path = os.environ.get("RAIL_PATH", ".")
        _project = rail.local(path=path)
    else:
        slug = os.environ.get("RAIL_PROJECT")
        if not slug:
            raise RuntimeError(
                "RAIL_PROJECT env var is required. "
                "Set it to your project slug or set RAIL_LOCAL=1 to load from disk."
            )
        _project = rail.connect(
            slug=slug,
            api_url=os.environ.get("RAIL_API_URL"),
            api_key=os.environ.get("RAIL_API_KEY"),
        )

    return _project


def _json(data: Any) -> str:
    if hasattr(data, "to_dict"):
        return json.dumps(data.to_dict(orient="records"), indent=2)
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Ontology / knowledge graph tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_classes() -> str:
    """List all ontology classes defined in the project (e.g. County, Indicator, Policy)."""
    return _json(_get_project().classes())


@mcp.tool()
def get_entities(class_name: str, limit: int = 20) -> str:
    """
    Return up to `limit` instances of an ontology class.

    Args:
        class_name: Exact class name from list_classes (e.g. "County").
        limit: Max rows to return (default 20, max 500).
    """
    limit = min(limit, 500)
    df = _get_project().entities(class_name, limit=limit)
    return _json(df)


@mcp.tool()
def search_entities(query: str) -> str:
    """
    Full-text search across all ontology entities.

    Args:
        query: Search term (e.g. "Middlesex County unemployment").
    """
    return _json(_get_project().search(query))


@mcp.tool()
def get_series(series_id: str) -> str:
    """
    Fetch a named time-series as a table of (date, value) rows.

    Args:
        series_id: Series identifier (e.g. "unemployment_rate_nj_2010_2024").
    """
    df = _get_project().series(series_id)
    return _json(df)


# ---------------------------------------------------------------------------
# SQL query tool
# ---------------------------------------------------------------------------


@mcp.tool()
def query_sql(sql: str) -> str:
    """
    Run a DuckDB SQL query against the project's artifact database.

    Use list_classes / get_entities first to discover available tables.
    Tables are named after ontology classes (snake_case), e.g. SELECT * FROM county LIMIT 5.

    Args:
        sql: A valid DuckDB SQL statement.
    """
    df = _get_project().query(sql)
    return _json(df)


# ---------------------------------------------------------------------------
# Python execution
# ---------------------------------------------------------------------------


@mcp.tool()
def execute_python(code: str, timeout: int = 60) -> str:
    """
    Execute arbitrary Python code in the project's sandbox and return stdout,
    stderr, any returned dataframes, and figures.

    The sandbox has access to pandas, numpy, matplotlib, statsmodels, and
    a pre-connected DuckDB database via the `db` variable.

    Args:
        code: Python source code to execute.
        timeout: Max seconds before the sandbox kills the process (default 60).
    """
    result = _get_project().execute(code, timeout=timeout)
    return _json(result)


# ---------------------------------------------------------------------------
# Analysis plugins
# ---------------------------------------------------------------------------


@mcp.tool()
def run_analysis(plugin_slug: str, **kwargs) -> str:
    """
    Run a named analysis plugin registered in the project.

    Args:
        plugin_slug: Plugin identifier (e.g. "regression", "correlation_matrix").
        **kwargs: Plugin-specific configuration options passed as keyword args.
    """
    result = _get_project().run_analysis(plugin_slug, **kwargs)
    return _json(result)


# ---------------------------------------------------------------------------
# Data catalog / registry
# ---------------------------------------------------------------------------


@mcp.tool()
def search_registry(query: str, provider: str = "", geography: str = "") -> str:
    """
    Search the platform's data catalog for available datasets.

    Args:
        query: What you're looking for (e.g. "NJ unemployment 2020").
        provider: Optional filter, e.g. "BLS", "Census", "FRED".
        geography: Optional filter, e.g. "NJ", "county", "national".
    """
    return _json(_get_project().search_registry(
        query,
        provider=provider or None,
        geography=geography or None,
    ))


@mcp.tool()
def discover_templates(query: str, tags: str = "") -> str:
    """
    Search for connector templates (Census, FRED, BLS, etc.) that can be added to the project.

    Args:
        query: What kind of data you need (e.g. "housing price index").
        tags: Comma-separated tags to filter by (e.g. "economic,nj").
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    return _json(_get_project().discover(query, tags=tag_list))


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


@mcp.tool()
def hydrate(pipeline_slug: str = "") -> str:
    """
    Trigger a hydration pipeline to refresh the project's data.

    Args:
        pipeline_slug: Pipeline to run. Leave empty to use the project's default pipeline.
    """
    result = _get_project().hydrate(pipeline_slug=pipeline_slug or None)
    return _json(result)


# ---------------------------------------------------------------------------
# Research integrity
# ---------------------------------------------------------------------------


@mcp.tool()
def integrity_status() -> str:
    """Return the overall research integrity report: assumptions, sources, claims, and their verification status."""
    return _json(_get_project().integrity_status())


@mcp.tool()
def integrity_assumptions() -> str:
    """List all recorded research assumptions and whether they have been verified."""
    return _json(_get_project().integrity_assumptions())


@mcp.tool()
def integrity_sources() -> str:
    """List all evidence sources cited in the project."""
    return _json(_get_project().integrity_sources())


@mcp.tool()
def integrity_claims() -> str:
    """List all empirical claims and their supporting evidence."""
    return _json(_get_project().integrity_claims())


@mcp.tool()
def integrity_rerun_plan(assumption_key: str, apply: bool = False) -> str:
    """
    Preview or apply the rerun plan triggered by an assumption change.

    When an assumption changes (e.g. a new data vintage), this identifies which
    downstream pipelines and analyses need to be re-executed.

    Args:
        assumption_key: The assumption that changed (from integrity_assumptions).
        apply: If True, create the actual rerun tasks. Default False (preview only).
    """
    if apply:
        result = _get_project().apply_integrity_rerun_plan(assumption_key)
    else:
        result = _get_project().integrity_rerun_plan(assumption_key)
    return _json(result)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


@mcp.tool()
def list_secrets() -> str:
    """List secret key names configured for this project (values are never returned)."""
    return _json(_get_project().list_secrets())


@mcp.tool()
def set_secret(key: str, value: str) -> str:
    """
    Store an API key or credential in the project's secrets vault.

    Args:
        key: Secret name, e.g. "FRED_API_KEY".
        value: Plaintext secret value.
    """
    return _json(_get_project().set_secret(key, value))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="rail-mcp", description="RAIL MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio). Use 'sse' or 'streamable-http' for URL-based remote access.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host for sse/streamable-http (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port for sse/streamable-http (default: 8001)")
    parser.add_argument("--project", help="Override RAIL_PROJECT env var")
    parser.add_argument("--api-url", help="Override RAIL_API_URL env var")
    parser.add_argument("--api-key", help="Override RAIL_API_KEY env var")
    parser.add_argument("--local", action="store_true", help="Load project from disk (sets RAIL_LOCAL=1)")
    parser.add_argument("--path", default=".", help="Local project path (default: .)")
    args = parser.parse_args()

    if args.project:
        os.environ["RAIL_PROJECT"] = args.project
    if args.api_url:
        os.environ["RAIL_API_URL"] = args.api_url
    if args.api_key:
        os.environ["RAIL_API_KEY"] = args.api_key
    if args.local:
        os.environ["RAIL_LOCAL"] = "1"
        os.environ["RAIL_PATH"] = args.path

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    elif args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
