# WO-5.2 — Scheduler Service

**Status:** blocked  
**Spec:** `specs/schedule.md`  
**Depends on:** WO-5.1  
**Blocks:** WO-5.3  

---

## Goal

Build the scheduling system: `scheduledPipelines` Convex table, `scheduler_service.py` that runs background asyncio tasks, and the `/schedules` REST router with full CRUD + pause/resume.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/convex/schema.ts` | **Modify** | Add `scheduledPipelines` table |
| `packages/web/convex/schedules.ts` | **Create** | CRUD functions |
| `packages/api/app/services/scheduler_service.py` | **Create** | Background scheduler |
| `packages/api/app/routers/schedules.py` | **Create** | REST router |
| `packages/api/app/main.py` | **Modify** | Register scheduler in lifespan; mount router |

---

## Steps

### 1. Add `scheduledPipelines` to `packages/web/convex/schema.ts`

```typescript
scheduledPipelines: defineTable({
  projectSlug: v.string(),
  pipelineSlug: v.string(),
  cron: v.optional(v.string()),         // resolved cron e.g. "0 * * * *"
  frequency: v.optional(v.string()),    // human shorthand "1h", "daily"
  windowEndsAt: v.optional(v.number()), // ms timestamp, null = indefinite
  enabled: v.boolean(),
  status: v.string(),                   // "active" | "paused" | "completed" | "error"
  lastRunAt: v.optional(v.number()),
  lastJobId: v.optional(v.string()),
  nextRunAt: v.optional(v.number()),
  createdAt: v.number(),
  updatedAt: v.number(),
}).index("by_project", ["projectSlug"])
  .index("by_status", ["status"]),
```

Run `npx convex deploy`.

### 2. Create `packages/web/convex/schedules.ts`

Export: `list`, `listByProject`, `get`, `create`, `update`, `pause`, `resume`, `remove`.

### 3. Create `packages/api/app/services/scheduler_service.py`

```python
import asyncio
from croniter import croniter  # pip install croniter
from datetime import datetime
import time
from app.services.convex_client import convex

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
                project = await convex.query("projects:getBySlug", {"slug": sched["projectSlug"]})
                if project:
                    from app.routers.jobs import _trigger_job
                    job_result = await _trigger_job(sched["pipelineSlug"], project["_id"])
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
```

### 4. Create `packages/api/app/routers/schedules.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.convex_client import convex
from app.services.scheduler_service import parse_frequency, parse_window

router = APIRouter(prefix="/schedules", tags=["schedules"])

class CreateScheduleRequest(BaseModel):
    project_slug: str
    pipeline_slug: str
    frequency: str          # "1h", "daily", "0 * * * *" (cron)
    window: str | None = None  # "7d", "1w"
    enabled: bool = True
```

Full CRUD: `GET /`, `GET /{id}`, `POST /`, `PUT /{id}`, `DELETE /{id}`, `POST /{id}/pause`, `POST /{id}/resume`.

### 5. Register in `main.py` lifespan

```python
from app.services.scheduler_service import scheduler
from app.routers import schedules

# In lifespan:
async with asynccontextmanager(...):
    await scheduler.start()
    yield
    await scheduler.stop()

app.include_router(schedules.router, prefix="/api/v1")
```

---

## Acceptance

- [ ] `scheduledPipelines` table in Convex after `npx convex deploy`
- [ ] `POST /api/v1/schedules` creates a schedule with proper `cron` and `nextRunAt`
- [ ] Scheduler loop runs and triggers hydration when `nextRunAt` is due
- [ ] `POST /{id}/pause` sets `enabled=false`; `POST /{id}/resume` reactivates
- [ ] Schedules with expired `windowEndsAt` are marked `completed` and not run again
- [ ] `croniter` correctly computes next run time for standard cron expressions
