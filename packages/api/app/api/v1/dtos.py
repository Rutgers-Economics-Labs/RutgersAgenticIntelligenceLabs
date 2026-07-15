"""Versioned RAIL-owned DTOs for project control-plane endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.projects.models import GitMetadata, ProjectRecord, WorkspaceAccess, WorkspaceMode
from app.projects.runtime import ProjectHealth, ProjectManifest


class DTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class RegisterProjectRequest(DTO):
    project_id: str | None = Field(
        default=None,
        alias="projectId",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    display_name: str = Field(alias="displayName", min_length=1, max_length=256)
    path: str = Field(min_length=1)
    workspace_mode: WorkspaceMode = Field(alias="workspaceMode")


class CreateManagedProjectRequest(DTO):
    """Identifiers and KRAIL init options only; the server derives the path."""

    project_id: str = Field(alias="projectId", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    display_name: str = Field(alias="displayName", min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    pack: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    mode: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    knowledge_mode: str = Field(alias="knowledgeMode", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class GitResponse(DTO):
    is_repository: bool = Field(alias="isRepository")
    repository_root: str | None = Field(default=None, alias="repositoryRoot")
    head_commit: str | None = Field(default=None, alias="headCommit")
    branch: str | None = None
    is_dirty: bool = Field(alias="isDirty")
    baseline_commit: str | None = Field(default=None, alias="baselineCommit")
    baseline_recorded_at: datetime | None = Field(default=None, alias="baselineRecordedAt")

    @classmethod
    def from_model(cls, git: GitMetadata) -> "GitResponse":
        return cls(**git.model_dump())


class ProjectResponse(DTO):
    project_id: str = Field(alias="projectId")
    display_name: str = Field(alias="displayName")
    canonical_path: str = Field(alias="canonicalPath")
    workspace_mode: WorkspaceMode = Field(alias="workspaceMode")
    access: WorkspaceAccess
    git: GitResponse
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_record(cls, record: ProjectRecord) -> "ProjectResponse":
        data = record.model_dump()
        data["git"] = GitResponse.from_model(record.git)
        return cls(**data)


class ProjectListResponse(DTO):
    projects: list[ProjectResponse]


class HealthCheckResponse(DTO):
    name: str
    ok: bool
    detail: str


class ProjectHealthDTO(DTO):
    ok: bool
    checks: list[HealthCheckResponse]
    warnings: list[str]
    krail_version: str = Field(alias="krailVersion")

    @classmethod
    def from_runtime(cls, health: ProjectHealth) -> "ProjectHealthDTO":
        return cls(**health.model_dump())


class ProjectHealthResponse(DTO):
    project_id: str = Field(alias="projectId")
    health: ProjectHealthDTO


class ProjectManifestDTO(DTO):
    version: int
    slug: str
    name: str
    default_branch: str = Field(alias="defaultBranch")
    knowledge_mode: str = Field(alias="knowledgeMode")
    paths: dict[str, str]

    @classmethod
    def from_runtime(cls, manifest: ProjectManifest) -> "ProjectManifestDTO":
        return cls(**manifest.model_dump())


class ProjectManifestResponse(DTO):
    project_id: str = Field(alias="projectId")
    manifest: ProjectManifestDTO


class ErrorDTO(DTO):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    details: dict = Field(default_factory=dict)


class ErrorEnvelope(DTO):
    error: ErrorDTO
