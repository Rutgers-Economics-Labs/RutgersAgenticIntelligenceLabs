# Scheduled Pipelines & Live Data Collection

Scheduled pipelines allow the platform to collect data from live or frequently-updated sources automatically, without requiring a user to manually trigger a hydration run. This document specifies the scheduling system, incremental hydration mode, and how the platform manages active collection windows.

---

## The Two Problems Scheduling Solves

**1. Collection:** Fetching data from a live source repeatedly over time (e.g., poll FRED daily for a week, collect hourly sensor readings for a month).

**2. Ingestion:** Adding new observations to an existing ontology without destroying previously collected data. This requires `hydration_mode: incremental` — the engine does not drop the quadstore before running.

Both concerns are configured in the pipeline YAML. The scheduling system handles when to run; incremental mode handles how the engine behaves when it runs.

---

## Pipeline Config Fields

```yaml
# configs/pipelines/nj-live-unemployment.yaml
name: NJ Live Unemployment Collection
ontology: configs/ontology/nj-economics.yaml
steps:
  - name: load_unemployment
    api: nj_unemployment
    class: LaborIndicator
    uri: "LaborIndicator_{series}_{date}"
    properties:
      hasValue: "{value}"
      hasDate: "{date}"
      hasSeries: "{series}"

hydration_mode: incremental          # preserve existing individuals between runs
schedule:
  frequency: 1h                      # collect every hour
  window: 7d                         # auto-stop after 7 days
```

Full schedule field reference is in `specs/yaml-config.md`.

---

## Hydration Modes

### `full` (default)

Current behavior. The worker deletes `onto.db` before each run and rebuilds the entire ontology from scratch. Every individual is recreated on every run. Appropriate for:
- Batch datasets that change entirely between runs
- Pipelines where correctness depends on a clean slate (e.g., revised historical data)
- Development and debugging

### `incremental`

The worker does **not** delete `onto.db` before running. The pipeline executes normally — `_get_or_create` returns the existing individual when a URI already exists, or creates a new one. Data properties on existing individuals are updated to the values from the current run.

Appropriate for:
- Append-only time series (each new date produces a new URI, so every run creates new individuals)
- Sources that publish new observations without revising old ones (FRED, BLS, Census estimates)
- Any pipeline where you want the ontology to accumulate data over time

**URI design is critical for incremental mode.** If the URI template includes the date (e.g., `LaborIndicator_{series}_{date}`), each observation gets a unique URI and accumulates naturally. If the URI does not include the date (e.g., `LaborIndicator_{series}`), the same individual is updated on every run — effectively an upsert.

---

## Convex Schema — `scheduledPipelines`

Active schedules are tracked in a new Convex table:

| Field | Type | Notes |
|-------|------|-------|
| `projectSlug` | string | Owning project, indexed `by_project` |
| `pipelineSlug` | string | Pipeline config slug |
| `cron` | string? | Resolved cron expression (e.g. `"0 * * * *"`) |
| `frequency` | string? | Original human shorthand (`"1h"`) |
| `windowEndsAt` | number? | ms timestamp when the schedule auto-stops; null = indefinite |
| `enabled` | boolean | Whether the schedule is currently active |
| `status` | string | `"active"` \| `"paused"` \| `"completed"` \| `"error"` |
| `lastRunAt` | number? | ms timestamp of most recent run |
| `lastJobId` | string? | Most recent hydration job ID |
| `nextRunAt` | number? | ms timestamp of next scheduled run |
| `runCount` | number | Total number of runs executed |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## Scheduler Service (`app/services/scheduler_service.py`)

A lightweight in-process scheduler that manages active collection windows. It runs as a background task in the FastAPI lifespan.

```python
class SchedulerService:
    async def start(self) -> None
        # Loads all enabled scheduledPipelines from Convex on startup
        # Registers each as an asyncio task with the correct interval

    async def stop(self) -> None
        # Cancels all scheduled tasks cleanly on shutdown

    async def register(self, schedule_id: str) -> None
        # Adds a new schedule from Convex at runtime (called when a schedule is created via API)

    async def pause(self, schedule_id: str) -> None
    async def resume(self, schedule_id: str) -> None
    async def cancel(self, schedule_id: str) -> None

    async def _run_tick(self, schedule_id: str) -> None
        # Called on each tick for a schedule:
        # 1. Check windowEndsAt — if passed, cancel and set status: "completed"
        # 2. Check enabled — if false, skip
        # 3. Fetch pipeline config from Convex
        # 4. Call hydration_worker.run() with hydration_mode: incremental
        # 5. Update lastRunAt, lastJobId, nextRunAt, runCount in Convex
```

