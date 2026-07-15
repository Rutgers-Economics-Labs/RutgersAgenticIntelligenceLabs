"""Models for RAIL-owned project operational metadata.

These records deliberately contain no KRAIL manifest, ontology, source, or workflow
state.  That state remains in the registered project directory and is read through
the runtime adapter when requested.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceMode(StrEnum):
    MANAGED = "managed"
    LINKED_LOCAL = "linked_local"


class WorkspaceAccess(StrEnum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class GitMetadata(BaseModel):
    """A registration-time Git baseline, not a mirror of repository content."""

    model_config = ConfigDict(frozen=True)

    is_repository: bool
    repository_root: str | None = None
    head_commit: str | None = None
    branch: str | None = None
    is_dirty: bool = False
    baseline_commit: str | None = None
    baseline_recorded_at: datetime | None = None


class ProjectRecord(BaseModel):
    """Persistent single-node registry record containing operational metadata only."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    display_name: str
    canonical_path: str
    workspace_mode: WorkspaceMode
    access: WorkspaceAccess
    git: GitMetadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def storage_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
