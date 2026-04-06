from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.convex_client import convex
from app.services.scheduler_service import parse_frequency, parse_window
import time

router = APIRouter(prefix="/schedules", tags=["schedules"])

class CreateScheduleRequest(BaseModel):
    project_slug: str
    pipeline_slug: str
    frequency: str          # "1h", "daily", "0 * * * *" (cron)
    window: str | None = None  # "7d", "1w"
    enabled: bool = True

class UpdateScheduleRequest(BaseModel):
    cron: str | None = None
    frequency: str | None = None
    window: str | None = None
    enabled: bool | None = None

@router.get("/")
async def list_schedules(project_slug: str | None = None):
    if project_slug:
        return await convex.query("schedules:listByProject", {"projectSlug": project_slug})
    return await convex.query("schedules:list", {})

@router.get("/{id}")
async def get_schedule(id: str):
    sched = await convex.query("schedules:get", {"id": id})
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return sched

@router.post("/")
async def create_schedule(req: CreateScheduleRequest):
    try:
        # Check if frequency is already a cron expression
        if " " in req.frequency:
            cron = req.frequency
        else:
            cron = parse_frequency(req.frequency)

        window_ends_at = None
        if req.window:
            window_ends_at = parse_window(req.window)

        # Initial next_run computation could be done here,
        # but for simplicity let's just trigger it or rely on scheduler fallback
        from croniter import croniter
        from datetime import datetime
        itr = croniter(cron, datetime.now())
        next_dt = itr.get_next(datetime)
        next_ms = int(next_dt.timestamp() * 1000)

        payload = {
            "projectSlug": req.project_slug,
            "pipelineSlug": req.pipeline_slug,
            "cron": cron,
            "frequency": req.frequency,
            "enabled": req.enabled,
            "status": "active" if req.enabled else "paused",
            "nextRunAt": next_ms
        }
        if window_ends_at is not None:
            payload["windowEndsAt"] = window_ends_at

        sched_id = await convex.mutation("schedules:create", payload)
        return {"id": sched_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{id}")
async def update_schedule(id: str, req: UpdateScheduleRequest):
    try:
        updates = {"id": id}
        if req.frequency is not None:
            if " " in req.frequency:
                updates["cron"] = req.frequency
            else:
                updates["cron"] = parse_frequency(req.frequency)
            updates["frequency"] = req.frequency

        if req.window is not None:
            updates["windowEndsAt"] = parse_window(req.window)

        if req.enabled is not None:
            updates["enabled"] = req.enabled
            updates["status"] = "active" if req.enabled else "paused"

        return await convex.mutation("schedules:update", updates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{id}")
async def remove_schedule(id: str):
    await convex.mutation("schedules:remove", {"id": id})
    return {"status": "ok"}

@router.post("/{id}/pause")
async def pause_schedule(id: str):
    return await convex.mutation("schedules:pause", {"id": id})

@router.post("/{id}/resume")
async def resume_schedule(id: str):
    return await convex.mutation("schedules:resume", {"id": id})
