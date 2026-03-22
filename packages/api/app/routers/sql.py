"""SQL endpoints for RAIL — backed by DuckDB export of the ontology."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import sql_service

router = APIRouter(prefix="/sql", tags=["sql"])


class SqlRequest(BaseModel):
    query: str


class NlSqlRequest(BaseModel):
    question: str
    model: str | None = None


@router.post("")
async def run_sql(req: SqlRequest):
    """Execute a SQL query against the DuckDB knowledge graph export."""
    try:
        return sql_service.run_query(req.query)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/translate")
async def translate_sql(req: NlSqlRequest):
    """Translate a natural-language question to SQL, then execute it."""
    try:
        translated = await sql_service.translate_to_sql(req.question, model=req.model)
        result = sql_service.run_query(translated["sql"])
        return {**translated, **result}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schema")
async def get_schema():
    """Return DuckDB schema: {table: [{name, type}]}."""
    return sql_service.get_schema()


@router.get("/tables")
async def list_tables():
    """List available DuckDB table names."""
    return sql_service.list_tables()
