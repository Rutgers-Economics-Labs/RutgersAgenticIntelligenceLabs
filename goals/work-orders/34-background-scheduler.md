# Work Order 34 — Background Scheduler

## Layer
8 — Infrastructure and Scale

## Goal
Add a cron-style scheduler that automatically runs pipelines on a configurable schedule (daily, weekly, custom cron expression), enabling fully automated data refresh without manual intervention.

## Steps

### 1. Schedule config in pipeline YAML
Extend `packages/engine/specs/yaml-config.md`:

```yaml
pipeline:
  slug: nj_employment
  schedule:
    cron: "0 6 * * *"     # 6am daily (UTC)
    enabled: true
    timezone: "America/New_York"  # optional, defaults to UTC
```

### 2. Scheduler service
File: `packages/api/app/services/scheduler_service.py`

Use `apscheduler` with `AsyncIOScheduler`:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class SchedulerService:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()

    def start(self):
        self._scheduler.start()

    def stop(self):
        self._scheduler.shutdown()

    async def load_schedules_from_configs(self):
        """
        Reads all pipeline YAML configs.
        For each with schedule.enabled=true, adds a job to the scheduler.
        """

    async def reload(self):
        """Remove all jobs and re-add from current configs. Called after config changes."""

    def list_jobs(self) -> list[dict]:
        """Returns list of scheduled jobs with next run time."""

    def trigger_now(self, slug: str):
        """Immediately trigger a scheduled job."""
```

Start in `main.py` lifespan. Call `load_schedules_from_configs()` at startup.

### 3. Schedule API endpoints
File: `packages/api/app/routers/scheduler.py`

```
GET  /api/v1/scheduler/jobs           — list all scheduled jobs with next_run_at
POST /api/v1/scheduler/reload         — reload schedules from disk
POST /api/v1/scheduler/jobs/{slug}/trigger  — run immediately
PUT  /api/v1/scheduler/jobs/{slug}/enable   — enable schedule
PUT  /api/v1/scheduler/jobs/{slug}/disable  — disable schedule
```

### 4. Schedule history in Convex
Each scheduled run is a normal job (uses existing `jobs` Convex table). Tag it with `triggered_by: "schedule"` vs `"manual"` using an optional field.

Add to `jobs` Convex table:
```ts
triggeredBy: v.optional(v.union(v.literal("manual"), v.literal("schedule"), v.literal("agent")))
```

### 5. Scheduler UI
File: `packages/web/app/(dashboard)/scheduler/page.tsx`

Table listing all scheduled pipelines:
- Pipeline slug, cron expression, next run time, last run time, status, enabled toggle

Enable/disable toggle calls `PUT /api/v1/scheduler/jobs/{slug}/enable|disable`.

"Run Now" button triggers an immediate run.

Show run history for each pipeline (last 5 runs with status badges).

### 6. Config editor integration
In the Configs YAML editor page (existing), show a "Schedule" section when editing a pipeline config. Provide a cron expression input with a human-readable preview (e.g., "Every day at 6:00 AM UTC").

### 7. New dependency
Add `apscheduler>=3.10.0` to `packages/api/pyproject.toml`.

## Affected Files
- `packages/api/app/services/scheduler_service.py` — **create**
- `packages/api/app/routers/scheduler.py` — **create**
- `packages/api/app/main.py` — start scheduler in lifespan, register router
- `packages/api/pyproject.toml` — add `apscheduler`
- `packages/web/convex/schema.ts` — add `triggeredBy` to jobs
- `packages/web/app/(dashboard)/scheduler/page.tsx` — **create**
- `packages/web/components/layout/Sidebar.tsx` — add "Scheduler" nav item
- `packages/engine/specs/yaml-config.md` — document `schedule` block

## Acceptance Criteria
- [ ] Pipeline with `cron: "*/5 * * * *"` runs every 5 minutes automatically
- [ ] Disabling a schedule stops future runs without deleting the config
- [ ] "Run Now" triggers an immediate job visible in the Jobs page
- [ ] Scheduler reloads correctly after a config YAML is edited
- [ ] Scheduler UI shows next run time in the researcher's local timezone
- [ ] Jobs table shows `triggered_by: "schedule"` for automated runs
