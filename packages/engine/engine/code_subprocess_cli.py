"""
Run user Python in an isolated OS process (invoked by the API).

Environment:
  RAIL_DUCKDB_PATH   — path to DuckDB file (read-only)
  RAIL_OUTPUT_DIR    — directory where user code may write artifacts (models, CSV, PNG, …)
  RAIL_MANIFEST_PATH — JSON file written with stdout/stderr/error/dataframes/figures

CLI args: path to a .py file to execute.

The execution namespace matches code_runner (sql, get_table, list_tables, pd, OUTPUT_DIR, …).
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import sys
import traceback
from pathlib import Path


def _build_namespace(db_path: str, output_dir: str) -> dict:
    import pandas as pd
    import duckdb

    def sql(query: str) -> pd.DataFrame:
        con = duckdb.connect(db_path, read_only=True)
        try:
            result = con.execute(query)
            cols = [d[0] for d in result.description] if result.description else []
            rows = result.fetchall()
            return pd.DataFrame(rows, columns=cols)
        finally:
            con.close()

    def get_table(name: str) -> pd.DataFrame:
        return sql(f'SELECT * FROM "{name}"')

    def list_tables() -> list[str]:
        con = duckdb.connect(db_path, read_only=True)
        try:
            return [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        finally:
            con.close()

    ctx: dict = {
        "sql": sql,
        "get_table": get_table,
        "list_tables": list_tables,
        "pd": pd,
        "OUTPUT_DIR": output_dir,
    }

    try:
        import numpy as np

        ctx["np"] = np
    except ImportError:
        pass

    try:
        import statsmodels.formula.api as smf
        import statsmodels.api as sm

        ctx["smf"] = smf
        ctx["sm"] = sm
    except ImportError:
        pass

    try:
        import sklearn

        ctx["sklearn"] = sklearn
    except ImportError:
        pass

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ctx["plt"] = plt
        ctx["matplotlib"] = matplotlib
    except ImportError:
        pass

    try:
        import folium

        ctx["folium"] = folium
    except ImportError:
        pass

    try:
        import geopandas as gpd

        ctx["gpd"] = gpd
        ctx["geopandas"] = gpd
    except ImportError:
        pass

    return ctx


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: code_subprocess_cli.py <user_script.py>", file=sys.stderr)
        sys.exit(2)

    user_path = Path(sys.argv[1])
    db_path = os.environ.get("RAIL_DUCKDB_PATH", "")
    manifest_path = Path(os.environ.get("RAIL_MANIFEST_PATH", "_rail_manifest.json"))
    output_dir = Path(os.environ.get("RAIL_OUTPUT_DIR", "."))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not db_path or not Path(db_path).is_file():
        manifest_path.write_text(
            json.dumps(
                {
                    "stdout": "",
                    "stderr": "",
                    "dataframes": {},
                    "figures": [],
                    "error": f"DuckDB not available at RAIL_DUCKDB_PATH={db_path!r}",
                }
            ),
            encoding="utf-8",
        )
        sys.exit(1)

    namespace = _build_namespace(db_path, str(output_dir.resolve()))
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    error: str | None = None

    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            code = user_path.read_text(encoding="utf-8")
            exec(compile(code, "<user_code>", "exec"), namespace)  # noqa: S102
        except Exception:
            error = traceback.format_exc()

    import pandas as pd

    dataframes: dict[str, dict] = {}
    for name, val in namespace.items():
        if name.startswith("_"):
            continue
        if isinstance(val, pd.DataFrame):
            try:
                dataframes[name] = {
                    "columns": list(val.columns),
                    "rows": val.head(500).to_dict(orient="records"),
                    "rowCount": len(val),
                }
            except Exception:
                pass

    figures: list[str] = []
    try:
        import matplotlib.pyplot as plt

        for fig_num in plt.get_fignums():
            fig = plt.figure(fig_num)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
            buf.seek(0)
            figures.append(base64.b64encode(buf.read()).decode())
        plt.close("all")
    except Exception:
        pass

    manifest = {
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "dataframes": dataframes,
        "figures": figures,
        "error": error,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    sys.exit(0 if error is None else 1)


if __name__ == "__main__":
    main()
