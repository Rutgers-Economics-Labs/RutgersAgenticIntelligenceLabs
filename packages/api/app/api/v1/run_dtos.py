"""Public, project-scoped workflow-run HTTP contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.execution.models import RunEvent, RunRecord, RunStatus


class RunDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias="runId")
    project_id: str = Field(alias="projectId")
    workflow_id: str | None = Field(alias="workflowId")
    status: RunStatus
    dry_run: bool = Field(alias="dryRun")
    permission_profile: str = Field(alias="permissionProfile")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    result: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: RunRecord) -> "RunDTO":
        return cls(runId=record.run_id, projectId=record.project_id, workflowId=record.workflow_id,
                   status=record.status, dryRun=bool(record.result.get("dryRun", True)),
                   permissionProfile=record.permission_profile.name, createdAt=record.created_at,
                   updatedAt=record.updated_at, result={k: v for k, v in record.result.items() if k != "dryRun"})


class RunEventDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    event_id: str = Field(alias="eventId")
    run_id: str = Field(alias="runId")
    kind: str
    message: str
    at: datetime
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: RunEvent) -> "RunEventDTO":
        return cls(eventId=event.event_id, runId=event.run_id, kind=event.kind, message=event.message, at=event.at, data=event.data)


class CreateWorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    workflow_id: str = Field(alias="workflowId", min_length=1, max_length=200)
    dry_run: bool = Field(default=True, alias="dryRun")
    force: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)
    permission_profile: str | None = Field(default=None, alias="permissionProfile", max_length=80)


class RunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run: RunDTO


class RunListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    runs: list[RunDTO]


class RunEventsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    events: list[RunEventDTO]
