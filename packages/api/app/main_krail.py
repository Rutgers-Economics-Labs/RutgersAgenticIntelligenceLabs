"""KRAIL-first RAIL platform API bootstrap (M2)."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.krail_runtime import LocalKrailRuntime
from app.krail_runtime.errors import (
    KrailPermissionError,
    KrailProjectNotFoundError,
    KrailRuntimeError,
    KrailUnavailableError,
    KrailValidationError,
)
from app.api.v1.dtos import ErrorDTO, ErrorEnvelope
from app.api.v1.router import router as projects_router
from app.projects.errors import PlatformError
from app.projects.registry import ProjectRegistry, RegistryConfig
from app.projects.runtime import KrailRuntime


def _error_response(request: Request, *, status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    envelope = ErrorEnvelope(
        error=ErrorDTO(code=code, message=message, request_id=request_id, details=details or {})
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json", by_alias=True),
        headers={"X-Request-ID": request_id},
    )


def create_app(
    *,
    registry_config: RegistryConfig | None = None,
    runtime: KrailRuntime | None = None,
) -> FastAPI:
    """Build an injectable API app without importing legacy routers or KRAIL directly."""

    app = FastAPI(title="RAIL Platform API", version="1.0.0")
    app.state.project_registry = ProjectRegistry(registry_config or RegistryConfig.from_environment())
    app.state.krail_runtime = runtime or LocalKrailRuntime()

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(PlatformError)
    async def platform_error_handler(request: Request, exc: PlatformError):
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return _error_response(
            request,
            status_code=422,
            code="request_validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
        )

    @app.exception_handler(KrailRuntimeError)
    async def krail_error_handler(request: Request, exc: KrailRuntimeError):
        if isinstance(exc, KrailUnavailableError):
            status_code = 503
        elif isinstance(exc, KrailProjectNotFoundError):
            status_code = 404
        elif isinstance(exc, KrailValidationError):
            status_code = 422
        elif isinstance(exc, KrailPermissionError):
            status_code = 403
        else:
            status_code = 502
        return _error_response(
            request,
            status_code=status_code,
            code=exc.code,
            message=str(exc),
            details={"operation": exc.operation},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Internal adapter and filesystem failures remain structured without
        # disclosing implementation details to browser clients.
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Internal server error",
        )

    @app.get("/health")
    def service_health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects_router, prefix="/api/v1")
    return app


app = create_app()
