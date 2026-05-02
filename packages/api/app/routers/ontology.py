from typing import Union
from fastapi import APIRouter, HTTPException, Query
from app.services import embedding_service, ontology_service
from app.services import project_artifacts_service

router = APIRouter(prefix="/ontology", tags=["ontology"])


def _handle_artifact_error(e: Exception) -> None:
    """Re-raise ontology load errors as appropriate HTTP exceptions."""
    if isinstance(e, FileNotFoundError):
        raise HTTPException(
            status_code=428,
            detail=f"Ontology artifacts missing from disk. Re-run hydration to regenerate them. ({e})",
        )
    raise e


@router.get("/classes")
async def list_classes(project_id: str | None = Query(None, alias="projectId")):
    try:
        if project_id:
            art = await project_artifacts_service.resolve(project_id)
            items = await ontology_service._run_with_ensure(
                project_id, art.db_path, ontology_service.list_classes
            )
            return {"classes": items}
        items = await ontology_service._run(project_id, ontology_service.list_classes)
        return {"classes": items}
    except Exception as e:
        _handle_artifact_error(e)


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
            return await ontology_service._run_with_ensure(
                project_id,
                art.db_path,
                ontology_service.list_instances,
                class_name,
                page,
                limit,
                search,
            )
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
            return await ontology_service._run_with_ensure(
                project_id, art.db_path, ontology_service.get_entity, uri
            )
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
            return await ontology_service._run_with_ensure(
                project_id, art.db_path, ontology_service.get_entity_graph, uri
            )
        return await ontology_service._run(project_id, ontology_service.get_entity_graph, uri)
    except RuntimeError as e:
        # e.g. Ontology not loaded yet (no hydration artifacts)
        raise HTTPException(503, detail=str(e))
    except ValueError as e:
        raise HTTPException(404, detail=str(e))


@router.get("/graph")
async def get_full_graph(
    types: str = Query("Observation,DataCenterFacilities,LoadZones,Electricutilities,Geography,Measure"),
    state_fips: Union[str, None] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    project_id: str | None = Query(None, alias="projectId"),
):
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        return await ontology_service._run_with_ensure(
            project_id,
            art.db_path,
            ontology_service.get_full_graph,
            type_list,
            state_fips,
            limit,
        )
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
        return await ontology_service._run_with_ensure(
            project_id, art.db_path, ontology_service.search_entities, q, type_list
        )
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
            await ontology_service.ensure_loaded_async(art.db_path, project_id=project_id)
        return await embedding_service.search(q, top_k=limit, types=type_list, project_id=project_id)
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))


@router.get("/series")
async def list_series(project_id: str | None = Query(None, alias="projectId")):
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        return await ontology_service._run_with_ensure(
            project_id, art.db_path, ontology_service.list_series
        )
    return await ontology_service._run(project_id, ontology_service.list_series)


@router.get("/series/{series_id}/data")
async def get_series_data(series_id: str, project_id: str | None = Query(None, alias="projectId")):
    if project_id:
        art = await project_artifacts_service.resolve(project_id)
        return await ontology_service._run_with_ensure(
            project_id, art.db_path, ontology_service.get_series_data, series_id
        )
    return await ontology_service._run(project_id, ontology_service.get_series_data, series_id)
