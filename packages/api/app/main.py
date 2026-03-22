"""
RAIL FastAPI service.
Run: uvicorn app.main:app --reload --port 8000
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import configs, jobs, ontology, analysis, storage, sql, execute, agent, registry


@asynccontextmanager
async def lifespan(app: FastAPI):
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
            print(f"[startup] Could not load ontology: {e}")

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(configs.router,  prefix="/api/v1")
app.include_router(jobs.router,     prefix="/api/v1")
app.include_router(ontology.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(storage.router,  prefix="/api/v1")
app.include_router(sql.router,      prefix="/api/v1")
app.include_router(execute.router,  prefix="/api/v1")
app.include_router(agent.router,    prefix="/api/v1")
app.include_router(registry.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
