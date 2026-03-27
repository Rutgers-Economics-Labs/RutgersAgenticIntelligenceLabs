import time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import sql_service, project_artifacts_service
from app.services.convex_client import convex

router = APIRouter(prefix="/sql", tags=["sql"])


class SqlRequest(BaseModel):
    query: str


class NlSqlRequest(BaseModel):
    question: str
    model: str | None = None


@router.post("")
async def run_sql(
    req: SqlRequest, 
    project_id: str | None = Query(None, alias="projectId"),
    workspace_id: str | None = Query(None, alias="workspaceId"),
    cell_id: str | None = Query(None, alias="cellId"),
    hydration_id: str | None = Query(None, alias="hydrationId"),
):
    """Execute a SQL query against the DuckDB knowledge graph export."""
    job_id = None
    try:
        # 1. Create Job record
        result = await convex.mutation("executions:create", {
            "projectId": project_id,
            "workspaceId": workspace_id,
            "cellId": cell_id,
            "hydrationId": hydration_id,
            "type": "sql",
            "input": req.query,
            "createdAt": int(time.time() * 1000)
        })
        job_id = result["jobId"]

        # 2. Resolve hydration path
        duck = None
        if hydration_id:
            # TODO: Resolve specific hydration path from jobs table
            # For now fallback to current active if not found
            pass
            
        if not duck and project_id:
            art = await project_artifacts_service.resolve(project_id)
            duck = art.duckdb_path
            
        # 3. Execute
        await convex.mutation("executions:updateStatus", {
            "jobId": job_id,
            "status": "running",
            "startedAt": int(time.time() * 1000)
        })
        
        # Run sync query in a thread
        import asyncio
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: sql_service.run_query(req.query, duckdb_path=duck))
        
        # 4. Report success
        await convex.mutation("executions:updateStatus", {
            "jobId": job_id,
            "status": "success",
            "finishedAt": int(time.time() * 1000),
            "result": res
        })
        return res

    except Exception as e:
        if job_id:
            await convex.mutation("executions:updateStatus", {
                "jobId": job_id,
                "status": "failed",
                "finishedAt": int(time.time() * 1000),
                "errorMessage": str(e)
            })
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/translate")
async def translate_sql(req: NlSqlRequest, project_id: str | None = Query(None, alias="projectId")):
    """Translate a natural-language question to SQL, then execute it."""
    try:
        duck = None
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            duck = art.duckdb_path
        translated = await sql_service.translate_to_sql(req.question, model=req.model, duckdb_path=duck)
        result = sql_service.run_query(translated["sql"], duckdb_path=duck)
        return {**translated, **result}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schema")
async def get_schema(project_id: str | None = Query(None, alias="projectId")):
    """Return DuckDB schema: {table: [{name, type}]}."""
    duck = None
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        duck = art.duckdb_path
    return sql_service.get_schema(duckdb_path=duck)


@router.get("/tables")
async def list_tables(project_id: str | None = Query(None, alias="projectId")):
    """List available DuckDB table names."""
    duck = None
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        duck = art.duckdb_path
    return sql_service.list_tables(duckdb_path=duck)
