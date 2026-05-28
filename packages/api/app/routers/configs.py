from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import requests

from app.services.convex_client import convex
from app.services import planner_service
from app.services.document_service import preview_document
from app.services.scrape_service import preview_table
from app.services.yaml_service import validate, parse
from app.services.pipeline_validate import validate_stored_pipeline
from app.services.safe_publish_service import (
    publish_config_files,
    record_publish_failure,
    record_publish_success,
    rollback_config_update,
    should_auto_publish,
)

router = APIRouter(prefix="/configs", tags=["configs"])


class CreateConfigRequest(BaseModel):
    name: str
    slug: str
    content: str       # raw YAML
    isPublic: bool = False
    tags: list[str] = []


class ValidateRequest(BaseModel):
    config_type: str   # "api" | "ontology" | "pipeline"
    content: str


class ValidatePipelineRequest(BaseModel):
    """Deep validation: Convex API/ontology registry + ontology alignment + transforms."""
    content: str


class ScrapePreviewRequest(BaseModel):
    url: str
    table_selector: str | None = None
    javascript: bool = False
    encoding: str | None = None


class DocumentPreviewRequest(BaseModel):
    storage_key: str
    extraction_mode: str
    pages: str | None = None


async def _get_project_for_save(project_id: str | None) -> dict | None:
    if not project_id:
        return None
    project = None
    try:
        project = await convex.query("projects:getById", {"projectId": project_id})
    except Exception:
        project = None
    if not project:
        try:
            project = await convex.query("projects:get", {"slug": project_id})
        except Exception:
            project = None
    if not project:
        candidate_slugs = [project_id]
        if isinstance(project_id, str) and project_id.startswith("local:"):
            candidate_slugs.append(project_id.removeprefix("local:"))
        for candidate in candidate_slugs:
            try:
                project = await planner_service.get_project_by_slug(candidate)
                if project:
                    break
            except Exception:
                project = None
    if not project:
        raise HTTPException(404, detail="Project not found")
    return project


async def _maybe_publish_config(
    *,
    project: dict | None,
    kind: str,
    slug: str,
    content: str,
    action: str,
) -> dict | None:
    if not project or not await should_auto_publish(project):
        return None
    try:
        result = await publish_config_files(project, kind, slug, content, action=action)
        await record_publish_success(project["_id"], result)
        return result
    except Exception as exc:
        await record_publish_failure(project["_id"], str(exc))
        raise


# ── Validation endpoint ─────────────────────────────────────────────────────

@router.post("/validate")
async def validate_config(req: ValidateRequest):
    errors = validate(req.config_type, req.content)
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/pipelines/validate")
async def validate_pipeline_config(req: ValidatePipelineRequest):
    errors = await validate_stored_pipeline(convex, {"content": req.content})
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/scrape-preview")
async def scrape_preview(req: ScrapePreviewRequest):
    try:
        return preview_table(req.url, req.table_selector, req.javascript, req.encoding)
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"Failed to fetch URL: {e}")
    except ValueError as e:
        raise HTTPException(422, detail=str(e))


@router.post("/doc-preview")
async def doc_preview(req: DocumentPreviewRequest):
    try:
        return await preview_document(req.storage_key, req.extraction_mode, req.pages)
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"Failed to fetch document: {e}")
    except ValueError as e:
        raise HTTPException(422, detail=str(e))


# ── API configs ─────────────────────────────────────────────────────────────

@router.get("/apis")
async def list_api_configs():
    return await convex.query("configs:listApis", {})


