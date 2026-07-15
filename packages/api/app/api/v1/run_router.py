"""Project-scoped asynchronous KRAIL workflow runs and event streams."""
from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, status
from fastapi.responses import StreamingResponse

from app.execution.models import RunStatus, TERMINAL_STATUSES
from app.execution.profile_registry import PermissionProfileRegistry
from app.execution.service import ExecutionService
from app.execution.supervisor import LocalRunSupervisor
from app.krail_runtime.contracts import RunRequest
from app.projects.errors import PlatformError
from app.projects.registry import ProjectRegistry

from .router import get_registry
from .run_dtos import CreateWorkflowRunRequest, RunDTO, RunEventDTO, RunEventsResponse, RunListResponse, RunResponse

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])
ProjectId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]


class RunNotFoundError(PlatformError):
    status_code = 404
    code = "run_not_found"


class RunPermissionError(PlatformError):
    status_code = 403
    code = "execution_permission_denied"


class ProjectReadOnlyError(PlatformError):
    status_code = 403
    code = "project_read_only"


def get_execution(request: Request) -> ExecutionService:
    return request.app.state.execution_service


def get_profiles(request: Request) -> PermissionProfileRegistry:
    return request.app.state.permission_profiles


def get_supervisor(request: Request) -> LocalRunSupervisor:
    return request.app.state.run_supervisor


def _run_for_project(service: ExecutionService, project_id: str, run_id: str):
    try:
        record = service.store.get(run_id)
    except KeyError as exc:
        raise RunNotFoundError("Run was not found") from exc
    if record.project_id != project_id:
        raise RunNotFoundError("Run was not found")
    return record


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_workflow_run(project_id: ProjectId, payload: CreateWorkflowRunRequest,
                        registry: ProjectRegistry = Depends(get_registry), service: ExecutionService = Depends(get_execution),
                        profiles: PermissionProfileRegistry = Depends(get_profiles), supervisor: LocalRunSupervisor = Depends(get_supervisor)) -> RunResponse:
    project = registry.get(project_id)
    try:
        profile = profiles.select(payload.permission_profile, dry_run=payload.dry_run)
    except PermissionError as exc:
        raise RunPermissionError(str(exc)) from exc
    if project.access.value == "read_only" and not payload.dry_run:
        raise ProjectReadOnlyError("Registered project is read-only")
    record = service.create_run(project_id=project.project_id, project_path=registry.project_ref(project).path, kind="workflow",
        profile=profile, baseline_commit=project.git.baseline_commit, workflow_id=payload.workflow_id,
        project_read_only=project.access.value == "read_only")
    # Dry-run is operational request metadata, not a client-controlled profile field.
    service.store.replace(record.model_copy(update={"result": {"dryRun": payload.dry_run}}))
    request = RunRequest(workflow_id=payload.workflow_id, dry_run=payload.dry_run, force=payload.force, inputs=payload.inputs)
    supervisor.submit_workflow(record.run_id, request)
    return RunResponse(run=RunDTO.from_record(service.store.get(record.run_id)))


@router.get("", response_model=RunListResponse)
def list_runs(project_id: ProjectId, registry: ProjectRegistry = Depends(get_registry), service: ExecutionService = Depends(get_execution)) -> RunListResponse:
    registry.get(project_id)
    return RunListResponse(runs=[RunDTO.from_record(r) for r in service.store.records() if r.project_id == project_id])


@router.get("/{run_id}", response_model=RunResponse)
def get_run(project_id: ProjectId, run_id: str, service: ExecutionService = Depends(get_execution)) -> RunResponse:
    return RunResponse(run=RunDTO.from_record(_run_for_project(service, project_id, run_id)))


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(project_id: ProjectId, run_id: str, service: ExecutionService = Depends(get_execution)) -> RunResponse:
    _run_for_project(service, project_id, run_id)
    return RunResponse(run=RunDTO.from_record(service.cancel(run_id)))


@router.get("/{run_id}/events", response_model=RunEventsResponse)
def event_snapshot(project_id: ProjectId, run_id: str, service: ExecutionService = Depends(get_execution)) -> RunEventsResponse:
    _run_for_project(service, project_id, run_id)
    return RunEventsResponse(events=[RunEventDTO.from_event(event) for event in service.events(run_id)])


@router.get("/{run_id}/events/stream")
async def event_stream(project_id: ProjectId, run_id: str, request: Request,
                       last_event_id: Annotated[str | None, Header()] = None,
                       service: ExecutionService = Depends(get_execution)) -> StreamingResponse:
    _run_for_project(service, project_id, run_id)
    async def generate():
        cursor = 0
        if last_event_id:
            found = [i for i, event in enumerate(service.events(run_id)) if event.event_id == last_event_id]
            cursor = found[-1] + 1 if found else 0
        while True:
            events = service.events(run_id)
            while cursor < len(events):
                event = events[cursor]; cursor += 1
                payload = json.dumps(RunEventDTO.from_event(event).model_dump(mode="json", by_alias=True), separators=(",", ":"))
                yield f"id: {event.event_id}\nevent: {event.kind}\ndata: {payload}\n\n"
            record = _run_for_project(service, project_id, run_id)
            if record.status in TERMINAL_STATUSES:
                return
            if await request.is_disconnected():
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
