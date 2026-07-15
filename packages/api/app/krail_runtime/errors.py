"""Typed platform errors translated from KRAIL exceptions."""

from __future__ import annotations


class KrailRuntimeError(RuntimeError):
    code = "krail_runtime_error"

    def __init__(self, message: str, *, operation: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.operation = operation
        self.cause = cause


class KrailUnavailableError(KrailRuntimeError):
    code = "krail_unavailable"


class KrailShadowingError(KrailUnavailableError):
    code = "krail_namespace_shadowed"


class KrailProjectNotFoundError(KrailRuntimeError):
    code = "krail_project_not_found"


class KrailValidationError(KrailRuntimeError):
    code = "krail_validation_failed"


class KrailRecordNotFoundError(KrailRuntimeError):
    code = "krail_record_not_found"


class KrailPermissionError(KrailRuntimeError):
    code = "krail_permission_denied"


class KrailCapabilityGapError(KrailRuntimeError):
    code = "krail_capability_gap"
