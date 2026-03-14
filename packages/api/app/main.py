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
from app.routers import configs, jobs, ontology, analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Add engine root to sys.path so engine imports work
    engine_root = str(settings.engine_root)
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    # If a local onto.db exists from a previous hydration, load it at startup
    default_db = settings.engine_root / "ontology" / "onto.db"
    if default_db.exists():
        from app.services import ontology_service
        try:
            ontology_service.load(default_db)
            print(f"[startup] Loaded ontology from {default_db}")
        except Exception as e:
            print(f"[startup] Could not load ontology: {e}")

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

app.include_router(configs.router, prefix="/api/v1")
app.include_router(jobs.router,    prefix="/api/v1")
app.include_router(ontology.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
