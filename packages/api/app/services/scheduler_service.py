import asyncio
from croniter import croniter  # pip install croniter
from datetime import datetime
import time
from app.services.convex_client import convex
from app.services import planner_service

FREQUENCY_TO_CRON = {
    "1m": "* * * * *",
    "5m": "*/5 * * * *",
    "15m": "*/15 * * * *",
    "30m": "*/30 * * * *",
    "1h": "0 * * * *",
    "6h": "0 */6 * * *",
    "12h": "0 */12 * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
}

def parse_frequency(freq: str) -> str:
    """Convert human shorthand to cron expression."""
    if freq in FREQUENCY_TO_CRON:
        return FREQUENCY_TO_CRON[freq]
    if freq.endswith("d"):
        days = int(freq[:-1])
        return f"0 0 */{days} * *"
    if freq.endswith("h"):
        hours = int(freq[:-1])
        return f"0 */{hours} * * *"
    raise ValueError(f"Unknown frequency: {freq}")

def parse_window(window: str) -> int:
    """Convert window string to milliseconds from now."""
    now_ms = int(time.time() * 1000)
    if window.endswith("d"):
        return now_ms + int(window[:-1]) * 86_400_000
    if window.endswith("h"):
        return now_ms + int(window[:-1]) * 3_600_000
    if window.endswith("w"):
        return now_ms + int(window[:-1]) * 7 * 86_400_000
    raise ValueError(f"Unknown window: {window}")


class SchedulerService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        """Poll Convex every 30 seconds for due schedules."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                print(f"[scheduler] error: {e}")
            await asyncio.sleep(30)

    async def _tick(self):
        now_ms = int(time.time() * 1000)
        schedules = await convex.query("schedules:listActive", {})

        for sched in schedules:
            # Check if window has expired
            if sched.get("windowEndsAt") and now_ms > sched["windowEndsAt"]:
                await convex.mutation("schedules:update", {
                    "id": sched["_id"],
                    "status": "completed",
                    "enabled": False,
                })
                continue

            next_run = sched.get("nextRunAt", 0)
            if now_ms < next_run:
                continue  # Not due yet

            # Trigger the pipeline
            try:
                project = None
                project_slug = str(sched.get("projectSlug") or "").strip()
                if project_slug:
                    try:
                        project = await planner_service.get_project_by_slug(project_slug)
                    except Exception:
                        project = None
                job_id = None
                if project:
                    from app.routers.jobs import _trigger_job
                    job_result = await _trigger_job(sched["pipelineSlug"], project_slug or str(project.get("slug") or ""))
                    job_id = job_result.get("jobId")

                # Compute next run time
                cron = sched.get("cron")
                if cron:
                    itr = croniter(cron, datetime.now())
                    next_dt = itr.get_next(datetime)
                    next_ms = int(next_dt.timestamp() * 1000)
                else:
                    next_ms = now_ms + 3_600_000  # fallback 1h

                await convex.mutation("schedules:update", {
                    "id": sched["_id"],
                    "lastRunAt": now_ms,
                    "lastJobId": job_id,
                    "nextRunAt": next_ms,
                })
            except Exception as e:
                await convex.mutation("schedules:update", {
                    "id": sched["_id"],
                    "status": "error",
                })

scheduler = SchedulerService()
