"""RAIL-owned execution metadata; never a mirror of KRAIL project state."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FilesystemMode(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class PermissionProfile(BaseModel):
    """Explicit execution authority. Empty allowlists grant no authority."""

    model_config = ConfigDict(frozen=True)
    name: str
    allowed_commands: frozenset[str] = Field(default_factory=frozenset)
    denied_commands: frozenset[str] = Field(default_factory=frozenset)
    filesystem_roots: tuple[Path, ...] = ()
    filesystem_mode: FilesystemMode = FilesystemMode.READ_ONLY
    environment_allowlist: frozenset[str] = Field(default_factory=frozenset)
    network_enabled: bool = False
    process_enabled: bool = False
    shell_enabled: bool = False
    timeout_seconds: float = Field(default=60, gt=0, le=86_400)
    max_concurrency: int = Field(default=1, ge=1, le=128)

    @model_validator(mode="after")
    def explicit_full_access_only(self) -> "PermissionProfile":
        if self.name != "full-access" and not self.filesystem_roots and self.filesystem_mode == FilesystemMode.READ_WRITE:
            raise ValueError("read-write access requires explicit filesystem roots")
        return self

    @classmethod
    def full_access(cls, *, timeout_seconds: float = 3600, max_concurrency: int = 1) -> "PermissionProfile":
        """The only opt-in profile that deliberately grants unrestricted authority."""
        return cls(
            name="full-access", allowed_commands=frozenset({"*"}), filesystem_roots=(Path("/"),),
            filesystem_mode=FilesystemMode.READ_WRITE, environment_allowlist=frozenset({"*"}),
            network_enabled=True, process_enabled=True, shell_enabled=True,
            timeout_seconds=timeout_seconds, max_concurrency=max_concurrency,
        )


class RunEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    kind: str
    message: str
    at: datetime = Field(default_factory=utc_now)
    data: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    project_path: Path
    kind: str
    status: RunStatus = RunStatus.QUEUED
    permission_profile: str
    baseline_commit: str | None = None
    worktree_path: Path | None = None
    workflow_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    result: dict[str, Any] = Field(default_factory=dict)
