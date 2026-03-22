# Work Order 30 — Ontology Health Panel

## Layer
7 — Dashboard and Monitoring

## Goal
Build a dedicated Ontology Health page that surfaces data quality issues, missing values, class distribution anomalies, and property coverage metrics so researchers can quickly assess the integrity of the hydrated knowledge graph.

## Steps

### 1. Health check service
File: `packages/api/app/services/health_service.py`

```python
async def run_health_checks(db_key: str) -> dict:
    """
    Returns a full health report:
    {
      "overall_score": 0.87,   # 0.0–1.0
      "checks": [
        {
          "name": "Property coverage",
          "status": "warning",   # "ok" | "warning" | "error"
          "message": "hasIncome missing for 12% of County entities",
          "affected_class": "County",
          "affected_property": "hasIncome",
          "affected_count": 50,
          "total_count": 420,
        },
        ...
      ]
    }
    """
```

Checks to run:
1. **Property coverage** — for each OWL class × data property, compute % of instances with a value
2. **Duplicate detection** — find entity URIs that appear more than once
3. **Orphaned instances** — instances with no outgoing object properties (disconnected nodes)
4. **Outlier values** — numeric properties where values are > 3 std devs from the mean
5. **Empty classes** — OWL classes with zero instances post-hydration

### 2. Health API endpoint
File: `packages/api/app/routers/health_ontology.py` (name avoids conflict with FastAPI's built-in `/health`)

```
GET /api/v1/ontology/health
```

Returns the health report JSON. Cached for 5 minutes (use `functools.lru_cache` with TTL or a module-level cache dict with timestamp).

### 3. Health page UI
File: `packages/web/app/(dashboard)/ontology/health/page.tsx`

**Header:**
- Overall score as a large circular progress indicator (green ≥ 0.9, yellow ≥ 0.7, red < 0.7)
- "Last checked" timestamp + "Re-check" button

**Checks list:**
- Each check as a row with: status icon (✓ / ⚠ / ✗), check name, message, affected count badge
- Rows are grouped by status (errors first, then warnings, then ok)
- Clicking a row navigates to the relevant Explorer page filtered to the affected class

**Class breakdown table:**
- Columns: Class | Instances | Properties | Coverage % | Outliers
- Sortable by each column

### 4. Sidebar navigation
Add "Ontology Health" under the Explorer nav section in `Sidebar.tsx`, with a badge showing warning/error count if non-zero.

### 5. Dashboard integration
On the Research Dashboard (WO-29), add a small "Ontology Health" widget in the bottom row showing the overall score and a link to the full health page.

## Affected Files
- `packages/api/app/services/health_service.py` — **create**
- `packages/api/app/routers/health_ontology.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/app/(dashboard)/ontology/health/page.tsx` — **create**
- `packages/web/components/layout/Sidebar.tsx` — add nav item with badge
- `packages/web/app/(dashboard)/page.tsx` — add health widget (WO-29)
- `specs/api.md` — document ontology health route

## Acceptance Criteria
- [ ] Health check detects missing property values and reports coverage %
- [ ] Duplicate detection finds entities with identical URIs
- [ ] Outlier detection flags numeric values > 3 std devs from mean
- [ ] Overall score is 1.0 on a perfectly clean ontology
- [ ] Health page displays checks grouped by severity
- [ ] Sidebar badge shows non-zero warning/error count
