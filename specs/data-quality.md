# Data Quality

The data quality system provides automated health monitoring for a project's DuckDB ontology. It tracks null rates, entity counts, and column-level statistics per table, and supports snapshot-based diffing to detect schema drift and data changes between hydration runs.

---

## Overview

After every hydration, the platform can answer:
- **Health:** How complete is this ontology? Which tables have high null rates? Which columns are sparse?
- **Freshness:** When was each table's data last updated?
- **Change:** How did this hydration change the ontology compared to the previous run?

The data quality page lives at `/[project]/quality` and is accessible from the project sidebar.

---

## API Routes — `/api/v1/quality`

Router: `packages/api/app/routers/quality.py`

| Method | Path | Params / Body | Returns |
|--------|------|--------------|---------|
| GET | `/report` | `project_id?` | Full quality report for the project's active DuckDB |
| POST | `/snapshot` | `{project_id?, label?}` | Saves current entity counts to Convex; returns `{snapshotId, tableCount, createdAt}` |
| GET | `/diff` | `project_id?` | Compares the two most recent snapshots; returns diff report |

`project_id` may be a Convex project ID or a project slug. When absent, falls back to the globally-loaded DuckDB path (legacy behavior).

### `GET /report` — Quality Report

Runs against the project's active DuckDB in read-only mode. For each table:

**Table-level metrics:**
- `rowCount` — total rows
- `freshness` — max value of the most recent date/timestamp column found (`hasIngestDate`, `hasDate`, `createdAt`, `updatedAt`, `year` — checked in this order)

**Column-level metrics (per column):**
- `name`, `type`
- `nullCount`, `nullRate` (fraction 0.0–1.0)
- `distinctCount`
- `min`, `max` — for numeric, date, and timestamp columns

**Summary:**
- `tableCount`, `totalRows`
- `overallNullRate` — weighted average across all cells (total null cells / total cells)

**Health rating** (derived on the frontend, not returned by API):

| Condition | Rating |
|-----------|--------|
| `overallNullRate == 0` | excellent |
| `overallNullRate < 0.05` | good |
| `overallNullRate < 0.15` | fair |
| `overallNullRate >= 0.15` | poor |

**Response shape:**
```json
{
  "projectId": "nj-economics",
  "dbPath": "/tmp/rail_artifacts/.../onto.duckdb",
  "generatedAt": 1705320000000,
  "summary": {
    "tableCount": 8,
    "totalRows": 63400,
    "overallNullRate": 0.0312
  },
  "tables": [
    {
      "table": "LaborIndicator",
      "rowCount": 48600,
      "freshness": { "column": "hasDate", "maxValue": "2024-01-01" },
      "columns": [
        {
          "name": "hasValue",
          "type": "FLOAT",
          "nullCount": 0,
          "nullRate": 0.0,
          "distinctCount": 1240,
          "min": "2.1",
          "max": "14.7"
        }
      ]
    }
  ]
}
```

### `POST /snapshot` — Save Snapshot

Saves a lightweight snapshot of the current entity counts and column null rates to Convex for later diffing. Called automatically by the hydration worker after each successful run (with `label: "post-hydration job #{jobId}"`). Can also be triggered manually from the UI.

Stored in the Convex `qualitySnapshots` table (see schema below).

### `GET /diff` — Compare Snapshots

Fetches the two most recent snapshots from Convex and computes the diff:

**Table-level diff statuses:**
- `added` — table exists in newer snapshot but not older
- `removed` — table exists in older but not newer
- `grew` — row count increased
- `shrank` — row count decreased
- `unchanged` — row count identical

**Column-level drift** (flagged when `|nullRateDrift| > 0.01` or `distinctDelta != 0`):
- `added` / `removed` — column appeared or disappeared
- `changed` — null rate drifted or distinct count changed

**Response shape:**
```json
{
  "hasDiff": true,
  "newer": { "label": "post-hydration job #42", "createdAt": 1705320000000 },
  "older": { "label": "post-hydration job #41", "createdAt": 1705233600000 },
  "summary": {
    "tablesAdded": 0, "tablesRemoved": 0,
    "tablesGrew": 3, "tablesShrank": 0, "tablesUnchanged": 5
  },
  "tables": [
    {
      "table": "LaborIndicator",
      "status": "grew",
      "newCount": 48600,
      "oldCount": 47400,
      "delta": 1200,
      "columnDiffs": []
    }
  ]
}
```

---

