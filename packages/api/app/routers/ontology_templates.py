import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.convex_client import convex

router = APIRouter(prefix="/ontology-templates", tags=["ontology-templates"])


class OntologyTemplateRequest(BaseModel):
    slug: str
    name: str
    description: str
    version: str = "1.0"
    tags: list[str] = []
    content: str


class OntologyTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    content: str | None = None


@router.get("/")
async def list_templates(tags: str | None = Query(None)):
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        return await convex.query("ontologyTemplates:listByTag", {"tags": tag_list})
    return await convex.query("ontologyTemplates:list", {})


@router.get("/{slug}")
async def get_template(slug: str):
    tpl = await convex.query("ontologyTemplates:getBySlug", {"slug": slug})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.post("/")
async def create_template(req: OntologyTemplateRequest):
    try:
        await convex.mutation("ontologyTemplates:create", req.model_dump())
        return await convex.query("ontologyTemplates:getBySlug", {"slug": req.slug})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{slug}")
async def update_template(slug: str, req: OntologyTemplateUpdate):
    try:
        update_data = req.model_dump(exclude_none=True)
        update_data["slug"] = slug
        await convex.mutation("ontologyTemplates:update", update_data)
        return await convex.query("ontologyTemplates:getBySlug", {"slug": slug})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}")
async def delete_template(slug: str):
    try:
        await convex.mutation("ontologyTemplates:remove", {"slug": slug})
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/validate")
async def validate_template(slug: str):
    tpl = await convex.query("ontologyTemplates:getBySlug", {"slug": slug})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    try:
        parsed = yaml.safe_load(tpl["content"])
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Template content is not a valid YAML dictionary")
        if parsed.get("config_type") != "ontology":
            raise HTTPException(status_code=400, detail="Template config_type is not 'ontology'")
        return {"valid": True, "parsed": parsed}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")
