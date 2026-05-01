from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROLE_ACTIVITY_KEYS = {
    "planner": "plan_decomposition",
    "research": "source_discovery",
    "data": "data_ingestion",
    "coding": "analysis_scripts",
    "artifact": "artifact_generation",
    "health": "verification",
}

PUBLISH_BOUNDARY_ACTIONS = {"publish_changes", "merge_changes", "create_pull_request"}


@dataclass(frozen=True)
class AutonomyDecision:
    mode: str
    action: str
    write_capable: bool
    allowed: bool
    requires_human_approval: bool
    blocked: bool
    status: str
    reason: str
    boundary: str | None = None


def activity_key_for_role(role: str) -> str:
    return ROLE_ACTIVITY_KEYS.get(role, "analysis_scripts")


def is_write_capable(*, role_policy: Any, allowed_paths: list[str] | None = None) -> bool:
    return bool((getattr(role_policy.paths, "write", None) or []) or (allowed_paths or []))


def evaluate_autonomy_policy(
    manifest: Any,
    *,
    action: str,
    write_capable: bool,
    integrity_blocked: bool = False,
    budget_exceeded: bool = False,
    runtime_exceeded: bool = False,
) -> AutonomyDecision:
    autonomy = getattr(manifest, "autonomy", None)
    mode = getattr(autonomy, "mode", "assisted")
    require_human_for = set(getattr(autonomy, "require_human_for", []) or [])
    allow_without_human = set(getattr(autonomy, "allow_without_human", []) or [])

    if integrity_blocked:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=False,
            blocked=True,
            status="blocked",
            reason="Integrity gates blocked this action.",
            boundary="integrity_gate",
        )

    if budget_exceeded:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=False,
            blocked=True,
            status="blocked",
            reason="Autonomy budget exceeded.",
            boundary="budget_exceeded",
        )

    if runtime_exceeded:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=False,
            blocked=True,
            status="blocked",
            reason="Autonomy runtime limit exceeded.",
            boundary="runtime_exceeded",
        )

    if action in PUBLISH_BOUNDARY_ACTIONS:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=True,
            blocked=False,
            status="awaiting_approval",
            reason="Publish and merge actions require a human review boundary.",
            boundary="publish_changes",
        )

    if mode == "assisted" and write_capable:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=True,
            blocked=False,
            status="awaiting_approval",
            reason="Assisted mode requires approval before write-capable worker runs.",
            boundary="write_capable_run",
        )

    if action in require_human_for:
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=True,
            blocked=False,
            status="awaiting_approval",
            reason=f"Autonomy policy requires human approval for `{action}`.",
            boundary=action,
        )

    if mode in {"supervised_autopilot", "autopilot"}:
        if not write_capable:
            return AutonomyDecision(
                mode=mode,
                action=action,
                write_capable=write_capable,
                allowed=True,
                requires_human_approval=False,
                blocked=False,
                status="ready",
                reason="Read-only work may proceed automatically.",
            )
        if action in allow_without_human:
            return AutonomyDecision(
                mode=mode,
                action=action,
                write_capable=write_capable,
                allowed=True,
                requires_human_approval=False,
                blocked=False,
                status="ready",
                reason=f"Autonomy policy allows `{action}` without human approval.",
            )
        return AutonomyDecision(
            mode=mode,
            action=action,
            write_capable=write_capable,
            allowed=False,
            requires_human_approval=True,
            blocked=False,
            status="awaiting_approval",
            reason=f"`{action}` is outside the routine autopilot allowlist.",
            boundary=action,
        )

    return AutonomyDecision(
        mode=mode,
        action=action,
        write_capable=write_capable,
        allowed=True,
        requires_human_approval=False,
        blocked=False,
        status="ready",
        reason="Autonomy policy allows this action.",
    )
