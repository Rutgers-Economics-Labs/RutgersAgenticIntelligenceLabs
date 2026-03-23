"""SqlClient — wraps the RAIL /sql endpoints, returning pandas DataFrames."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from .client import RailClient


class SqlClient:
    def __init__(self, client: "RailClient") -> None:
        self._c = client

    def _result_to_df(self, result: dict) -> "pd.DataFrame":
        import pandas as pd
        rows = result.get("rows", [])
        if not rows:
            return pd.DataFrame(columns=result.get("columns", []))
        return pd.DataFrame(rows)

    def query(self, sql: str) -> "pd.DataFrame":
        """Execute a SQL query and return results as a DataFrame."""
        result = self._c._post("/sql", {"query": sql})
        return self._result_to_df(result)

    def schema(self) -> dict:
        """Return the DuckDB schema: {table: [{name, type}]}."""
        return self._c._get("/sql/schema")

    def tables(self) -> list[str]:
        """List available DuckDB table names."""
        return self._c._get("/sql/tables")

    def translate(self, question: str) -> tuple["pd.DataFrame", str]:
        """
        Translate a natural-language question to SQL and execute it.
        Returns (DataFrame, generated_sql_string).
        """
        result = self._c._post("/sql/translate", {"question": question})
        df = self._result_to_df(result)
        return df, result.get("sql", "")
