import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import project_artifacts_service, sql_service, ontology_service
from app.services.convex_client import convex
from app.services.execution_manager import execution_manager

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _get_runner():
    """Import analysis_runner from the engine package, adding it to sys.path if needed."""
    engine_root = str(settings.engine_root)
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)
    from engine.analysis_runner import discover, run
    return discover, run


def _serialize_section(sec: dict) -> dict:
    """Convert a section dict to JSON-safe form (DataFrames → list[dict])."""
    import pandas as pd
    result = {k: v for k, v in sec.items() if k != "data"}
    if "data" in sec and isinstance(sec["data"], pd.DataFrame):
        result["data"] = sec["data"].to_dict(orient="records")
        result["columns"] = list(sec["data"].columns)
    if "items" in sec:
        result["items"] = sec["items"]
    return result


@router.get("/plugins")
async def list_plugins():
    discover, _ = _get_runner()
    mods = discover()
    return [
        {
            "slug": name,
            "name": getattr(mod, "NAME", name),
            "description": (mod.__doc__ or "").strip().split("\n")[0],
        }
        for name, mod in mods.items()
    ]


class RunRequest(BaseModel):
    config: dict = {}


class RunCodeRequest(BaseModel):
    """Run arbitrary Python in a subprocess against DuckDB; optional artifact upload."""

    code: str
    timeout: int = Field(default=120, ge=1, le=600)
    upload_artifacts: bool = True


@router.post("/run-code")
async def run_code_analysis(
    req: RunCodeRequest, 
    project_id: str | None = Query(None, alias="projectId"),
    workspace_id: str | None = Query(None, alias="workspaceId"),
    cell_id: str | None = Query(None, alias="cellId"),
    hydration_id: str | None = Query(None, alias="hydrationId"),
):
    """
    Execute Python in an isolated child process with the same helpers as POST /execute
    (sql, get_table, list_tables, pd, np, sklearn, plt). User code may write files under
    `OUTPUT_DIR` (string path); those files are copied to artifact storage when
    `upload_artifacts` is true.

    Returns: stdout, stderr, dataframes, figures, error, and `artifacts` [{filename, storageKey}].
    """
    if not settings.execute_python_enabled:
        raise HTTPException(
            status_code=403,
            detail="Python execution is disabled (RAIL_EXECUTE_ENABLED=false).",
        )
    from app.services import subprocess_code_runner

    # 1. Create Job record
    result = await convex.mutation("executions:create", {
        "projectId": project_id,
        "workspaceId": workspace_id,
        "cellId": cell_id,
        "hydrationId": hydration_id,
        "type": "code",
        "input": req.code,
        "createdAt": int(time.time() * 1000)
    })
    job_id = result["jobId"]

    # 2. Resolve hydration path
    duck = None
    if hydration_id:
        # TODO: Resolve specific hydration path
        pass
        
    if not duck and project_id:
        art = await project_artifacts_service.resolve(project_id)
        duck = art.duckdb_path

    if not sql_service.is_ready(duck):
        await convex.mutation("executions:updateStatus", {
            "jobId": job_id,
            "status": "failed",
            "errorMessage": "DuckDB mirror not ready. Run a hydration job first."
        })
        raise HTTPException(status_code=503, detail="DuckDB mirror not ready. Run a hydration job first.")

    # 3. Create execution task
    task = asyncio.create_task(
        subprocess_code_runner.run_user_code(
            req.code,
            req.timeout,
            upload_artifacts=req.upload_artifacts,
            duckdb_path=duck,
            job_id=job_id
        )
    )
    
    # 4. Register with manager
    execution_manager.register_job(job_id, task)

    # Note: We return the job_id to the client immediately for streaming UI.
    # The client can wait for the result or poll status/logs.
    return {"jobId": job_id, "status": "queued"}


@router.post("/plugins/{slug}/run")
async def run_plugin(
    slug: str,
    req: RunRequest,
    project_id: str | None = Query(None, alias="projectId"),
):
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            ontology_service.ensure_loaded(art.db_path, project_id=project_id)
        from app.services.ontology_service import _require_onto

        onto = _require_onto(project_id)
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))

    discover, run = _get_runner()
    mods = discover()
    if slug not in mods:
        raise HTTPException(404, detail=f"Analysis plugin '{slug}' not found")

    try:
        result = mods[slug].analyze(onto, **req.config)
    except Exception as e:
        raise HTTPException(500, detail=f"Analysis failed: {e}")

    return {
        "title": result.get("title", slug),
        "sections": [_serialize_section(s) for s in result.get("sections", [])],
    }
