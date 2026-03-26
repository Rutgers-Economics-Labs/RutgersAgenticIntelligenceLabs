"""
DuckDB SQL service for RAIL.

After a hydration job completes, the ontology is exported to a DuckDB file.
Each OWL class becomes a table; data properties become columns.

Callers can then:
  - run arbitrary SQL
  - get schema info
  - translate natural language → SQL via the LLM
"""
from pathlib import Path
from typing import Optional

import duckdb

_duckdb_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Path management
# ---------------------------------------------------------------------------

def get_path() -> Optional[Path]:
    return _duckdb_path


def set_path(path: str | Path) -> None:
    global _duckdb_path
    _duckdb_path = Path(path)


def is_ready(path: str | Path | None = None) -> bool:
    p = Path(path) if path is not None else _duckdb_path
    return p is not None and p.exists()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _connect(*, read_only: bool = True, path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    p = Path(path) if path is not None else _duckdb_path
    if p is None or not p.exists():
        raise RuntimeError("No DuckDB database loaded. Run a hydration pipeline first.")
    return duckdb.connect(str(p), read_only=read_only)


def run_query(sql: str, *, duckdb_path: str | Path | None = None) -> dict:
    """Execute SQL and return {columns, rows, rowCount}."""
    con = _connect(path=duckdb_path)
    try:
        result = con.execute(sql)
        columns = [d[0] for d in result.description] if result.description else []
        rows = result.fetchall()
        # Serialize to JSON-safe dicts
        data = []
        for row in rows:
            rec = {}
            for col, val in zip(columns, row):
                # Convert non-JSON-serialisable types
                if hasattr(val, "isoformat"):
                    rec[col] = val.isoformat()
                else:
                    rec[col] = val
            data.append(rec)
        return {"columns": columns, "rows": data, "rowCount": len(data)}
    finally:
        con.close()


def list_tables(*, duckdb_path: str | Path | None = None) -> list[str]:
    if not is_ready(duckdb_path):
        return []
    con = duckdb.connect(str(Path(duckdb_path) if duckdb_path is not None else _duckdb_path), read_only=True)
    try:
        return [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    finally:
        con.close()


def get_schema(*, duckdb_path: str | Path | None = None) -> dict:
    """Return {table_name: [{name, type}, ...]} for all tables."""
    if not is_ready(duckdb_path):
        return {}
    con = duckdb.connect(str(Path(duckdb_path) if duckdb_path is not None else _duckdb_path), read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        schema: dict[str, list[dict]] = {}
        for t in tables:
            cols = con.execute(f'DESCRIBE "{t}"').fetchall()
            schema[t] = [{"name": c[0], "type": c[1]} for c in cols]
        return schema
    finally:
        con.close()


def get_schema_ddl(*, duckdb_path: str | Path | None = None) -> str:
    """Return CREATE TABLE statements as a string — useful for LLM prompts."""
    schema = get_schema(duckdb_path=duckdb_path)
    lines = []
    for table, cols in schema.items():
        col_defs = ", ".join(f'"{c["name"]}" {c["type"]}' for c in cols)
        lines.append(f'CREATE TABLE "{table}" ({col_defs});')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# NL → SQL translation
# ---------------------------------------------------------------------------

async def translate_to_sql(
    natural_language: str,
    model: str | None = None,
    *,
    duckdb_path: str | Path | None = None,
) -> dict:
    """
    Use the LLM to translate a natural-language question into SQL.
    Returns {sql, explanation}.
    """
    from app.services import llm_service

    schema_ddl = get_schema_ddl(duckdb_path=duckdb_path)
    if not schema_ddl:
        raise RuntimeError("No schema available. Run a hydration pipeline first.")

    system = (
        "You are a SQL expert. Given a DuckDB schema and a question, write a single SQL query.\n"
        "Rules:\n"
        "- Output ONLY valid DuckDB SQL, nothing else, no markdown fences.\n"
        "- Use double-quotes for identifiers with special characters.\n"
        "- Limit results to 500 rows unless the user asks for more.\n"
        "- After the SQL query, add a blank line then a one-sentence explanation prefixed with '-- '."
    )
    prompt = f"Schema:\n{schema_ddl}\n\nQuestion: {natural_language}"

    response = await llm_service.complete(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        model=model,
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()

    # Split SQL from explanation comment
    parts = raw.split("\n-- ", 1)
    sql = parts[0].strip()
    explanation = parts[1].strip() if len(parts) > 1 else ""
    return {"sql": sql, "explanation": explanation}
