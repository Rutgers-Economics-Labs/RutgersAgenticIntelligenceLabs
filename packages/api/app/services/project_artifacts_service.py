"""
Resolve per-project knowledge graph artifact paths/keys.

Projects are hydrated via jobs that produce:
  - onto.db (OWLReady2 SQLite quadstore)
  - populated_ontology.owl
  - onto.duckdb (DuckDB mirror export)
  - embeddings.db (semantic search index)

After hydration success, we persist the active artifact pointers onto the project doc
in Convex so API reads can reliably select the right ontology per project.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.convex_client import convex
from app.services.storage_service import storage
from app.services import ontology_service


@dataclass(frozen=True)
class ProjectArtifacts:
    project_id: str
    db_path: str
    owl_path: str | None
    duckdb_path: str
    embeddings_path: str


def _local_cache_dir(project_id: str) -> Path:
    base = Path("/tmp/rail_project_artifacts") / project_id
    base.mkdir(parents=True, exist_ok=True)
    return base


async def _materialize(storage_key_or_path: str, *, filename: str, project_id: str) -> str:
    """
    Return a local filesystem path to the artifact.
    - local backend: storage_key_or_path is already a local path
    - s3 backend: download to /tmp/rail_project_artifacts/<project_id>/<filename>
    """
    if settings.storage_backend == "local":
        p = Path(storage_key_or_path)
        if not p.is_absolute():
            # Assume relative to repo root if not absolute
            repo_root = Path(__file__).resolve().parents[1] # app/services
            repo_root = repo_root.parents[2] # RutgersAgenticIntelligenceLabs
            p = repo_root / p
        
        p = p.resolve() # Handle symlinks and .. to ensure a canonical string for state mapping
        
        if not p.exists():
            # FALLBACK: If the project-specific local file is missing (e.g. from /tmp cleanup),
            # fall back to the global hydrated ontology in engine/ontology/onto.db
            global_path = (Path(__file__).resolve().parents[4] / "packages" / "engine" / "ontology" / "onto.db").resolve()
            if global_path.exists():
                return str(global_path)
                
        return str(p)
    dest = _local_cache_dir(project_id) / filename
    await storage.download(storage_key_or_path, dest)
    return str(dest)


class HydrationRequiredError(RuntimeError):
    pass


_NON_QUADSTORE_SUFFIXES = {".yaml", ".yml", ".owl", ".json", ".md", ".txt", ".csv"}


def _is_valid_quadstore_path(path: str | None) -> bool:
    if not path:
        return False
    candidate = Path(path)
    suffix = candidate.suffix.lower()
    if suffix in _NON_QUADSTORE_SUFFIXES:
        return False
    if suffix != ".db":
        return False
    if not candidate.exists():
        return False
    try:
        with sqlite3.connect(f"file:{candidate.resolve()}?mode=ro", uri=True) as conn:
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return True
    except Exception:
        return False


def _quadstore_fallback_paths(db_key: str | None) -> list[str]:
    if not db_key:
        return []
    parent = Path(db_key).parent
    return [str(parent / "onto.db")]


def _populate_local_active_artifact_paths(project: dict) -> dict:
    root_value = project.get("localRepoPath")
    if not root_value:
        return project
    root = Path(root_value).resolve()
    ontology_root = root / ".ontology"
    db_path = ontology_root / "onto.db"
    duckdb_path = ontology_root / "onto.duckdb"
    owl_path = ontology_root / "populated_ontology.owl"
    embeddings_path = ontology_root / "embeddings.db"

    enriched = dict(project)
    if db_path.exists() and not enriched.get("activeOntologyDbPath"):
        enriched["activeOntologyDbPath"] = str(db_path)
    if duckdb_path.exists() and not enriched.get("activeOntologyDuckdbPath"):
        enriched["activeOntologyDuckdbPath"] = str(duckdb_path)
    if owl_path.exists() and not enriched.get("activeOntologyOwlPath"):
        enriched["activeOntologyOwlPath"] = str(owl_path)
    if embeddings_path.exists() and not enriched.get("activeOntologyEmbeddingsPath"):
        enriched["activeOntologyEmbeddingsPath"] = str(embeddings_path)
    return enriched


async def _resolve_active_db_key(project: dict, db_key: str | None) -> str | None:
    if db_key and _is_valid_quadstore_path(db_key):
        return db_key

    for candidate in _quadstore_fallback_paths(db_key):
        if _is_valid_quadstore_path(candidate):
            return candidate

    job = await find_latest_success_job_with_outputs(project)
    if not job:
        return db_key

    job_db = job.get("outputDbPath")
    if job_db and _is_valid_quadstore_path(str(job_db)):
        return str(job_db)

    for candidate in _quadstore_fallback_paths(str(job_db) if job_db else None):
        if _is_valid_quadstore_path(candidate):
            return candidate

    return db_key


def _job_has_stored_outputs(job: dict) -> bool:
    st = job.get("status")
    if st not in ("success", "completed"):
        return False
    return bool(job.get("outputDbPath"))


async def find_latest_success_job_with_outputs(project: dict) -> dict | None:
    """
    Find a hydration job that finished successfully and has outputDbPath.

    Primary path: jobs indexed by projectId (listByProject).
    Fallback: recent jobs where projectSlug matches but projectId was missing on insert,
    or where projectId matches after a backfill.
    """
    slug = project.get("slug")
    project_internal_id = project.get("_id")

    if slug:
        try:
            jobs_list = await convex.query(
                "jobs:listByProject",
                {"projectSlug": slug, "limit": 50},
            )
        except Exception:
            jobs_list = None
        if jobs_list:
            for j in jobs_list:
                if _job_has_stored_outputs(j):
                    return j

    try:
        recent = await convex.query("jobs:list", {"limit": 200})
    except Exception:
        recent = None
    if not recent:
        return None

    for j in recent:
        if not _job_has_stored_outputs(j):
            continue
        if slug and j.get("projectSlug") == slug:
            return j
        if project_internal_id and j.get("projectId") == project_internal_id:
            return j

    return None


async def resolve(project_id: str) -> ProjectArtifacts:
    # 1. Try resolving by Internal ID first
    project = await convex.query("projects:getById", {"projectId": project_id})
    
    # 2. If not found, try resolving by Slug
    if not project:
        project = await convex.query("projects:get", {"slug": project_id})
        
    if not project:
        raise RuntimeError(f"Project '{project_id}' not found (tried ID and Slug)")

    db_key = project.get("activeOntologyDbPath")
    owl_key = project.get("activeOntologyOwlPath")
    duck_key = project.get("activeOntologyDuckdbPath")
    emb_key = project.get("activeOntologyEmbeddingsPath")

    # Back-compat: if not yet persisted on the project, fall back to lastJobId → job.outputDbPath
    if not db_key:
        last_job = project.get("lastJobId")
        if last_job:
            job = await convex.query("jobs:get", {"jobId": last_job})
            if job and job.get("outputDbPath"):
                db_key = job["outputDbPath"]
                owl_key = job.get("outputOwlPath") or owl_key

    # If project was never patched (e.g. worker skipped project update) but jobs exist with outputs,
    # use the latest successful hydration job (including jobs only linked via projectSlug).
    if not db_key:
        j = await find_latest_success_job_with_outputs(project)
        if j:
            db_key = j["outputDbPath"]
            owl_key = j.get("outputOwlPath") or owl_key

    if not db_key:
        raise HydrationRequiredError(
            "No ontology is active for this project. Run hydration from this project, "
            "or ensure the FastAPI server can read the artifact paths stored with the job."
        )

    db_key = await _resolve_active_db_key(project, db_key)
    if not db_key or not _is_valid_quadstore_path(db_key):
        raise HydrationRequiredError(
            "No valid ontology quadstore (onto.db) is active for this project. "
            "Run hydration or repair activeOntologyDbPath to point at onto.db, not ontology.yaml."
        )

    db_path = await _materialize(db_key, filename="onto.db", project_id=project_id)
    owl_path = await _materialize(owl_key, filename="populated_ontology.owl", project_id=project_id) if owl_key else None

    # Derive sibling files from onto.db unless explicitly set.
    parent = Path(db_path).parent
    duck_default = str(parent / "onto.duckdb")
    emb_default = str(parent / "embeddings.db")

    duckdb_path = duck_default
    if duck_key:
        duckdb_path = await _materialize(duck_key, filename="onto.duckdb", project_id=project_id)

    embeddings_path = emb_default
    if emb_key:
        embeddings_path = await _materialize(emb_key, filename="embeddings.db", project_id=project_id)

    # SELF-HEALING: If DuckDB is missing but SQLite is here, regenerate it immediately.
    # This prevents "No DuckDB database loaded" errors after /tmp cleanup.
    if not Path(duckdb_path).exists() and Path(db_path).exists():
        print(f"  [project_artifacts_service] project={project_id} DuckDB missing, regenerating at {duckdb_path}...")
        await ontology_service.ensure_loaded_async(db_path, project_id=project_id)
        await ontology_service.export_to_duckdb(project_id, duckdb_path)

    return ProjectArtifacts(
        project_id=project_id,
        db_path=db_path,
        owl_path=owl_path,
        duckdb_path=duckdb_path,
        embeddings_path=embeddings_path,
    )
