from typing import Union
from fastapi import APIRouter, HTTPException, Query
from app.services import ontology_service

router = APIRouter(prefix="/ontology", tags=["ontology"])


@router.get("/classes")
async def list_classes():
    return await ontology_service._run(ontology_service.list_classes)


@router.get("/classes/{class_name}/instances")
async def list_instances(
    class_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str = Query(""),
):
    try:
        return await ontology_service._run(
            ontology_service.list_instances, class_name, page, limit, search
        )
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/entities/{uri}")
async def get_entity(uri: str):
    try:
        return await ontology_service._run(ontology_service.get_entity, uri)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/entities/{uri}/graph")
async def get_entity_graph(uri: str):
    try:
        return await ontology_service._run(ontology_service.get_entity_graph, uri)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/graph")
async def get_full_graph(
    types: str = Query("State,County,Municipality,Individual"),
    state_fips: Union[str, None] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
):
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    return await ontology_service._run(
        ontology_service.get_full_graph, type_list, state_fips, limit
    )


@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=1),
    types: Union[str, None] = Query(None),
):
    type_list = [t.strip() for t in types.split(",")] if types else None
    return await ontology_service._run(ontology_service.search_entities, q, type_list)


@router.get("/series")
async def list_series():
    return await ontology_service._run(ontology_service.list_series)


@router.get("/series/{series_id}/data")
async def get_series_data(series_id: str):
    return await ontology_service._run(ontology_service.get_series_data, series_id)
