from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

from app.services.convex_client import convex
from app.services.scrape_service import preview_table
from app.services.yaml_service import validate, parse

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


class ScrapePreviewRequest(BaseModel):
    url: str
    table_selector: str | None = None


# ── Validation endpoint ─────────────────────────────────────────────────────

@router.post("/validate")
async def validate_config(req: ValidateRequest):
    errors = validate(req.config_type, req.content)
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/scrape-preview")
async def scrape_preview(req: ScrapePreviewRequest):
    try:
        return preview_table(req.url, req.table_selector)
    except requests.RequestException as e:
        raise HTTPException(502, detail=f"Failed to fetch URL: {e}")
    except ValueError as e:
        raise HTTPException(422, detail=str(e))


# ── API configs ─────────────────────────────────────────────────────────────

@router.get("/apis")
async def list_api_configs():
    return await convex.query("configs:listApis", {})


@router.post("/apis")
async def create_api_config(req: CreateConfigRequest):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    return await convex.mutation("configs:createApi", {
        **req.model_dump(),
        "parsedSpec": parsed,
        "sourceType": parsed.get("type", "api"),
    })


@router.get("/apis/{slug}")
async def get_api_config(slug: str):
    result = await convex.query("configs:getApi", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"API config '{slug}' not found")
    return result


@router.put("/apis/{slug}")
async def update_api_config(slug: str, req: CreateConfigRequest):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    return await convex.mutation("configs:updateApi", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
        "tags": req.tags,
    })


@router.delete("/apis/{slug}")
async def delete_api_config(slug: str):
    return await convex.mutation("configs:deleteApi", {"slug": slug})


# ── Ontology configs ────────────────────────────────────────────────────────

@router.get("/ontologies")
async def list_ontology_configs():
    return await convex.query("configs:listOntologies", {})


@router.post("/ontologies")
async def create_ontology_config(req: CreateConfigRequest):
    errors = validate("ontology", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    return await convex.mutation("configs:createOntology", {
        **req.model_dump(),
        "parsedSpec": parsed,
        "ontologyUri": parsed.get("uri", ""),
    })


@router.get("/ontologies/{slug}")
async def get_ontology_config(slug: str):
    result = await convex.query("configs:getOntology", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"Ontology config '{slug}' not found")
    return result


@router.put("/ontologies/{slug}")
async def update_ontology_config(slug: str, req: CreateConfigRequest):
    errors = validate("ontology", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    return await convex.mutation("configs:updateOntology", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
    })


@router.delete("/ontologies/{slug}")
async def delete_ontology_config(slug: str):
    return await convex.mutation("configs:deleteOntology", {"slug": slug})


# ── Pipeline configs ────────────────────────────────────────────────────────

@router.get("/pipelines")
async def list_pipeline_configs():
    return await convex.query("configs:listPipelines", {})


@router.post("/pipelines")
async def create_pipeline_config(req: CreateConfigRequest):
    errors = validate("pipeline", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    api_slugs = list({step["api"] for step in parsed.get("steps", []) if "api" in step})
    return await convex.mutation("configs:createPipeline", {
        **req.model_dump(),
        "parsedSpec": parsed,
        "referencedApiSlugs": api_slugs,
    })


@router.get("/pipelines/{slug}")
async def get_pipeline_config(slug: str):
    result = await convex.query("configs:getPipeline", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"Pipeline config '{slug}' not found")
    return result


@router.put("/pipelines/{slug}")
async def update_pipeline_config(slug: str, req: CreateConfigRequest):
    errors = validate("pipeline", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    parsed = parse(req.content)
    api_slugs = list({step["api"] for step in parsed.get("steps", []) if "api" in step})
    return await convex.mutation("configs:updatePipeline", {
        "slug": slug,
        "content": req.content,
        "parsedSpec": parsed,
        "name": req.name,
        "isPublic": req.isPublic,
        "tags": req.tags,
        "referencedApiSlugs": api_slugs,
    })


@router.delete("/pipelines/{slug}")
async def delete_pipeline_config(slug: str):
    return await convex.mutation("configs:deletePipeline", {"slug": slug})
