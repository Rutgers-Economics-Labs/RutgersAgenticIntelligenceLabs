"""Small M2 project control-plane HTTP surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.projects.creation import ManagedProjectCreator
from app.projects.registry import ProjectRegistry
from app.projects.runtime import KrailRuntime

from .dtos import (
    ProjectHealthDTO,
    ProjectHealthResponse,
    ProjectListResponse,
    ProjectManifestDTO,
    ProjectManifestResponse,
    ProjectResponse,
    CreateManagedProjectRequest,
    RegisterProjectRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.project_registry


def get_runtime(request: Request) -> KrailRuntime:
    return request.app.state.krail_runtime


def get_managed_project_creator(request: Request) -> ManagedProjectCreator:
    return request.app.state.managed_project_creator


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def register_project(
    payload: RegisterProjectRequest,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> ProjectResponse:
    record = registry.register(
        project_id=payload.project_id,
        display_name=payload.display_name,
        path=payload.path,
        workspace_mode=payload.workspace_mode,
        runtime=runtime,
    )
    return ProjectResponse.from_record(record)


@router.post("/managed", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_managed_project(
    payload: CreateManagedProjectRequest,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
    creator: ManagedProjectCreator = Depends(get_managed_project_creator),
) -> ProjectResponse:
    record = creator.create(
        registry=registry,
        runtime=runtime,
        project_id=payload.project_id,
        display_name=payload.display_name,
        name=payload.name,
        slug=payload.slug,
        pack=payload.pack,
        mode=payload.mode,
        knowledge_mode=payload.knowledge_mode,
    )
    return ProjectResponse.from_record(record)


@router.get("", response_model=ProjectListResponse)
def list_projects(registry: ProjectRegistry = Depends(get_registry)) -> ProjectListResponse:
    return ProjectListResponse(projects=[ProjectResponse.from_record(item) for item in registry.list()])


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, registry: ProjectRegistry = Depends(get_registry)) -> ProjectResponse:
    return ProjectResponse.from_record(registry.get(project_id))


@router.get("/{project_id}/health", response_model=ProjectHealthResponse)
def get_project_health(
    project_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> ProjectHealthResponse:
    record = registry.get(project_id)
    health = runtime.doctor(registry.project_ref(record))
    return ProjectHealthResponse(project_id=record.project_id, health=ProjectHealthDTO.from_runtime(health))


@router.get("/{project_id}/manifest", response_model=ProjectManifestResponse)
def get_project_manifest(
    project_id: str,
    registry: ProjectRegistry = Depends(get_registry),
    runtime: KrailRuntime = Depends(get_runtime),
) -> ProjectManifestResponse:
    record = registry.get(project_id)
    manifest = runtime.manifest(registry.project_ref(record))
    return ProjectManifestResponse(
        project_id=record.project_id,
        manifest=ProjectManifestDTO.from_runtime(manifest),
    )