## Convex Schema — `qualitySnapshots`

| Field | Type | Notes |
|-------|------|-------|
| `projectId` | string? | Project slug or Convex project ID. Indexed `by_project`. |
| `label` | string | Human-readable label (e.g. `"post-hydration job #42"`) |
| `tables` | any | `{tableName: {rowCount, columns: {colName: {nullRate, distinctCount}}}}` |
| `createdAt` | number | ms timestamp, indexed `by_created` |

The `quality:listSnapshots` Convex query returns snapshots ordered by `createdAt` descending. The diff endpoint fetches `limit: 2` to get the two most recent.

### Auto-Snapshot on Hydration

`hydration_worker.py` calls `POST /quality/snapshot` (internal call, not via HTTP — direct function call to `quality_service.save_snapshot()`) after each successful hydration with label `f"post-hydration {job_id}"`. This ensures a diff is always available immediately after any hydration completes.

---

## Frontend — `/[project]/quality`

### Summary Cards (top row)
Four metric cards: Tables, Total Rows, Null Rate (colored by health), Health rating (text: excellent / good / fair / poor).

### Two-Tab Layout

**Tab 1: Table Health**

Sorted by worst null rate descending (most problematic tables first). Each table renders as a collapsible `TableCard`:

- **Header:** health icon (✓ green / ✓ yellow / △ orange), table name, freshness badge (`latest: 2024-01-01`), row count, column count, expand/collapse chevron.
- **Expanded:** per-column table with: column name (monospace), type, null rate bar (color-coded: green=0%, yellow<5%, orange<20%, red≥20%), distinct count, min, max.

**Tab 2: Diff**

Shows "N snapshots" count in the tab label. Requires ≥ 2 snapshots; shows an empty state with instructions if fewer exist.

- **Comparison header:** old label → new label with colored summary chips (N Added, N Grew, N Shrank, N Removed).
- **Table diff rows** — one per table, collapsed by default if `unchanged`, expanded otherwise:
  - Status badge (added/removed/grew/shrank/unchanged)
  - Old count → new count with delta (+ green / − orange)
  - Expanded: column-level drift list — added, removed, or changed columns with null rate drift direction and magnitude

### Actions (header buttons)

- **Snapshot** — calls `POST /quality/snapshot` with current timestamp as label; refreshes the diff tab. Disabled if no DuckDB is loaded.
- **Refresh** — re-fetches both the report and diff simultaneously.

---

## Integration with Hydration Jobs

Quality snapshots integrate with the hydration job lifecycle:

1. Job starts → no snapshot action
2. Job completes (success) → `quality_service.save_snapshot(project_id, label=f"post-hydration {job_id}")` called automatically
3. Job fails → no snapshot (failed runs don't produce a valid DuckDB)

The jobs page links to the quality page with `?projectId={slug}` for quick access to the post-run quality report.

---

## `lib/api.ts` — Quality Namespace

```typescript
quality = {
  report(projectId?: string): Promise<QualityReport>
    // GET /quality/report?project_id={projectId}

  snapshot(projectId?: string, label?: string): Promise<{snapshotId: string, tableCount: number, createdAt: number}>
    // POST /quality/snapshot

  diff(projectId?: string): Promise<DiffReport>
    // GET /quality/diff?project_id={projectId}
}
```

**Types:**

```typescript
ColumnStat = {
  name: string; type: string;
  nullCount: number; nullRate: number;
  distinctCount: number; min?: string; max?: string; error?: string;
}
TableReport = {
  table: string; rowCount: number;
  columns: ColumnStat[];
  freshness?: { column: string; maxValue: string } | null;
}
QualityReport = {
  projectId?: string; generatedAt: number;
  summary: { tableCount: number; totalRows: number; overallNullRate: number };
  tables: TableReport[]; error?: string;
}
ColumnDiff = {
  column: string; status: string;
  nullRateDrift?: number; distinctDelta?: number;
  newNullRate?: number; oldNullRate?: number;
}
TableDiff = {
  table: string; status: string;
  newCount: number; oldCount: number; delta: number;
  columnDiffs: ColumnDiff[];
}
DiffReport = {
  hasDiff: boolean; message?: string; snapshots?: number;
  newer?: { label: string; createdAt: number };
  older?: { label: string; createdAt: number };
  summary?: { tablesAdded: number; tablesRemoved: number; tablesGrew: number; tablesShrank: number; tablesUnchanged: number };
  tables?: TableDiff[];
}
```
