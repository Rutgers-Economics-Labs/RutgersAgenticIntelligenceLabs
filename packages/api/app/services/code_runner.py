"""
Python code execution sandbox for RAIL.

Executes researcher-supplied Python code in an isolated namespace with:
  - `sql(query)` → run SQL via DuckDB, returns a DataFrame
  - `get_table(name)` → fetch an entire OWL class as a DataFrame
  - `list_tables()` → list available tables
  - Full data science stack: pandas, numpy, statsmodels, sklearn, matplotlib

Captures stdout, DataFrames (any variable ending in _df or named `result`),
and matplotlib figures (saved as base64 PNG).

Security note: this is single-user; inproc mode uses namespace isolation only.
Use RAIL_EXECUTE_MODE=subprocess (and optionally RAIL_EXECUTE_DOCKER_IMAGE) for a child process.
"""
import asyncio
import base64
import contextlib
import io
import traceback
from typing import Any

import pandas as pd

from app.core.config import settings


def _execute_disabled() -> dict[str, Any]:
    return {
        "stdout": "",
        "stderr": "",
        "dataframes": {},
        "figures": [],
        "error": "Python execution is disabled (RAIL_EXECUTE_ENABLED=false).",
    }


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context() -> dict[str, Any]:
    """Build the execution namespace available to user code."""
    from app.services import sql_service

    def sql(query: str) -> pd.DataFrame:
        result = sql_service.run_query(query)
        return pd.DataFrame(result["rows"], columns=result["columns"])

    def get_table(name: str) -> pd.DataFrame:
        return sql(f'SELECT * FROM "{name}"')

    def list_tables() -> list[str]:
        return sql_service.list_tables()

    ctx: dict[str, Any] = {
        "sql": sql,
        "get_table": get_table,
        "list_tables": list_tables,
        "pd": pd,
    }

    # Optional heavy imports — only add if available
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
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
        ctx["plt"] = plt
        ctx["matplotlib"] = matplotlib
    except ImportError:
        pass

    return ctx


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _run_inproc(code: str, timeout_seconds: int) -> dict[str, Any]:
    import concurrent.futures

    def _execute() -> dict:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        namespace = _build_context()
        error: str | None = None

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                exec(compile(code, "<rail_sandbox>", "exec"), namespace)  # noqa: S102
            except Exception:
                error = traceback.format_exc()

        stdout = stdout_buf.getvalue()
        stderr = stderr_buf.getvalue()

        # Collect DataFrames
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

        # Collect matplotlib figures
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

        return {
            "stdout": stdout,
            "stderr": stderr,
            "dataframes": dataframes,
            "figures": figures,
            "error": error,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_execute)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            return {
                "stdout": "",
                "stderr": "",
                "dataframes": {},
                "figures": [],
                "error": f"Execution timed out after {timeout_seconds}s",
            }


def run_code(code: str, timeout_seconds: int = 60) -> dict:
    """
    Execute `code` (sync). Prefer `run_code_async` from async HTTP handlers.

    Returns:
        {
            "stdout": str,
            "stderr": str,
            "dataframes": {name: {columns, rows}},
            "figures": [base64_png_str, ...],
            "error": str | None,
        }
    """
    if not settings.execute_python_enabled:
        return _execute_disabled()
    if settings.execute_python_mode == "subprocess":
        from app.services import subprocess_code_runner

        return asyncio.run(
            subprocess_code_runner.run_user_code(code, timeout_seconds, upload_artifacts=False)
        )
    return _run_inproc(code, timeout_seconds)


async def run_code_async(code: str, timeout_seconds: int = 60) -> dict:
    """Async entrypoint for /execute and agent tools."""
    if not settings.execute_python_enabled:
        return _execute_disabled()
    if settings.execute_python_mode == "subprocess":
        from app.services import subprocess_code_runner

        return await subprocess_code_runner.run_user_code(
            code, timeout_seconds, upload_artifacts=False
        )
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _run_inproc(code, timeout_seconds))
