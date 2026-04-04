"""
RAIL FastAPI service.
Run: uvicorn app.main:app --reload --port 8000
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.convex_client import ConvexBackendConfigurationError
from app.routers import configs, jobs, ontology, analysis, storage, sql, execute, agent, registry, project_agent, questions, context, quality, connectors, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    _hl = logging.getLogger("rail.hydration")
    if not _hl.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(levelname)s [rail.hydration] %(message)s"))
        _hl.addHandler(_h)
    _hl.setLevel(logging.INFO)
    _hl.propagate = False

    # Add engine root to sys.path so engine imports work
    engine_root = str(settings.engine_root)
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    # Push LLM API keys into os.environ so LiteLLM can read them
    import os
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)

    # If a local onto.db exists from a previous hydration, load it at startup
    default_db = settings.engine_root / "ontology" / "onto.db"
    if default_db.exists():
        from app.services import ontology_service, sql_service
        try:
            ontology_service.load(default_db)
            print(f"[startup] Loaded ontology from {default_db}")
        except Exception as e:
            extra = ""
            if "locked" in str(e).lower():
                extra = (
                    " Another process is using onto.db (second API/uvicorn, Streamlit, hydrate.py, or a stuck job). "
                    "Close those or run one API instance without --reload."
                )
            print(f"[startup] Could not load ontology: {e}{extra}")

        # Load DuckDB export if it exists
        default_duckdb = settings.engine_root / "ontology" / "onto.duckdb"
        if default_duckdb.exists():
            sql_service.set_path(default_duckdb)
            print(f"[startup] Loaded DuckDB from {default_duckdb}")

    yield


app = FastAPI(
    title="RAIL API",
    description="Rutgers Agentic Intelligence Labs — ontology engine API",
    version="0.2.0",
    lifespan=lifespan,
)

_cors_kw: dict = {
    "allow_origins": settings.api_cors_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.api_cors_origin_regex and settings.api_cors_origin_regex.strip():
    _cors_kw["allow_origin_regex"] = settings.api_cors_origin_regex.strip()
app.add_middleware(CORSMiddleware, **_cors_kw)

app.include_router(configs.router,  prefix="/api/v1")
app.include_router(jobs.router,     prefix="/api/v1")
app.include_router(ontology.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(storage.router,  prefix="/api/v1")
app.include_router(sql.router,      prefix="/api/v1")
app.include_router(execute.router,  prefix="/api/v1")
app.include_router(agent.router,    prefix="/api/v1")
app.include_router(registry.router,       prefix="/api/v1")
app.include_router(project_agent.router,  prefix="/api/v1")
app.include_router(questions.router,      prefix="/api/v1")
app.include_router(context.router,        prefix="/api/v1")
app.include_router(quality.router,        prefix="/api/v1")
app.include_router(connectors.router,     prefix="/api/v1/connectors")
app.include_router(projects.router,       prefix="/api/v1")


@app.exception_handler(ConvexBackendConfigurationError)
async def convex_configuration_handler(_, exc: ConvexBackendConfigurationError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}