@router.post("/apis")
async def create_api_config(req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    project = await _get_project_for_save(project_id)
    result = await convex.mutation("configs:createApi", {
        **req.model_dump(),
        "parsedSpec": parsed,
        "sourceType": parsed.get("type", "api"),
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="apis",
            slug=req.slug,
            content=req.content,
            action="create",
        )
    except Exception as exc:
        await rollback_config_update("apis", req.slug, None)
        raise HTTPException(502, detail=f"Config saved locally but GitHub publish failed and was rolled back: {exc}")
    return {"configId": result, "publish": publish_result}


@router.get("/apis/{slug}")
async def get_api_config(slug: str):
    result = await convex.query("configs:getApi", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"API config '{slug}' not found")
    return result


@router.put("/apis/{slug}")
async def update_api_config(slug: str, req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    project = await _get_project_for_save(project_id)
    previous = await convex.query("configs:getApi", {"slug": slug})
    result = await convex.mutation("configs:updateApi", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
        "tags": req.tags,
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="apis",
            slug=slug,
            content=req.content,
            action="update",
        )
    except Exception as exc:
        await rollback_config_update("apis", slug, previous)
        raise HTTPException(502, detail=f"Config update rolled back because GitHub publish failed: {exc}")
    return {"configId": result, "publish": publish_result}


@router.delete("/apis/{slug}")
async def delete_api_config(slug: str):
    return await convex.mutation("configs:deleteApi", {"slug": slug})


# ── Ontology configs ────────────────────────────────────────────────────────

@router.get("/ontologies")
async def list_ontology_configs():
    return await convex.query("configs:listOntologies", {})


@router.post("/ontologies")
async def create_ontology_config(req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    errors = validate("ontology", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    project = await _get_project_for_save(project_id)
    result = await convex.mutation("configs:createOntology", {
        "slug": req.slug,
        "name": req.name,
        "content": req.content,
        "isPublic": req.isPublic,
        "parsedSpec": parsed,
        "ontologyUri": parsed.get("uri", ""),
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="ontologies",
            slug=req.slug,
            content=req.content,
            action="create",
        )
    except Exception as exc:
        await rollback_config_update("ontologies", req.slug, None)
        raise HTTPException(502, detail=f"Config saved locally but GitHub publish failed and was rolled back: {exc}")
    return {"configId": result, "publish": publish_result}


@router.get("/ontologies/{slug}")
async def get_ontology_config(slug: str):
    result = await convex.query("configs:getOntology", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"Ontology config '{slug}' not found")
    return result


@router.put("/ontologies/{slug}")
async def update_ontology_config(slug: str, req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    errors = validate("ontology", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    project = await _get_project_for_save(project_id)
    previous = await convex.query("configs:getOntology", {"slug": slug})
    result = await convex.mutation("configs:updateOntology", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="ontologies",
            slug=slug,
            content=req.content,
            action="update",
        )
    except Exception as exc:
        await rollback_config_update("ontologies", slug, previous)
        raise HTTPException(502, detail=f"Config update rolled back because GitHub publish failed: {exc}")
    return {"configId": result, "publish": publish_result}


@router.delete("/ontologies/{slug}")
async def delete_ontology_config(slug: str):
    return await convex.mutation("configs:deleteOntology", {"slug": slug})


# ── Pipeline configs ────────────────────────────────────────────────────────

@router.get("/pipelines")
async def list_pipeline_configs():
    return await convex.query("configs:listPipelines", {})


@router.post("/pipelines")
async def create_pipeline_config(req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    deep = await validate_stored_pipeline(convex, {"content": req.content})
    if deep:
        raise HTTPException(422, detail=deep)
    parsed = parse(req.content)
    api_slugs = list({step["api"] for step in parsed.get("steps", []) if "api" in step})
    project = await _get_project_for_save(project_id)
    result = await convex.mutation("configs:createPipeline", {
        **req.model_dump(),
        "parsedSpec": parsed,
        "referencedApiSlugs": api_slugs,
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="pipelines",
            slug=req.slug,
            content=req.content,
            action="create",
        )
    except Exception as exc:
        await rollback_config_update("pipelines", req.slug, None)
        raise HTTPException(502, detail=f"Config saved locally but GitHub publish failed and was rolled back: {exc}")
    return {"configId": result, "publish": publish_result}


@router.get("/pipelines/{slug}")
async def get_pipeline_config(slug: str):
    result = await convex.query("configs:getPipeline", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"Pipeline config '{slug}' not found")
    return result


@router.put("/pipelines/{slug}")
async def update_pipeline_config(slug: str, req: CreateConfigRequest, project_id: str | None = Query(None, alias="projectId")):
    deep = await validate_stored_pipeline(convex, {"content": req.content})
    if deep:
        raise HTTPException(422, detail=deep)
    parsed = parse(req.content)
    api_slugs = list({step["api"] for step in parsed.get("steps", []) if "api" in step})
    project = await _get_project_for_save(project_id)
    previous = await convex.query("configs:getPipeline", {"slug": slug})
    result = await convex.mutation("configs:updatePipeline", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
        "tags": req.tags,
        "referencedApiSlugs": api_slugs,
    })
    try:
        publish_result = await _maybe_publish_config(
            project=project,
            kind="pipelines",
            slug=slug,
            content=req.content,
            action="update",
        )
    except Exception as exc:
        await rollback_config_update("pipelines", slug, previous)
        raise HTTPException(502, detail=f"Config update rolled back because GitHub publish failed: {exc}")
    return {"configId": result, "publish": publish_result}


@router.delete("/pipelines/{slug}")
async def delete_pipeline_config(slug: str):
    return await convex.mutation("configs:deletePipeline", {"slug": slug})
