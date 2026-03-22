# Work Order 36 — Cursor-Based Pagination at Scale

## Layer
8 — Infrastructure and Scale

## Goal
Replace all offset-based list endpoints with cursor-based pagination so that the platform remains performant as ontology data, job history, and analysis runs grow to millions of records.

## Background
Offset-based pagination (`LIMIT 100 OFFSET 500`) requires scanning all prior rows, which degrades as tables grow. Cursor-based pagination (`WHERE id > cursor LIMIT 100`) is O(1) regardless of dataset size.

## Steps

### 1. Pagination response envelope
Define a standard paginated response schema in `packages/api/app/models/pagination.py`:

```python
from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None    # base64-encoded cursor, None if no more pages
    has_more: bool
    total_count: int | None    # optional; expensive to compute, omit for large tables
```

Cursor encoding: `base64(json({"id": last_item_id, "ts": last_item_timestamp}))`.

### 2. SQL service pagination
Update `packages/api/app/services/sql_service.py`:

```python
async def run_query_paginated(
    sql: str,
    cursor: str | None = None,
    limit: int = 100,
    order_column: str = "rowid",
) -> PaginatedResponse:
    """
    Appends WHERE + ORDER BY + LIMIT to the user's SQL.
    Decodes cursor to determine starting position.
    """
```

### 3. Update list endpoints to support cursors
All list-style GET endpoints should accept `cursor` and `limit` query parameters and return `PaginatedResponse`:

| Endpoint | Change |
|---|---|
| `GET /api/v1/sql/tables` | Add cursor support |
| `GET /api/v1/ontology/entities` | Add cursor (currently returns all) |
| `GET /api/v1/jobs` | Add cursor (currently returns all jobs) |
| `GET /api/v1/dependencies/graph` | Add cursor for nodes |
| `GET /api/v1/timeseries` | Add cursor for data points |

Keep backward compatibility: if `cursor` and `limit` are omitted, existing behavior is preserved (return all, up to a hard cap of 10,000 rows).

### 4. DuckDB entity pagination
In `packages/api/app/services/ontology_service.py`, add:

```python
async def list_entities_paginated(
    db_key: str,
    class_name: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
) -> PaginatedResponse:
    """
    Returns entities in stable order (by URI).
    Cursor is the last URI seen.
    """
```

### 5. Convex query pagination
Convex natively supports cursor-based pagination via `.paginate()`. Update Convex query functions that return large lists:

In `agent.ts`, `workspaces.ts`, `analysisRuns.ts` (WO-25):
```ts
export const listSessions = query({
  args: { paginationOpts: paginationOptsValidator },
  handler: async (ctx, { paginationOpts }) => {
    return await ctx.db.query("agentSessions")
      .order("desc")
      .paginate(paginationOpts);
  },
});
```

### 6. Frontend infinite scroll
In list-heavy pages (Jobs, Workspace sessions, Analysis runs), replace full-load with infinite scroll:
- Use an `IntersectionObserver` on a sentinel div at the bottom of the list
- When sentinel is visible, fetch the next page using the `next_cursor` from the last response
- Append new items to the existing list

### 7. Explorer page pagination
The Ontology Explorer currently loads all entities. Cap at 100 and add a "Load more" button that passes the `next_cursor`.

## Affected Files
- `packages/api/app/models/pagination.py` — **create**
- `packages/api/app/services/sql_service.py` — add `run_query_paginated`
- `packages/api/app/services/ontology_service.py` — add `list_entities_paginated`
- `packages/api/app/routers/jobs.py` — cursor pagination
- `packages/api/app/routers/timeseries.py` — cursor pagination (WO-31)
- `packages/web/convex/agent.ts` — paginate `listSessions`
- `packages/web/convex/workspaces.ts` — paginate `listWorkspaces`
- `packages/web/app/(dashboard)/jobs/page.tsx` — infinite scroll
- `packages/web/app/(dashboard)/explorer/page.tsx` — load more
- `specs/api.md` — document pagination scheme

## Acceptance Criteria
- [ ] `GET /api/v1/jobs?limit=10` returns exactly 10 jobs with a `next_cursor`
- [ ] Passing `next_cursor` back returns the next 10 jobs with no overlap
- [ ] Last page has `has_more: false` and `next_cursor: null`
- [ ] Cursor is opaque to the client (base64 encoded, not a raw integer)
- [ ] Explorer page loads 100 entities then adds more on "Load more"
- [ ] No endpoint breaks when `cursor` and `limit` are omitted (backward-compatible)
