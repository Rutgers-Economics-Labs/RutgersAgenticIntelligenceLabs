"""KRAIL-first RAIL platform API bootstrap (M2)."""
from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.krail_runtime import LocalKrailRuntime
from app.krail_runtime.errors import (
    KrailCapabilityGapError,
    KrailPermissionError,
    KrailProjectNotFoundError,
    KrailRuntimeError,
    KrailUnavailableError,
    KrailValidationError,
)
from app.api.v1.dtos import ErrorDTO, ErrorEnvelope
from app.api.v1.knowledge_router import router as knowledge_router
from app.api.v1.capabilities_router import router as capabilities_router
from app.api.v1.router import router as projects_router
from app.api.v1.run_router import router as runs_router
from app.execution import (
    CommandExecutor,
    ExecutionService,
    InMemoryRunStore,
    JsonRunStore,
    LocalRunSupervisor,
    PermissionProfileRegistry,
)
from app.execution.sandbox import SandboxUnavailableError, detect_capability, select_sandbox
from app.projects.errors import PlatformError
from app.projects.creation import ManagedProjectCreator
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


def _operator_flag(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_workers() -> int:
    raw = os.environ.get("RAIL_RUN_MAX_WORKERS", "4")
    try:
        workers = int(raw)
    except ValueError as exc:
        raise ValueError("RAIL_RUN_MAX_WORKERS must be an integer") from exc
    if not 1 <= workers <= 32:
        raise ValueError("RAIL_RUN_MAX_WORKERS must be between 1 and 32")
    return workers


def create_app(
    *,
    registry_config: RegistryConfig | None = None,
    runtime: KrailRuntime | None = None,
    run_store: InMemoryRunStore | None = None,
    permission_profiles: PermissionProfileRegistry | None = None,
    managed_project_creator: ManagedProjectCreator | None = None,
    max_run_workers: int | None = None,
) -> FastAPI:
    """Build an injectable API app without importing legacy routers or KRAIL directly."""

    configured_runtime = runtime or LocalKrailRuntime()
    configured_store = run_store or JsonRunStore(
        Path(os.environ.get("RAIL_RUN_STORE_PATH", ".rail/platform-runs.json"))
    )
    execution_service = ExecutionService(configured_store, configured_runtime)
    profiles = permission_profiles or PermissionProfileRegistry(
        full_access_enabled=_operator_flag("RAIL_FULL_ACCESS_ENABLED")
    )
    supervisor = LocalRunSupervisor(
        execution_service,
        max_workers=max_run_workers if max_run_workers is not None else _run_workers(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            # Let accepted local work reach a durable terminal state before the
            # process exits. Restart recovery still fail-closes interrupted runs.
            supervisor.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="RAIL Platform API", version="1.0.0", lifespan=lifespan)
    app.state.project_registry = ProjectRegistry(registry_config or RegistryConfig.from_environment())
    app.state.krail_runtime = configured_runtime
    app.state.execution_service = execution_service
    app.state.permission_profiles = profiles
    app.state.run_supervisor = supervisor
    app.state.managed_project_creator = managed_project_creator or ManagedProjectCreator()

    # Restricted commands always flow through an enforcing provider when one is
    # available. CommandExecutor itself rejects restricted execution if local OS
    # enforcement is unavailable; full access remains separately operator-gated.
    app.state.sandbox_capability = detect_capability()
    try:
        sandbox = select_sandbox()
    except SandboxUnavailableError:
        sandbox = None
    app.state.command_executor = CommandExecutor(sandbox)

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
        if isinstance(exc, KrailCapabilityGapError):
            status_code = 501
        elif isinstance(exc, KrailUnavailableError):
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
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(capabilities_router, prefix="/api/v1")
    return app


app = create_app()
