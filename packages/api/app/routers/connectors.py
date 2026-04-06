from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import yaml
from app.services.convex_client import convex
from app.services import connector_service
from app.services.yaml_service import validate

router = APIRouter(tags=["connectors"])

class CreateConnectorRequest(BaseModel):
    slug: str
    name: str
    description: str
    version: str
    content: str
    tags: list[str] = []

class ResolveRequest(BaseModel):
    base_content: str
    extends_slug: str

@router.get("/")
async def list_connectors(q: str | None = None, tags: str | None = Query(None, description="Comma-separated tags")):
    tag_list = tags.split(",") if tags else None
    return await connector_service.list_templates(q=q, tags=tag_list)

@router.get("/{slug}")
async def get_connector(slug: str):
    result = await convex.query("connectors:getBySlug", {"slug": slug})
    if not result:
        raise HTTPException(404, detail=f"Connector '{slug}' not found")
    return result

@router.post("/")
async def create_connector(req: CreateConnectorRequest):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    return await convex.mutation("connectors:create", req.model_dump())

@router.put("/{slug}")
async def update_connector(slug: str, req: CreateConnectorRequest):
    errors = validate("api", req.content)
    if errors:
        raise HTTPException(422, detail=errors)
    # Exclude slug from updates if necessary, though it should match the path
    updates = req.model_dump()
    updates["slug"] = slug
    return await convex.mutation("connectors:update", updates)

@router.delete("/{slug}")
async def delete_connector(slug: str):
    return await convex.mutation("connectors:remove", {"slug": slug})

@router.post("/{slug}/validate")
async def validate_connector(slug: str, req: CreateConnectorRequest):
    errors = validate("api", req.content)
    return {"valid": len(errors) == 0, "errors": errors}

@router.post("/resolve")
async def resolve_connector(req: ResolveRequest):
    try:
        resolved = await connector_service.resolve(req.base_content, req.extends_slug)
        return {"resolved_content": resolved}
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
