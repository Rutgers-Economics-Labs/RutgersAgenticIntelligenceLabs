# Work Order 24 — Staleness Detection and Auto-Refresh

## Layer
5 — Self-Updating Analyses

## Prerequisites
WO-23 (Dependency Graph)

## Goal
Detect when a pipeline's source data is stale (based on configurable freshness rules) and automatically re-run dependent analyses, or notify the researcher to do so.

## Steps

### 1. Freshness config in pipeline YAML
Extend `packages/engine/specs/yaml-config.md` to support:

```yaml
pipeline:
  slug: nj_employment
  freshness:
    check_interval_hours: 24      # how often to check source for new data
    max_age_hours: 72             # mark stale if data older than this
    auto_refresh: true            # trigger re-hydration automatically if stale
    notify_on_stale: true         # send notification event (for UI banner)
```

### 2. Freshness check service
File: `packages/api/app/services/freshness_service.py`

```python
async def check_pipeline_freshness(pipeline_slug: str) -> dict:
    """
    Returns:
      {
        "slug": str,
        "last_hydrated_at": ISO datetime | None,
        "is_stale": bool,
        "age_hours": float,
        "max_age_hours": int,
        "auto_refresh": bool
      }
    """

async def check_all_pipelines() -> list[dict]:
    """Check freshness for all pipelines with freshness config."""

async def refresh_if_stale(pipeline_slug: str) -> bool:
    """Triggers hydration if stale and auto_refresh=true. Returns True if triggered."""
```

Last hydration time read from the Convex `jobs` table (most recent completed job for the pipeline).

### 3. Staleness API endpoints
File: `packages/api/app/routers/freshness.py`

```
GET  /api/v1/freshness                   — check_all_pipelines()
GET  /api/v1/freshness/{slug}            — check_pipeline_freshness(slug)
POST /api/v1/freshness/{slug}/refresh    — refresh_if_stale(slug), or force if ?force=true
```

### 4. Staleness banner in the UI
In the Jobs page and the Pipeline detail view:
- If a pipeline is stale, show a yellow banner: "Data may be outdated — last refreshed X hours ago. [Refresh Now]"
- If `auto_refresh: true`, show: "Auto-refresh is enabled — will refresh automatically."

Poll `GET /api/v1/freshness` every 5 minutes via a `useEffect` interval in the Jobs page.

### 5. Downstream analysis invalidation
When a pipeline is re-hydrated (job completes), query the `dependencies` table for all analyses that depend on it. Mark those analyses as `stale: true` in Convex.

When a researcher opens a stale analysis in the workspace, show a yellow "Results may be outdated" banner with a "Re-run" button.

### 6. Convex schema update
Add `stale: v.optional(v.boolean())` and `staledAt: v.optional(v.number())` to `agentSessions` (or a new `analysisRuns` table if created in a prior WO).

## Affected Files
- `packages/api/app/services/freshness_service.py` — **create**
- `packages/api/app/routers/freshness.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/api/app/services/hydration_worker.py` — trigger dependency invalidation on job complete
- `packages/web/convex/schema.ts` — add stale fields
- `packages/web/app/(dashboard)/jobs/page.tsx` — staleness banners
- `packages/engine/specs/yaml-config.md` — document `freshness` block
- `specs/api.md` — document freshness routes

## Acceptance Criteria
- [ ] Pipeline with `max_age_hours: 1` shows as stale after 1 hour without re-hydration
- [ ] `auto_refresh: true` triggers re-hydration without manual action
- [ ] Staleness banner appears in the Jobs UI
- [ ] Dependent analyses are marked stale when their source pipeline re-hydrates
- [ ] Re-run button in workspace re-executes the stale analysis
