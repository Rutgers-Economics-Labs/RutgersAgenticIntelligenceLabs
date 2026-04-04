from fastapi import APIRouter, HTTPException
from app.services.convex_client import convex

router = APIRouter(prefix="/projects", tags=["projects"])

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
