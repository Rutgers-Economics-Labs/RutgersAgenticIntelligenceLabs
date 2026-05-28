"""
Data quality analysis for RAIL ontology DuckDB databases.

Endpoints:
  GET  /quality/report   — per-table row counts, null rates, distinct counts, freshness
  POST /quality/snapshot — save current counts to Convex (for diff tracking)
  GET  /quality/diff     — compare the last two snapshots
"""

import time
from typing import Any

import duckdb
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import sql_service, project_artifacts_service

router = APIRouter(prefix="/quality", tags=["quality"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_db_path(project_id: str | None) -> str | None:
    """Return the DuckDB path for a project (or the globally-loaded one)."""
    if project_id:
        try:
            artifacts = await project_artifacts_service.resolve(project_id)
            if artifacts.duckdb_path:
                return artifacts.duckdb_path
        except Exception:
            try:
                proj = await convex.query("projects:getById", {"projectId": project_id})
            except Exception:
                proj = None
            if not proj:
                try:
                    proj = await convex.query("projects:get", {"slug": project_id})
                except Exception:
                    proj = None
            if proj and proj.get("activeOntologyDuckdbPath"):
                return proj["activeOntologyDuckdbPath"]
    # Fall back to globally-loaded path
    p = sql_service.get_path()
    return str(p) if p else None


def _analyze_table(con: duckdb.DuckDBPyConnection, table: str) -> dict:
    """Return quality metrics for one table."""
    # Row count
    row_count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    # Column-level stats
    col_rows = con.execute(f'DESCRIBE "{table}"').fetchall()
    columns = []
    for col_row in col_rows:
        col_name = col_row[0]
        col_type = col_row[1]
        try:
            stats = con.execute(
                f'SELECT '
                f'  COUNT(*) AS total, '
                f'  COUNT("{col_name}") AS non_null, '
                f'  COUNT(DISTINCT "{col_name}") AS distinct_count '
                f'FROM "{table}"'
            ).fetchone()
            total, non_null, distinct_count = stats
            null_count = total - non_null
            null_rate = round(null_count / total, 4) if total > 0 else 0.0

            # Try min/max for numeric/date columns
            min_val = max_val = None
            if any(t in col_type.upper() for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "DATE", "TIMESTAMP", "BIGINT")):
                try:
                    mm = con.execute(f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM "{table}"').fetchone()
                    min_val = str(mm[0]) if mm[0] is not None else None
                    max_val = str(mm[1]) if mm[1] is not None else None
                except Exception:
                    pass

            columns.append({
                "name": col_name,
                "type": col_type,
                "nullCount": null_count,
                "nullRate": null_rate,
                "distinctCount": distinct_count,
                "min": min_val,
                "max": max_val,
            })
        except Exception as e:
            columns.append({"name": col_name, "type": col_type, "error": str(e)})

    # Freshness: look for createdAt / updatedAt / date columns
    freshness = None
    for ts_col in ("createdAt", "updatedAt", "created_at", "updated_at", "date", "year"):
        if any(c["name"].lower() == ts_col.lower() for c in columns):
            try:
                val = con.execute(f'SELECT MAX("{ts_col}") FROM "{table}"').fetchone()[0]
                if val is not None:
                    freshness = {"column": ts_col, "maxValue": str(val)}
                    break
            except Exception:
                pass

    return {
        "table": table,
        "rowCount": row_count,
        "columns": columns,
        "freshness": freshness,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/report")
async def get_quality_report(project_id: str | None = None):
    """Run quality checks against the project's DuckDB and return metrics."""
    db_path = await _resolve_db_path(project_id)
    if not db_path or not sql_service.is_ready(db_path):
        return {"error": "No database loaded for this project", "tables": []}

    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        table_reports = [_analyze_table(con, t) for t in tables]
    finally:
        con.close()

    total_rows = sum(t["rowCount"] for t in table_reports)
    total_nulls = sum(
        sum(c.get("nullCount", 0) for c in t["columns"])
        for t in table_reports
    )
    total_cells = sum(
        t["rowCount"] * len(t["columns"])
        for t in table_reports
    )
    overall_null_rate = round(total_nulls / total_cells, 4) if total_cells > 0 else 0.0

    return {
        "projectId": project_id,
        "dbPath": db_path,
        "generatedAt": int(time.time() * 1000),
        "summary": {
            "tableCount": len(table_reports),
            "totalRows": total_rows,
            "overallNullRate": overall_null_rate,
        },
        "tables": table_reports,
    }


class SnapshotRequest(BaseModel):
    project_id: str | None = None
    label: str | None = None  # e.g. "post-hydration job #42"


@router.post("/snapshot")
async def save_snapshot(req: SnapshotRequest):
    """Save current entity counts to Convex for diff tracking."""
    db_path = await _resolve_db_path(req.project_id)
    if not db_path or not sql_service.is_ready(db_path):
        return {"error": "No database loaded for this project"}

    con = duckdb.connect(db_path, read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        counts: dict[str, Any] = {}
        for t in tables:
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            # Column-level null rates for drift detection
            col_rows = con.execute(f'DESCRIBE "{t}"').fetchall()
            col_stats = {}
            for cr in col_rows:
                col = cr[0]
                try:
                    stats = con.execute(
                        f'SELECT COUNT(*) AS total, COUNT("{col}") AS non_null FROM "{t}"'
                    ).fetchone()
                    total, non_null = stats
                    col_stats[col] = {
                        "nullRate": round((total - non_null) / total, 4) if total > 0 else 0.0,
                        "distinctCount": con.execute(f'SELECT COUNT(DISTINCT "{col}") FROM "{t}"').fetchone()[0],
                    }
                except Exception:
                    pass
            counts[t] = {"rowCount": n, "columns": col_stats}
    finally:
        con.close()

    now = int(time.time() * 1000)
    payload: dict = {
        "tables": counts,
        "label": req.label or f"Snapshot {now}",
        "createdAt": now,
    }
    if req.project_id:
        payload["projectSlug"] = req.project_id

    snapshot_id = await convex.mutation("quality:saveSnapshot", payload)
    return {"snapshotId": snapshot_id, "tableCount": len(counts), "createdAt": now}


@router.get("/diff")
async def get_diff(project_id: str | None = None):
    """Compare the two most recent snapshots and return changes."""
    params: dict = {}
    if project_id:
        # The Convex query expects 'projectSlug'
        params["projectSlug"] = project_id

    snapshots = await convex.query("quality:listSnapshots", {**params, "limit": 2})
    if not snapshots or not isinstance(snapshots, list) or len(snapshots) < 2:
        return {
            "hasDiff": False,
            "message": "Need at least 2 snapshots to compare. Take a snapshot before and after hydration.",
            "snapshots": len(snapshots) if snapshots and isinstance(snapshots, list) else 0,
        }

    newer, older = snapshots[0], snapshots[1]
    new_tables: dict = newer.get("tables", {})
    old_tables: dict = older.get("tables", {})

    all_tables = set(new_tables.keys()) | set(old_tables.keys())
    table_diffs = []

    for table in sorted(all_tables):
        new_data = new_tables.get(table)
        old_data = old_tables.get(table)

        if old_data is None:
            table_diffs.append({"table": table, "status": "added", "newCount": new_data["rowCount"], "oldCount": 0, "delta": new_data["rowCount"], "columnDiffs": []})
            continue
        if new_data is None:
            table_diffs.append({"table": table, "status": "removed", "newCount": 0, "oldCount": old_data["rowCount"], "delta": -old_data["rowCount"], "columnDiffs": []})
            continue

        new_count = new_data["rowCount"]
        old_count = old_data["rowCount"]
        delta = new_count - old_count
        status = "unchanged" if delta == 0 else ("grew" if delta > 0 else "shrank")

        # Column-level drift
        new_cols: dict = new_data.get("columns", {})
        old_cols: dict = old_data.get("columns", {})
        all_cols = set(new_cols.keys()) | set(old_cols.keys())
        col_diffs = []
        for col in sorted(all_cols):
            nc = new_cols.get(col)
            oc = old_cols.get(col)
            if nc is None:
                col_diffs.append({"column": col, "status": "removed"})
            elif oc is None:
                col_diffs.append({"column": col, "status": "added", "newNullRate": nc["nullRate"]})
            else:
                null_drift = round(nc["nullRate"] - oc["nullRate"], 4)
                distinct_delta = nc["distinctCount"] - oc["distinctCount"]
                if abs(null_drift) > 0.01 or abs(distinct_delta) > 0:
                    col_diffs.append({
                        "column": col,
                        "status": "changed",
                        "nullRateDrift": null_drift,
                        "distinctDelta": distinct_delta,
                        "newNullRate": nc["nullRate"],
                        "oldNullRate": oc["nullRate"],
                    })

        table_diffs.append({
            "table": table,
            "status": status,
            "newCount": new_count,
            "oldCount": old_count,
            "delta": delta,
            "columnDiffs": col_diffs,
        })

    return {
        "hasDiff": True,
        "newer": {"label": newer.get("label"), "createdAt": newer.get("createdAt")},
        "older": {"label": older.get("label"), "createdAt": older.get("createdAt")},
        "summary": {
            "tablesAdded": sum(1 for t in table_diffs if t["status"] == "added"),
            "tablesRemoved": sum(1 for t in table_diffs if t["status"] == "removed"),
            "tablesGrew": sum(1 for t in table_diffs if t["status"] == "grew"),
            "tablesShrank": sum(1 for t in table_diffs if t["status"] == "shrank"),
            "tablesUnchanged": sum(1 for t in table_diffs if t["status"] == "unchanged"),
        },
        "tables": table_diffs,
    }
