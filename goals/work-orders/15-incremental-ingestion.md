# Work Order 15 — Incremental / Delta Ingestion

## Layer
2 — Ingestion Expansion

## Goal
Track the last-fetched state per API source so pipelines only pull new records on subsequent runs, reducing hydration time from minutes to seconds for sources with incremental updates.

## Background
Currently every hydration run re-fetches all data from scratch. A FRED series with 20 years of monthly data re-downloads all 240 observations every time. At scale with many sources this is slow and wasteful. Incremental ingestion fetches only records newer than the last run.

## Steps

### 1. Add `incremental` field to API config YAML

```yaml
name: NJ Unemployment (FRED)
type: api
url: "https://api.stlouisfed.org/fred/series/observations"
incremental:
  enabled: true
  cursor_field: date        # which field to use as the high-water mark
  cursor_type: date         # "date" | "integer" | "string"
  param_name: observation_start  # API query param to pass the cursor to
```

When `incremental.enabled: true`, the engine:
1. Reads the stored cursor from `{RAIL_CACHE_DIR}/cursors/{slug}.json`
2. Adds the cursor value as a query param (e.g. `observation_start=2024-01-01`)
3. After a successful fetch, writes the new max cursor value back to the file

### 2. Implement cursor read/write in `api_runner.py`
File: `packages/engine/engine/api_runner.py`

```python
def _read_cursor(cache_dir: str, slug: str) -> str | None: ...
def _write_cursor(cache_dir: str, slug: str, value: str) -> None: ...
```

Cursor file format: `{"cursor": "2024-03-01", "updated_at": "2024-03-15T10:00:00"}`

### 3. Merge strategy for incremental runs
When a pipeline step runs incrementally, only new rows arrive. The ontology builder must:
- **Create** new individuals for new rows (existing behavior)
- **Update** existing individuals if the URI matches an existing one (new behavior — currently skips or errors on duplicate URIs)

Add `on_duplicate: update` field to pipeline step config (default: `skip`).

### 4. Cursor storage in Convex
Store cursors in Convex for persistence across server restarts and deployments (local file cache is not reliable in containerized environments).

New Convex table: `sourceCursors`
| Field | Type |
|-------|------|
| `slug` | string (indexed `by_slug`) |
| `cursor` | string |
| `cursorField` | string |
| `updatedAt` | number |
| `recordCount` | number |

New Convex functions in `convex/sourceCursors.ts`: `get(slug)`, `set(slug, cursor, recordCount)`.

The hydration worker reads/writes cursors via Convex before/after the engine subprocess runs, then passes them to the engine via env vars.

### 5. Engine reads cursor from env
Pass `RAIL_CURSOR_{SLUG_UPPER}=2024-01-01` into the subprocess env. The engine reads these and applies them when building requests.

### 6. Hydration worker updates cursor on success
After successful job completion, for each API config that has `incremental.enabled: true`:
- Read the max value of `cursor_field` from the fetched data
- Call `sourceCursors:set(slug, newCursor, rowCount)` in Convex

### 7. Jobs page: show incremental badge
In `/jobs`, show an "incremental" badge on job cards where any API source used delta fetching. Show "N new records" in the step result.

### 8. Force full refresh option
In the trigger job endpoint and UI, add `force_full_refresh: true` option that ignores the cursor and fetches everything. Useful when source data is corrected retroactively.

## Affected Files
- `packages/engine/engine/api_runner.py` — add cursor read/write, incremental fetch logic
- `packages/engine/engine/pipeline_runner.py` — pass `on_duplicate` to ontology builder
- `packages/engine/engine/ontology_builder.py` — add `on_duplicate: update` behavior
- `packages/api/app/services/hydration_worker.py` — read/write cursors via Convex, pass env vars
- `packages/api/app/routers/jobs.py` — add `force_full_refresh` param
- `packages/web/convex/schema.ts` — add `sourceCursors` table
- `packages/web/convex/sourceCursors.ts` — **create**
- `specs/api.md` — update after implementation
- `specs/yaml-config.md` (engine specs) — document `incremental` field

## Acceptance Criteria
- [ ] First run fetches all records; second run only fetches records newer than the cursor date
- [ ] Cursor persists in Convex across server restarts
- [ ] `on_duplicate: update` correctly updates existing individuals instead of skipping
- [ ] `force_full_refresh: true` ignores cursor and fetches everything
- [ ] Jobs page shows "N new records (incremental)" for delta runs
- [ ] Incremental run is measurably faster than full run for the same source
