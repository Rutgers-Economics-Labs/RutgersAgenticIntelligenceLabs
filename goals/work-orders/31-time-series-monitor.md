# Work Order 31 — Time-Series Monitor Page

## Layer
7 — Dashboard and Monitoring

## Goal
Build a time-series monitoring page that plots any numeric ontology property over time for one or more entities, enabling researchers to visually track trends, spot anomalies, and compare entities without writing SQL.

## Steps

### 1. Time-series query endpoint
File: `packages/api/app/routers/timeseries.py`

```
GET /api/v1/timeseries
Query params:
  class_name:  OWL class (e.g. "County")
  property:    data property name (e.g. "hasUnemploymentRate")
  entity_uris: comma-separated list (optional; defaults to all entities)
  start:       ISO date (optional)
  end:         ISO date (optional)
  limit:       int (default 1000, max 10000)
```

Returns:
```json
{
  "property": "hasUnemploymentRate",
  "series": [
    {
      "entity_uri": "http://.../County_34001",
      "label": "Atlantic County",
      "data": [
        {"period": "2020-Q1", "value": 5.2},
        {"period": "2020-Q2", "value": 7.8}
      ]
    }
  ]
}
```

Period is extracted from the `Measure` linked to each entity. If no period is present, fall back to insertion order.

### 2. Property selector
Build a property discovery endpoint:
```
GET /api/v1/timeseries/properties?class_name=County
```
Returns list of numeric data properties available for that class. Derived from DuckDB column types.

### 3. Time-series monitor page
File: `packages/web/app/(dashboard)/monitor/page.tsx`

**Controls bar:**
- Class selector dropdown (populated from `/sql/tables`)
- Property selector (populated from `/api/v1/timeseries/properties`)
- Entity multi-select (type to search, populated lazily from ontology)
- Date range picker
- "Plot" button

**Chart area:**
- Multi-line `recharts` LineChart — one line per entity
- X axis: period labels
- Y axis: property value
- Tooltip showing entity label + value
- Toggle to show/hide individual series by clicking legend

**Anomaly highlight:**
- Any data point > 2 std devs from that entity's own mean is highlighted with a red dot

**Comparison table:**
- Below chart: table showing summary stats (mean, min, max, latest) per entity
- Sortable by any column

### 4. Saved monitors
Add a `monitors` Convex table:
```ts
monitors: defineTable({
  title: v.string(),
  className: v.string(),
  property: v.string(),
  entityUris: v.array(v.string()),
  createdAt: v.number(),
})
  .index("by_created", ["createdAt"])
```

A "Save Monitor" button stores the current selections. Saved monitors appear in a list on the left sidebar of the monitor page and can be re-loaded with one click.

## Affected Files
- `packages/api/app/routers/timeseries.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/convex/schema.ts` — add `monitors` table
- `packages/web/convex/monitors.ts` — **create** (CRUD functions)
- `packages/web/app/(dashboard)/monitor/page.tsx` — **create**
- `packages/web/components/layout/Sidebar.tsx` — add "Monitor" nav item
- `specs/api.md` — document timeseries routes

## Acceptance Criteria
- [ ] Time-series endpoint returns per-entity data points ordered by period
- [ ] Selecting 5 NJ counties and `hasUnemploymentRate` plots 5 labeled lines
- [ ] Anomaly dots appear on points > 2 std devs from entity mean
- [ ] Saved monitors restore all selections
- [ ] Date range filter restricts returned data points correctly
