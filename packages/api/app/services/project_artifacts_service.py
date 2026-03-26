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

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.convex_client import convex
from app.services.storage_service import storage


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
        return storage_key_or_path
    dest = _local_cache_dir(project_id) / filename
    await storage.download(storage_key_or_path, dest)
    return str(dest)


async def resolve(project_id: str) -> ProjectArtifacts:
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        raise RuntimeError("Project not found")

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

    if not db_key:
        raise RuntimeError("No ontology is active for this project. Run hydration first.")

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

    return ProjectArtifacts(
        project_id=project_id,
        db_path=db_path,
        owl_path=owl_path,
        duckdb_path=duckdb_path,
        embeddings_path=embeddings_path,
    )

