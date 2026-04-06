from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class HydrationResult(BaseModel):
    job_id: str
    status: str
    duration_seconds: float
    steps: List[Dict[str, Any]]
    error: Optional[str] = None
    onto_db_path: str
    duckdb_path: str

class ExecuteResult(BaseModel):
    stdout: str
    stderr: str
    dataframes: Dict[str, Any]  # Storing as Any because PD DataFrame type isn't a simple Pydantic type out-of-the-box
    figures: List[str]
    error: Optional[str] = None