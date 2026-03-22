# Work Order 29 — Research Dashboard Homepage

## Layer
7 — Dashboard and Monitoring

## Goal
Replace the current bare homepage with a rich research dashboard showing pipeline health, recent analyses, entity counts, and quick-start actions — the central hub researchers see first.

## Steps

### 1. Dashboard API endpoint
File: `packages/api/app/routers/dashboard.py`

```
GET /api/v1/dashboard/summary
```

Returns:
```json
{
  "pipeline_count": 3,
  "entity_count": 847,
  "triple_count": 12043,
  "last_hydrated_at": "2025-03-20T14:30:00Z",
  "pipelines": [
    {
      "slug": "nj_employment",
      "entity_count": 420,
      "last_run_at": "2025-03-20T14:30:00Z",
      "last_run_status": "success",
      "is_stale": false
    }
  ],
  "recent_jobs": [
    {"slug": "nj_employment", "status": "success", "started_at": "...", "duration_ms": 3400}
  ]
}
```

### 2. Entity and triple counts
In `ontology_service.py`, add:
```python
def get_entity_count(db_key: str) -> int
def get_triple_count(db_key: str) -> int
def get_class_counts(db_key: str) -> dict[str, int]  # {class_name: entity_count}
```

### 3. Dashboard page
Replace `packages/web/app/(dashboard)/page.tsx` (or create if not existing) with a full dashboard:

**Top row — stat cards:**
- Total Entities
- Total Triples
- Active Pipelines
- Last Hydration (relative time, e.g. "2 hours ago")

**Middle row — pipeline status grid:**
- One card per pipeline showing: slug, entity count, last run time, status badge (green/yellow/red), "Run Now" button

**Bottom row — two columns:**
- Left: Recent Jobs (last 5 jobs as a timeline list)
- Right: Quick Actions (4 buttons: New Workspace, New Config, Run All Pipelines, Explore Ontology)

### 4. Real-time updates
Poll `GET /api/v1/dashboard/summary` every 30 seconds via `useEffect` with a timer. Show a "Refreshing..." indicator when polling.

Alternatively, listen to Convex `jobs` table for real-time job status updates (no polling needed for job status).

### 5. Empty state
If no pipelines are configured, show a centered onboarding card:
- "Welcome to RAIL — your AI-powered research platform"
- Step list: 1. Create a pipeline config, 2. Add a data source, 3. Run hydration, 4. Ask the AI
- "Create First Pipeline" button → navigates to `/configs`

## Affected Files
- `packages/api/app/routers/dashboard.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/api/app/services/ontology_service.py` — add count methods
- `packages/web/app/(dashboard)/page.tsx` — replace with full dashboard
- `specs/api.md` — document dashboard route

## Acceptance Criteria
- [ ] Dashboard shows correct entity and triple counts from the live ontology
- [ ] Each pipeline card shows status and last run time
- [ ] "Run Now" triggers a hydration job and updates the card status in real time
- [ ] Empty state shows when no pipelines exist
- [ ] Quick actions navigate to the correct pages
