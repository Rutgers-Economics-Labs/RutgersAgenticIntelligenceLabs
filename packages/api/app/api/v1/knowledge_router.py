"""Read-only knowledge API backed exclusively by the KRAIL runtime boundary."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import StringConstraints

from app.krail_runtime.contracts import KrailRuntime
from app.projects.registry import ProjectRegistry

from .knowledge_dtos import (
    ApprovalInventoryResponse,
    ApprovalResponse,
    FindRequest,
    FindResponse,
    GraphRequest,
    GraphResponse,
    IntegrityResponse,
    SourceCheckResponse,
    SourceImpactResponse,
    SourceInventoryResponse,
    WorkflowInventoryResponse,
)
from .router import get_registry, get_runtime


router = APIRouter(prefix="/projects/{project_id}", tags=["knowledge"])

ProjectId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
RecordId = Annotated[str, Path(min_length=1, max_length=200)]
SourceId = Annotated[str, StringConstraints(min_length=1, max_length=200)]


def _project(project_id: str, registry: ProjectRegistry):
    record = registry.get(project_id)
    return record, registry.project_ref(record)


@router.post("/find", response_model=FindResponse)
def find_knowledge(
    project_id: ProjectId,
    payload: FindRequest,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> FindResponse:
    record, project = _project(project_id, registry)
    return FindResponse.from_runtime(record.project_id, runtime.find(project, payload.to_runtime()))


@router.get("/graph", response_model=GraphResponse)
def query_graph(
    project_id: ProjectId,
    query: Annotated[GraphRequest, Query()],
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> GraphResponse:
    record, project = _project(project_id, registry)
    return GraphResponse.from_runtime(record.project_id, runtime.graph(project, query.to_runtime()))


@router.get("/sources", response_model=SourceInventoryResponse)
def source_inventory(
    project_id: ProjectId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> SourceInventoryResponse:
    record, project = _project(project_id, registry)
    return SourceInventoryResponse.from_runtime(record.project_id, runtime.sources(project))


@router.post("/sources/check", response_model=SourceCheckResponse)
def check_sources(
    project_id: ProjectId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> SourceCheckResponse:
    record, project = _project(project_id, registry)
    return SourceCheckResponse.from_runtime(record.project_id, runtime.check_sources(project))


@router.get("/sources/affected", response_model=SourceImpactResponse)
def affected_documents(
    project_id: ProjectId,
    source_ids: Annotated[list[SourceId] | None, Query(alias="sourceId", max_length=50)] = None,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> SourceImpactResponse:
    record, project = _project(project_id, registry)
    return SourceImpactResponse.from_runtime(record.project_id, runtime.affected_sources(project, source_ids))


@router.get("/integrity", response_model=IntegrityResponse)
def integrity_summary(
    project_id: ProjectId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> IntegrityResponse:
    record, project = _project(project_id, registry)
    return IntegrityResponse.from_runtime(record.project_id, runtime.integrity(project))


@router.get("/workflows", response_model=WorkflowInventoryResponse)
def workflow_inventory(
    project_id: ProjectId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> WorkflowInventoryResponse:
    record, project = _project(project_id, registry)
    return WorkflowInventoryResponse.from_runtime(record.project_id, runtime.workflows(project))


@router.get("/approvals", response_model=ApprovalInventoryResponse)
def approval_inventory(
    project_id: ProjectId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> ApprovalInventoryResponse:
    record, project = _project(project_id, registry)
    return ApprovalInventoryResponse.from_runtime(record.project_id, runtime.approvals(project))


@router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
def approval_detail(
    project_id: ProjectId,
    approval_id: RecordId,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> ApprovalResponse:
    record, project = _project(project_id, registry)
    return ApprovalResponse.from_runtime(record.project_id, runtime.approval(project, approval_id))
