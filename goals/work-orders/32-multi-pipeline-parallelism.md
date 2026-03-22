# Work Order 32 — Multi-Pipeline Parallelism

## Layer
8 — Infrastructure and Scale

## Goal
Allow multiple pipelines to hydrate concurrently instead of sequentially, using an async task queue with configurable concurrency, so large multi-pipeline research projects complete faster.

## Background
Currently each pipeline runs sequentially in a single `ThreadPoolExecutor(max_workers=1)`. This prevents SQLite contention but forces pipelines to queue. Pipelines that target different OWL namespaces or use disjoint data sources can safely run in parallel.

## Steps

### 1. Pipeline concurrency config
Add to `packages/api/app/core/config.py`:
```python
pipeline_max_concurrency: int = 3  # max parallel pipelines
pipeline_queue_size: int = 50      # max queued jobs
```

### 2. Async job queue
File: `packages/api/app/services/job_queue.py`

```python
class JobQueue:
    def __init__(self, max_concurrency: int):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active: dict[str, asyncio.Task] = {}
        self._queue: asyncio.Queue = asyncio.Queue()

    async def submit(self, pipeline_slug: str) -> str:
        """Enqueue a pipeline run. Returns job_id."""

    async def _worker(self):
        """Pulls from queue, acquires semaphore, runs hydration_worker."""

    def get_status(self) -> dict:
        """Returns active and queued job counts."""

    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued or running job."""
```

Start the worker loop in `main.py` `lifespan` startup.

### 3. OWL write isolation
Each pipeline gets its own temporary OWL world during hydration, then merges into the main world under the `ThreadPoolExecutor(max_workers=1)` lock. This allows parsing and transform steps to run in parallel while write-back to the shared OWL world remains single-threaded.

In `hydration_worker.py`:
- Move the parse + transform + DuckDB export phases outside the OWL executor
- Keep only `onto.save()` and `onto.load()` calls inside the executor
- Each pipeline writes to a temp `.owl` file, then the executor merges it

### 4. Job status API update
Extend `GET /api/v1/jobs/{job_id}` to return:
- `queue_position: int | null` — position in queue (null if running)
- `queued_at: datetime | null`
- `started_at: datetime | null`

### 5. Queue status endpoint
```
GET /api/v1/jobs/queue
```
Returns:
```json
{
  "active": ["pipeline_a", "pipeline_b"],
  "queued": ["pipeline_c"],
  "max_concurrency": 3
}
```

### 6. Cancel job endpoint
```
POST /api/v1/jobs/{job_id}/cancel
```

### 7. UI updates
In the Jobs page:
- Show a "Queue" section at the top if any jobs are waiting
- Show a progress spinner with "Position X in queue" for queued jobs
- Add a "Cancel" button (×) on running or queued jobs

## Affected Files
- `packages/api/app/core/config.py` — add concurrency settings
- `packages/api/app/services/job_queue.py` — **create**
- `packages/api/app/services/hydration_worker.py` — refactor for parallel-safe phases
- `packages/api/app/routers/jobs.py` — add queue status + cancel endpoints
- `packages/api/app/main.py` — start job queue worker in lifespan
- `packages/web/app/(dashboard)/jobs/page.tsx` — queue UI + cancel button
- `specs/api.md` — document new endpoints

## Acceptance Criteria
- [ ] Two pipelines submitted simultaneously both start running (up to `max_concurrency`)
- [ ] A third pipeline queues and starts when a slot opens
- [ ] Cancel stops a running job within 5 seconds
- [ ] The shared OWL world is never corrupted by concurrent pipeline runs
- [ ] Queue status endpoint reports correct active and queued counts
