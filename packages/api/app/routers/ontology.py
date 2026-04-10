from typing import Union
from fastapi import APIRouter, HTTPException, Query
from app.services import embedding_service, ontology_service
from app.services import project_artifacts_service

router = APIRouter(prefix="/ontology", tags=["ontology"])


@router.get("/classes")
async def list_classes(project_id: str | None = Query(None, alias="projectId")):
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        ontology_service.ensure_loaded(art.db_path, project_id=project_id)
    return await ontology_service._run(project_id, ontology_service.list_classes)


@router.get("/classes/{class_name}/instances")
async def list_instances(
    class_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    project_id: str | None = Query(None, alias="projectId"),
):
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            ontology_service.ensure_loaded(art.db_path, project_id=project_id)
        return await ontology_service._run(
            project_id, ontology_service.list_instances, class_name, page, limit, search
        )
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/entities/{uri}")
async def get_entity(uri: str, project_id: str | None = Query(None, alias="projectId")):
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            ontology_service.ensure_loaded(art.db_path, project_id=project_id)
        return await ontology_service._run(project_id, ontology_service.get_entity, uri)
    except RuntimeError as e:
        # e.g. Ontology not loaded yet (no hydration artifacts)
        raise HTTPException(503, detail=str(e))
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/entities/{uri}/graph")
async def get_entity_graph(uri: str, project_id: str | None = Query(None, alias="projectId")):
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            ontology_service.ensure_loaded(art.db_path, project_id=project_id)
        return await ontology_service._run(project_id, ontology_service.get_entity_graph, uri)
    except RuntimeError as e:
        # e.g. Ontology not loaded yet (no hydration artifacts)
        raise HTTPException(503, detail=str(e))
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/graph")
async def get_full_graph(
    types: str = Query("State,County,Municipality,Individual,Measure"),
    state_fips: Union[str, None] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    project_id: str | None = Query(None, alias="projectId"),
):
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        ontology_service.ensure_loaded(art.db_path, project_id=project_id)
    return await ontology_service._run(
        project_id, ontology_service.get_full_graph, type_list, state_fips, limit
    )


@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=1),
    types: Union[str, None] = Query(None),
    project_id: str | None = Query(None, alias="projectId"),
):
    type_list = [t.strip() for t in types.split(",")] if types else None
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        ontology_service.ensure_loaded(art.db_path, project_id=project_id)
    return await ontology_service._run(project_id, ontology_service.search_entities, q, type_list)


@router.get("/semantic-search")
async def semantic_search_entities(
    q: str = Query(..., min_length=1),
    types: Union[str, None] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None, alias="projectId"),
):
    type_list = [t.strip() for t in types.split(",")] if types else None
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            ontology_service.ensure_loaded(art.db_path, project_id=project_id)
        return await embedding_service.search(q, top_k=limit, types=type_list, project_id=project_id)
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))


@router.get("/series")
async def list_series(project_id: str | None = Query(None, alias="projectId")):
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        ontology_service.ensure_loaded(art.db_path, project_id=project_id)
    return await ontology_service._run(project_id, ontology_service.list_series)


@router.get("/series/{series_id}/data")
async def get_series_data(series_id: str, project_id: str | None = Query(None, alias="projectId")):
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        ontology_service.ensure_loaded(art.db_path, project_id=project_id)
    return await ontology_service._run(project_id, ontology_service.get_series_data, series_id)

@router.get("/schema")
async def get_merged_schema(project: str = Query(..., min_length=1)):
    # This acts as a mock/stub for the frontend merged schema request
    # Since we can't easily reproduce full merge from convex directly here without convex client and engine
    # we'll return a stub for the frontend viewer to handle or return error for now so we know it hits.

    # Let's fetch the ontology config and kernel and return it.
    from app.services.convex_client import convex
    import os
    import yaml

    project_doc = await convex.query("projects:getBySlug", {"slug": project})
    if not project_doc:
        raise HTTPException(404, "Project not found")

    project_onto = "# Project ontology not configured"
    if project_doc.get("ontologyConfigSlug"):
        onto_doc = await convex.query("configs:getOntology", {"slug": project_doc["ontologyConfigSlug"]})
        if onto_doc:
            project_onto = onto_doc.get("content", project_onto)

    kernel_path = os.path.join(os.path.dirname(__file__), "../../../engine/ontology/kernel.yaml")
    kernel_onto = "# Kernel not found"
    if os.path.exists(kernel_path):
        with open(kernel_path, "r") as f:
            kernel_onto = f.read()

    return {
        "yaml": f"{kernel_onto}\n\n# --- Project Extension ---\n\n{project_onto}"
    }
