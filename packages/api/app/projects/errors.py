"""Typed errors exposed by the project control plane."""
from __future__ import annotations


class PlatformError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProjectNotFoundError(PlatformError):
    status_code = 404
    code = "project_not_found"


class ProjectConflictError(PlatformError):
    status_code = 409
    code = "project_conflict"


class WorkspacePolicyError(PlatformError):
    status_code = 403
    code = "workspace_access_denied"


class WorkspaceValidationError(PlatformError):
    status_code = 422
    code = "workspace_invalid"


class RuntimeUnavailableError(PlatformError):
    status_code = 503
    code = "runtime_unavailable"
