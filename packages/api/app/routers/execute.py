"""Code execution endpoint — runs Python in a sandboxed namespace."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services import code_runner

router = APIRouter(prefix="/execute", tags=["execute"])


class ExecuteRequest(BaseModel):
    code: str
    timeout: int = 60  # seconds


@router.post("")
async def execute_code(req: ExecuteRequest):
    """
    Execute Python code with access to the knowledge graph via DuckDB.

    Available in the execution namespace:
    - sql(query) → pd.DataFrame
    - get_table(name) → pd.DataFrame
    - list_tables() → list[str]
    - pd, np, smf, sm, sklearn, plt

    Returns: {stdout, stderr, dataframes, figures (base64 PNGs), error}
    """
    if req.timeout > 300:
        raise HTTPException(status_code=400, detail="Timeout cannot exceed 300s")
    if not settings.execute_python_enabled:
        raise HTTPException(
            status_code=403,
            detail="Python execution is disabled (RAIL_EXECUTE_ENABLED=false).",
        )
    return await code_runner.run_code_async(req.code, timeout_seconds=req.timeout)
