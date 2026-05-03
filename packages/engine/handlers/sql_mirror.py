"""
Source handler for SQL databases (Postgres, SQLite, Snowflake, DuckDB, etc.).
Uses SQLAlchemy connection strings so any dialect works.

YAML config shape:
    type: sql_mirror
    name: employment_data
    connection_string: "${DB_URL}"      # env var substitution works
    query: "SELECT * FROM qcew WHERE year = 2023"
    # or
    table: qcew_2023                    # reads entire table
    fields: [...]                       # optional column mapping
"""
import pandas as pd


def fetch(spec: dict, **kwargs) -> pd.DataFrame:
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        raise ImportError(
            "sqlalchemy is required for sql_mirror sources: pip install sqlalchemy"
        )

    conn_str = spec.get("connection_string")
    if not conn_str:
        raise ValueError("sql_mirror requires connection_string")

    engine = create_engine(conn_str)

    if "query" in spec:
        sql = spec["query"]
    elif "table" in spec:
        sql = f"SELECT * FROM {spec['table']}"
    else:
        raise ValueError("sql_mirror requires either query or table")

    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    return df
