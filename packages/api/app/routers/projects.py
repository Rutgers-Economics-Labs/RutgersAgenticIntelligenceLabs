import time
import yaml
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import ontology_service, sql_service
from app.services.project_artifacts_service import find_latest_success_job_with_outputs

router = APIRouter(prefix="/projects", tags=["projects"])

class RegisterArtifactsBody(BaseModel):
    """Optional explicit paths when job discovery fails (e.g. paths only on disk)."""

    output_db_path: str | None = None
    output_owl_path: str | None = None


class CreateProjectRequest(BaseModel):
    name: str
    slug: str
    description: str = ""
    approach: str = "data-first"
    ontologyConfigSlug: str | None = None
    apiConfigSlugs: list[str] = []
    pipelineConfigSlug: str | None = None
    ontologyTemplates: list[str] | None = None


@router.post("/")
async def create_project(data: CreateProjectRequest):
    project_data = data.model_dump()

    # Process ontologyTemplates if provided
    ontology_templates = project_data.pop("ontologyTemplates", None)
    if ontology_templates:
        merged_onto = {
            "uri": f"http://rail.rutgers.edu/ontology/{data.slug}",
            "classes": [],
            "data_properties": [],
            "object_properties": []
        }
        for template_slug in ontology_templates:
            tpl = await convex.query("ontologyTemplates:getBySlug", {"slug": template_slug})
            if tpl and tpl.get("content"):
                tpl_content = yaml.safe_load(tpl["content"])
                merged_onto["classes"].extend(tpl_content.get("classes", []))
                merged_onto["data_properties"].extend(tpl_content.get("data_properties", []))
                merged_onto["object_properties"].extend(tpl_content.get("object_properties", []))

        # Create as the project's initial ontologyConfig
        config_slug = f"{data.slug}-ontology"
        await convex.mutation("configs:createOntology", {
            "name": f"{data.name} Ontology",
            "slug": config_slug,
            "content": yaml.dump(merged_onto),
            "parsedSpec": merged_onto,
            "ontologyUri": merged_onto["uri"],
            "isPublic": False
        })
        project_data["ontologyConfigSlug"] = config_slug
        project_data["ontologyTemplates"] = ontology_templates

    project_id = await convex.mutation("projects:create", project_data)
    return await convex.query("projects:getBySlug", {"slug": data.slug})


@router.post("/{slug}/register-artifacts")
async def register_artifacts_from_job(
    slug: str,
    job_id: str | None = Query(None, alias="jobId"),
    body: RegisterArtifactsBody | None = Body(None),
):
    """
    Copy ontology artifact paths from a successful hydration job onto the Convex project.

    Use when hydration finished but the project doc was never updated (428 Sync Required).
    Defaults to the latest successful job for this project that has outputDbPath.
    Optional JSON body: {"output_db_path": "/abs/path/onto.db", "output_owl_path": "..."} to set paths without job lookup.
    """
    project = await convex.query("projects:get", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    convex_project_id = project["_id"]
    job: dict | None = None
    db_key: str | None = None
    owl_key: str | None = None
    last_job_convex_id: str | None = None

    if body and body.output_db_path:
        db_key = body.output_db_path.strip()
        owl_key = body.output_owl_path
        if job_id:
            j = await convex.query("jobs:get", {"jobId": job_id})
            if j:
                last_job_convex_id = j["_id"]
    elif job_id:
        job = await convex.query("jobs:get", {"jobId": job_id})
        if not job:
            raise HTTPException(404, "Job not found")
        if job.get("status") not in ("success", "completed"):
            raise HTTPException(400, "Job is not in success status")
        db_key = job.get("outputDbPath")
        owl_key = job.get("outputOwlPath")
        last_job_convex_id = job["_id"]
    else:
        job = await find_latest_success_job_with_outputs(project)
        if not job:
            raise HTTPException(
                400,
                "No successful hydration job with stored outputs found for this project. "
                "Run hydration with this project selected, POST with ?jobId=..., or send "
                '{"output_db_path": "/path/to/onto.db"} in the request body.',
            )
        db_key = job.get("outputDbPath")
        owl_key = job.get("outputOwlPath")
        last_job_convex_id = job["_id"]

    if not db_key:
        raise HTTPException(400, "Job has no outputDbPath stored")

    parent = Path(db_key).parent
    duckdb_path = str(parent / "onto.duckdb")
    embeddings_path = str(parent / "embeddings.db")

    now_ms = int(time.time() * 1000)
    patch: dict = {
        "projectId": convex_project_id,
        "status": "hydrated",
        "lastHydratedAt": now_ms,
        "activeOntologyDbPath": db_key,
        "activeOntologyOwlPath": owl_key,
        "activeOntologyDuckdbPath": duckdb_path,
        "activeOntologyEmbeddingsPath": embeddings_path,
    }
    if last_job_convex_id is not None:
        patch["lastJobId"] = last_job_convex_id
    await convex.mutation("projects:updateById", patch)

    # Warm ontology on the same thread the API uses for Owlready2 (executor), not the event loop.
    db_path = Path(db_key).resolve()
    if db_path.is_file():
        try:
            await ontology_service.ensure_loaded_async(str(db_path), project_id=slug)
        except Exception:
            pass
    duck_p = Path(duckdb_path).resolve()
    if duck_p.is_file():
        try:
            sql_service.set_path(str(duck_p))
        except Exception:
            pass

    return {
        "ok": True,
        "jobId": last_job_convex_id,
        "activeOntologyDbPath": db_key,
        "activeOntologyDuckdbPath": duckdb_path,
    }


@router.get("/{slug}/context")
async def get_project_context(slug: str):
    """Returns a structured context snapshot for agent initialization."""
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    context = {
        "project": {
            "name": project["name"],
            "slug": project["slug"],
            "status": project.get("status"),
            "last_hydrated": project.get("lastHydratedAt"),
        },
        "ontology": {},
        "data_sources": [],
        "pipelines": [],
        "analysis_plugins": [],
    }

    # Fetch ontology info if project is hydrated
    if project.get("activeOntologyDuckdbPath"):
        try:
            from app.services import sql_service, ontology_service
            sql_service.set_path(project["activeOntologyDuckdbPath"])
            schema = sql_service.get_schema()
            classes = await ontology_service._run(ontology_service.list_classes)
            context["ontology"] = {
                "classes": classes,
                "schema_ddl": sql_service.get_schema_ddl(),
            }
        except Exception:
            pass

    # Fetch data sources
    api_slugs = project.get("apiConfigSlugs", [])
    for slug_s in api_slugs:
        cfg = await convex.query("configs:getApiBySlug", {"slug": slug_s})
        if cfg:
            context["data_sources"].append({"slug": cfg["slug"], "name": cfg["name"]})

    # Fetch pipeline info
    pipeline_slug = project.get("pipelineConfigSlug")
    if pipeline_slug:
        pipeline = await convex.query("configs:getPipelineBySlug", {"slug": pipeline_slug})
        if pipeline:
            context["pipelines"].append({"slug": pipeline["slug"], "name": pipeline["name"]})

    return context
