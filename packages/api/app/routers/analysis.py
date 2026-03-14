import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

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


@router.post("/plugins/{slug}/run")
async def run_plugin(slug: str, req: RunRequest):
    from app.services.ontology_service import _require_onto
    try:
        onto = _require_onto()
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
