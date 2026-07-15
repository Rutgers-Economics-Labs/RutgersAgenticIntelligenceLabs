"""RAIL-owned operator inventory for execution profiles and sandbox support."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.execution.profile_registry import PermissionProfileRegistry
from app.execution.sandbox.capabilities import SandboxCapability


class CapabilityDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class ExecutionProfileCapability(CapabilityDTO):
    name: str
    enabled: bool
    dry_run_only: bool = Field(alias="dryRunOnly")
    filesystem_mode: str = Field(alias="filesystemMode")
    network_enabled: bool = Field(alias="networkEnabled")
    process_enabled: bool = Field(alias="processEnabled")
    shell_enabled: bool = Field(alias="shellEnabled")
    timeout_seconds: float = Field(alias="timeoutSeconds")
    max_concurrency: int = Field(alias="maxConcurrency")


class SandboxCapabilityResponse(CapabilityDTO):
    provider: str
    available: bool
    reason: str | None = None
    filesystem_enforcement: bool = Field(alias="filesystemEnforcement")
    network_enforcement: bool = Field(alias="networkEnforcement")
    portability_note: str | None = Field(alias="portabilityNote")


class ExecutionCapabilityInventory(CapabilityDTO):
    profiles: list[ExecutionProfileCapability]
    sandbox: SandboxCapabilityResponse


router = APIRouter(prefix="/operator", tags=["operator"])


@router.get("/execution-capabilities", response_model=ExecutionCapabilityInventory)
def execution_capabilities(request: Request) -> ExecutionCapabilityInventory:
    profiles: PermissionProfileRegistry = request.app.state.permission_profiles
    sandbox: SandboxCapability = request.app.state.sandbox_capability
    inventory = [
        ExecutionProfileCapability(
            name=profile.name,
            enabled=profile.name != "full-access" or profiles.full_access_enabled,
            dryRunOnly=profile.name != "full-access",
            filesystemMode=profile.filesystem_mode.value,
            networkEnabled=profile.network_enabled,
            processEnabled=profile.process_enabled,
            shellEnabled=profile.shell_enabled,
            timeoutSeconds=profile.timeout_seconds,
            maxConcurrency=profile.max_concurrency,
        )
        for profile in profiles.profiles()
    ]
    return ExecutionCapabilityInventory(
        profiles=inventory,
        sandbox=SandboxCapabilityResponse(
            provider=sandbox.provider,
            available=sandbox.available,
            reason=sandbox.reason,
            filesystemEnforcement=sandbox.filesystem_enforcement,
            networkEnforcement=sandbox.network_enforcement,
            portabilityNote=sandbox.portability_note,
        ),
    )
