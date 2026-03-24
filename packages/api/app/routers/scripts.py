"""
Script run endpoints — execute a saved project script and persist the results.

POST /scripts/{script_id}/runs   — run code, save figures, create run record
GET  /scripts/{script_id}/runs   — list runs from Convex
GET  /scripts/runs/{run_id}/figures/{index} — download a saved figure
"""
import base64
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.config import settings
from app.services import code_runner
from app.services.convex_client import convex
from app.services.storage_service import storage

router = APIRouter(prefix="/scripts", tags=["scripts"])


class RunRequest(BaseModel):
    project_id: str
    code: str
    timeout: int = 120


@router.post("/{script_id}/runs")
async def create_run(script_id: str, req: RunRequest):
    """Execute code for a saved script, persist figures + stdout to storage, return results."""
    if req.timeout > 300:
        raise HTTPException(status_code=400, detail="Timeout cannot exceed 300s")
    if not settings.execute_python_enabled:
        raise HTTPException(
            status_code=403,
            detail="Python execution is disabled (RAIL_EXECUTE_ENABLED=false).",
        )

    # Create run record in Convex
    run_id: str = await convex.mutation("scriptRuns:create", {
        "scriptId": script_id,
        "projectId": req.project_id,
        "codeSnapshot": req.code,
    })

    # Execute
    result = await code_runner.run_code_async(req.code, timeout_seconds=req.timeout)

    # Save figures to storage
    figure_storage_keys: list[str] = []
    for i, fig_b64 in enumerate(result.get("figures") or []):
        try:
            fig_bytes = base64.b64decode(fig_b64)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(fig_bytes)
                tmp_path = Path(tmp.name)
            key = await storage.upload(run_id, f"figure_{i}.png", tmp_path)
            figure_storage_keys.append(key)
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[scripts] Could not save figure {i} for run {run_id}: {e}")

    # Build lightweight dataframe summary (column names + row counts, no rows)
    df_summary = None
    if result.get("dataframes"):
        df_summary = {
            name: {"columns": df["columns"], "rowCount": df["rowCount"]}
            for name, df in result["dataframes"].items()
        }

    status = "failed" if result.get("error") else "success"
    stdout = (result.get("stdout") or "")[:65_000]  # cap at ~64KB

    await convex.mutation("scriptRuns:complete", {
        "runId": run_id,
        "status": status,
        "stdout": stdout or None,
        "error": result.get("error") or None,
        "figureCount": len(figure_storage_keys),
        "figureStorageKeys": figure_storage_keys,
        "dfSummary": df_summary,
        "finishedAt": __import__("time").time() * 1000,
    })

    return {
        "runId": run_id,
        "result": result,
        "figureStorageKeys": figure_storage_keys,
    }


@router.get("/{script_id}/runs")
async def list_runs(script_id: str, limit: int = 20):
    """List run records for a script from Convex."""
    rows = await convex.query("scriptRuns:listByScript", {
        "scriptId": script_id,
        "limit": limit,
    })
    return rows or []


@router.get("/runs/{run_id}/figures/{index}")
async def get_figure(run_id: str, index: int):
    """Download a saved figure from storage."""
    run = await convex.query("scriptRuns:get", {"runId": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    keys: list[str] = run.get("figureStorageKeys") or []
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=404, detail="Figure index out of range")
    key = keys[index]
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await storage.download(key, tmp_path)
        data = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
    return Response(content=data, media_type="image/png")
