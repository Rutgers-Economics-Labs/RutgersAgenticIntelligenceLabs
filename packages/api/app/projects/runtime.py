"""The injectable boundary between RAIL control-plane code and KRAIL."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .errors import RuntimeUnavailableError


class ProjectRef(BaseModel):
    """A permission-scoped project location passed to the KRAIL adapter."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    canonical_path: str
    read_only: bool


class HealthCheck(BaseModel):
    name: str
    status: str
    message: str | None = None


class ProjectHealth(BaseModel):
    """RAIL's stable, adapter-mapped health contract."""

    status: str
    summary: str | None = None
    checks: list[HealthCheck] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"


class ProjectManifest(BaseModel):
    """RAIL's stable manifest view; never a pass-through KRAIL dictionary."""

    project_name: str
    schema_version: str | None = None
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)


@runtime_checkable
class KrailRuntime(Protocol):
    """Minimal M2 runtime surface; concrete adapters live at the KRAIL boundary."""

    def doctor(self, project: ProjectRef) -> ProjectHealth: ...

    def manifest(self, project: ProjectRef) -> ProjectManifest: ...


class UnavailableKrailRuntime:
    """Safe bootstrap default until a concrete KRAIL adapter is configured."""

    def doctor(self, project: ProjectRef) -> ProjectHealth:
        raise RuntimeUnavailableError("No KRAIL runtime adapter has been configured")

    def manifest(self, project: ProjectRef) -> ProjectManifest:
        raise RuntimeUnavailableError("No KRAIL runtime adapter has been configured")
