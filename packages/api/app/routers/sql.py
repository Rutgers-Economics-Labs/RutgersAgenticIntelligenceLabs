"""SQL endpoints for RAIL — backed by DuckDB export of the ontology."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import sql_service, project_artifacts_service

router = APIRouter(prefix="/sql", tags=["sql"])


class SqlRequest(BaseModel):
    query: str


class NlSqlRequest(BaseModel):
    question: str
    model: str | None = None


@router.post("")
async def run_sql(req: SqlRequest, project_id: str | None = Query(None, alias="projectId")):
    """Execute a SQL query against the DuckDB knowledge graph export."""
    try:
        duck = None
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            duck = art.duckdb_path
        return sql_service.run_query(req.query, duckdb_path=duck)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
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