**Frequency to cron conversion:**
```python
FREQUENCY_MAP = {
    "15m": "*/15 * * * *",
    "1h":  "0 * * * *",
    "6h":  "0 */6 * * *",
    "12h": "0 */12 * * *",
    "1d":  "0 8 * * *",     # daily at 8am
    "1w":  "0 8 * * 1",     # weekly on Monday at 8am
}
```

The scheduler uses `croniter` to compute `nextRunAt` from a cron expression and the current time.

---

## API Routes — `/api/v1/schedules`

New router: `app/routers/schedules.py`

| Method | Path | Body / Params | Returns |
|--------|------|--------------|---------|
| GET | `` | `project_slug?` | list of schedule records for the project |
| GET | `/{schedule_id}` | — | single schedule record |
| POST | `` | `{project_slug, pipeline_slug, cron?, frequency?, window?, enabled?}` | created schedule record; registers with scheduler_service |
| PUT | `/{schedule_id}` | `{enabled?, window?}` | updated record; updates scheduler_service |
| DELETE | `/{schedule_id}` | — | cancels schedule; removes from Convex |
| POST | `/{schedule_id}/pause` | — | sets `enabled: false`; pauses scheduler task |
| POST | `/{schedule_id}/resume` | — | sets `enabled: true`; resumes scheduler task |

`POST /` validates that the referenced `pipeline_slug` exists and that its YAML contains `hydration_mode: incremental` (warning, not error, if missing — `full` mode schedules are allowed but discouraged).

---

## Frontend — Schedule Management

Schedules surface in two places:

**`/[project]/pipelines` page:**
Each pipeline card gains a "Schedule" button. Clicking opens a modal:
- Frequency selector (15m / 1h / 6h / 1d / 1w / custom cron)
- Window duration input (e.g. "7 days")
- Enable/disable toggle
- "Save" creates or updates the schedule via `POST /api/v1/schedules`

Active schedules show a badge on the pipeline card: `● collecting · next run in 23m`.

**`/[project]/jobs` page:**
Scheduled runs appear in the job history with a clock icon and "scheduled" trigger label (vs "manual"). The schedule's status (`active`/`paused`/`completed`) is shown in a header banner when a schedule is active.

---

## Collection Window Lifecycle

```
Schedule created (enabled: true, windowEndsAt: +7d)
    │
    ├── tick at t+1h → run pipeline → create hydrationJob (incremental) → append new individuals
    ├── tick at t+2h → run pipeline → ...
    ├── ...
    ├── tick at t+168h (7d) → windowEndsAt passed → cancel schedule → status: "completed"
    │
    └── Ontology now contains 168 hours of observations
```

After collection completes, the ontology is finalized. Subsequent queries and agent sessions see the full accumulated time series. The project's DuckDB is updated after each run, so partial results are queryable throughout the collection window.

---

## Data Model Considerations for Incremental Mode

**URI uniqueness is the deduplication key.** Design URIs to be unique per observation:

```yaml
# Good: unique per series+date — accumulates correctly
uri: "LaborIndicator_{series}_{date}"

# Good: unique per station+date+hour — accumulates correctly
uri: "Reading_{station_id}_{date}_{hour}"

# Caution: unique per series only — updates the same individual each run (upsert behavior)
uri: "LaborIndicator_{series}"
```

**Data properties are updated on upsert.** If a URI already exists and the run produces new property values, those values are written to the existing individual. This means revised data (e.g., FRED data revisions) automatically update existing observations.

**Kernel properties are re-written on each upsert.** `hasIngestDate` and `hasPipelineID` on existing individuals reflect the most recent run that touched them, not the original creation run. This is intentional — it surfaces when data was last refreshed.
