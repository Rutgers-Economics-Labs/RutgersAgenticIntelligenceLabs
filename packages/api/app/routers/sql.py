"""SQL endpoints for RAIL — backed by DuckDB export of the ontology."""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import sql_service
from app.services.convex_client import convex

router = APIRouter(prefix="/sql", tags=["sql"])


class SqlRequest(BaseModel):
    query: str
    project_id: Optional[str] = None


class NlSqlRequest(BaseModel):
    question: str
    model: Optional[str] = None
    project_id: Optional[str] = None


async def _resolve_db_path(project_id: Optional[str]) -> Optional[Path]:
    """
    If a project_id is given, find its most recent successful job and return
    the DuckDB path from that job. Falls back to the global DuckDB if not found.
    """
    if not project_id:
        return None
    try:
        jobs = await convex.query("jobs:listByProject", {"projectId": project_id, "limit": 20})
        if jobs:
            for job in jobs:
                if job.get("status") == "success" and job.get("outputDbPath"):
                    p = Path(job["outputDbPath"])
                    if p.exists():
                        return p
    except Exception:
        pass
    return None


@router.post("")
async def run_sql(req: SqlRequest):
    """Execute a SQL query against the DuckDB knowledge graph export."""
    db_path = await _resolve_db_path(req.project_id)
    try:
        return sql_service.run_query(req.query, db_path=db_path)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/translate")
async def translate_sql(req: NlSqlRequest):
    """Translate a natural-language question to SQL, then execute it."""
    db_path = await _resolve_db_path(req.project_id)
    try:
        translated = await sql_service.translate_to_sql(req.question, model=req.model, db_path=db_path)
        result = sql_service.run_query(translated["sql"], db_path=db_path)
        return {**translated, **result}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/schema")
async def get_schema(project_id: Optional[str] = None):
    """Return DuckDB schema: {table: [{name, type}]}."""
    db_path = await _resolve_db_path(project_id)
    return sql_service.get_schema(db_path=db_path)


@router.get("/tables")
async def list_tables(project_id: Optional[str] = None):
    """List available DuckDB table names."""
    db_path = await _resolve_db_path(project_id)
    return sql_service.list_tables(db_path=db_path)
