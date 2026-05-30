"""Autopilot kill-switch endpoints — emergency stop for the whole platform."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.services import kill_switch_service

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.post("/kill-all")
async def kill_all(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Engage the GLOBAL kill switch.

    Every active autopilot loop is signalled to stop, every in-flight runner
    subprocess is cancelled, and the persisted flag prevents any new autopilot
    from starting until released.

    Body (optional): ``{"reason": "...", "engagedBy": "..."}``.
    """
    reason = payload.get("reason") if isinstance(payload, dict) else None
    engaged_by = payload.get("engagedBy") if isinstance(payload, dict) else None
    return await kill_switch_service.engage_global(reason=reason, engaged_by=engaged_by)


@router.post("/release-all")
async def release_all() -> dict[str, Any]:
    """Release the global kill switch. Per-project kills are not affected."""
    return await kill_switch_service.release_global()


@router.get("/kill-status")
async def kill_status() -> dict[str, Any]:
    """Snapshot of the global flag and every per-project kill currently engaged."""
    return kill_switch_service.status()
