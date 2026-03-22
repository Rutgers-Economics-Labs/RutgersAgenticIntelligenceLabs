from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import registry_service

router = APIRouter(prefix="/registry", tags=["registry"])


class RegistryEntryRequest(BaseModel):
    provider: str
    id: str
    name: str
    description: str
    unit: str
    frequency: str
    geography: str
    tags: list[str] = []
    exampleYaml: str
    updatedAt: int | None = None


@router.get("/search")
async def search_registry(
    q: str = Query(default=""),
    provider: str | None = Query(default=None),
    geography: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    return await registry_service.search_registry_entries(q, provider, geography, limit)


@router.get("/{provider}/{source_id}")
async def get_registry_entry(provider: str, source_id: str):
    entry = await registry_service.get_registry_entry(provider, source_id)
    if not entry:
        raise HTTPException(404, detail=f"Registry entry '{provider}/{source_id}' not found")
    return entry


@router.post("")
async def create_registry_entry(req: RegistryEntryRequest):
    return await registry_service.create_registry_entry(req.model_dump())
