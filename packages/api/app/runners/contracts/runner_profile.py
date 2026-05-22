"""RunnerProfile — capability declaration for one runner.

One YAML file per registered runner under
packages/api/app/runners/profiles/. The schema here is the validator.

Three-valued capability state (yes/no/configurable/unknown) matters:
several capabilities depend on per-user configuration RAIL cannot infer
(e.g. MCP, web browse), and the router needs to distinguish "definitely
not" from "needs operator setup" from "we haven't probed yet."
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.runners.contracts.work_order import Capability, TaskType


class AdapterType(str, Enum):
    LOCAL_CLI = "local_cli"
    HOSTED_API = "hosted_api"
    ATTACHED_IDE = "attached_ide"


class CertificationStatus(str, Enum):
    """Lifecycle of a runner's certification.

    - experimental: profile exists, probe may pass, but not certified
      end-to-end against the protocol.
    - certified: passed Phase 1-4 verification matrix for at least the
      task types listed in task_affinity above its threshold.
    - advisory_only: usable as an assistant (e.g. Copilot CLI suggest) but
      not autonomous; never enters the router's eligible pool.
    - deprecated: still registered for back-compat, but new work orders
      should not be routed here.
    """

    EXPERIMENTAL = "experimental"
    CERTIFIED = "certified"
    ADVISORY_ONLY = "advisory_only"
    DEPRECATED = "deprecated"


class CapabilityState(str, Enum):
    """Three-valued logic for capability declarations.

    - yes: capability is available without operator setup.
    - no: capability is definitely not available.
    - configurable: available IF the operator has configured it (e.g. MCP
      enabled, credentials present, plugin installed).
    - unknown: probe hasn't run yet or doesn't yet cover this capability.

    The router treats configurable as no for routing decisions until a
    probe confirms it.
    """

    YES = "yes"
    NO = "no"
    CONFIGURABLE = "configurable"
    UNKNOWN = "unknown"


class SteeringMode(str, Enum):
    """How RAIL can redirect a running session.

    - native: the runner exposes a send-message or resume API and accepts
      mid-run instructions without restarting.
    - native_or_relaunch: prefers native steering if a message channel is
      open, falls back to relaunch.
    - relaunch_only: must cancel and dispatch a continuation work order
      with the prior session_result.json as context.
    - attached: only steerable through the user's attached IDE/UI.
    - unsupported: cannot be steered once launched.
    """

    NATIVE = "native"
    NATIVE_OR_RELAUNCH = "native_or_relaunch"
    RELAUNCH_ONLY = "relaunch_only"
    ATTACHED = "attached"
    UNSUPPORTED = "unsupported"


class ExecutionCapabilities(BaseModel):
    """How sessions on this runner behave operationally."""

    model_config = ConfigDict(extra="forbid")

    mode: AdapterType
    supports_streaming: bool
    supports_resume: CapabilityState = CapabilityState.UNKNOWN
    supports_midrun_messages: bool = False
    supports_native_approval: bool = False
    supports_cancel: bool = True
    supports_mcp: CapabilityState = CapabilityState.UNKNOWN
    supports_native_questions: bool = False
    """Whether the runner can emit rail.ask() mid-session. Runners without
    this fall back to the file-based questions.json polling path."""
    steering_mode: SteeringMode = SteeringMode.RELAUNCH_ONLY


class OutputContract(BaseModel):
    """What the runner is required to produce."""

    model_config = ConfigDict(extra="forbid")

    requires_session_result: bool = True
    required_fields: list[str] = Field(
        default_factory=lambda: ["status", "summary", "task_type", "runner_name"]
    )
    """Field names that must be present in session_result.json. Used by the
    Phase 0 test harness for contract validation."""


class RunnerProfile(BaseModel):
    """Per-runner capability declaration. One YAML per runner.

    The router (Phase 5) reads these to decide which runners are eligible
    for a work order. The probe (Phase 1) updates the dynamic checks; the
    static declarations here are authored by hand and reviewed.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    adapter: AdapterType
    default_command: str | None = None
    status: CertificationStatus = CertificationStatus.EXPERIMENTAL

    execution: ExecutionCapabilities
    capabilities: dict[Capability, CapabilityState]
    task_affinity: dict[TaskType, float] = Field(default_factory=dict)
    """0..1 score per task type. Used by the router to rank eligible runners
    when multiple satisfy capability requirements. Seeded by hand, updated
    empirically from the runner scoreboard (Phase 6)."""

    output_contract: OutputContract = Field(default_factory=OutputContract)

    notes: str | None = None
    """Free-form notes — quirks, known issues, special setup, etc.
    Surfaced in the operator UI runner readiness panel."""

    @field_validator("task_affinity")
    @classmethod
    def _task_affinity_in_range(cls, value: dict[TaskType, float]) -> dict[TaskType, float]:
        for task_type, score in value.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"task_affinity[{task_type.value}] = {score} is out of [0, 1]"
                )
        return value

    @field_validator("capabilities")
    @classmethod
    def _capabilities_cover_router_inputs(
        cls, value: dict[Capability, CapabilityState]
    ) -> dict[Capability, CapabilityState]:
        # Don't require exhaustive coverage of every Capability — that would
        # make adding a new Capability a breaking schema change for every
        # profile. But warn-via-error if a profile is suspiciously sparse,
        # since the router falls back to "no" for missing capabilities and
        # that has caused silent routing misses in the past.
        if len(value) == 0:
            raise ValueError(
                "capabilities must declare at least one capability state. "
                "An empty map means the router treats this runner as unable "
                "to do anything, which is almost never the intent."
            )
        return value
