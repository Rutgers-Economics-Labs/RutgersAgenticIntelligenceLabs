# Work Order 25 — Versioned Analysis Outputs

## Layer
5 — Self-Updating Analyses

## Goal
Store every analysis run as an immutable versioned record so researchers can compare results across time, rollback to a prior version, and audit how findings changed as data was refreshed.

## Steps

### 1. Analysis runs table in Convex
Add to `convex/schema.ts`:

```ts
analysisRuns: defineTable({
  workspaceId: v.id("workspaces"),
  cellId: v.string(),              // which workspace cell triggered this run
  analysisType: v.string(),        // "did_analysis" | "python" | "sql" | etc.
  config: v.any(),                 // the config dict used
  result: v.any(),                 // full result JSON
  ontologyVersion: v.string(),     // hash of ontology state at time of run
  pipelineSlug: v.optional(v.string()),
  createdAt: v.number(),
  durationMs: v.optional(v.number()),
  status: v.union(v.literal("success"), v.literal("error")),
  errorMessage: v.optional(v.string()),
})
  .index("by_workspace", ["workspaceId"])
  .index("by_cell", ["workspaceId", "cellId"])
  .index("by_created", ["createdAt"])
```

### 2. Convex functions
File: `packages/web/convex/analysisRuns.ts`

- `createRun(workspaceId, cellId, analysisType, config, result, ...)` — insert
- `listRunsForCell(workspaceId, cellId)` — ordered by `createdAt` desc
- `getRunById(runId)` — single run
- `listRunsForWorkspace(workspaceId)` — all runs, ordered by `createdAt` desc

### 3. Ontology version hash
File: `packages/api/app/services/ontology_service.py`

Add:
```python
def get_version_hash(db_key: str) -> str:
    """
    Returns a short hash of the ontology's current state —
    based on the count of individuals and last modified time of the OWL file.
    Used to tag analysis runs with the data version they were run against.
    """
```

### 4. Auto-save runs from the agent
In `agent_service.py`, when a tool call produces an analysis result (SQL result, Python execution, or analysis plugin output), call the Convex `createRun` mutation to persist the result.

Include `ontologyVersion` from `ontology_service.get_version_hash()`.

### 5. Version history UI
In the AI Workspace, each completed analysis cell shows a history icon (clock). Clicking opens a side panel listing prior runs for that cell:

- Run date + time
- Data version hash (short)
- Status (success / error)
- Duration
- "View" button — replaces the cell's current result with the historical result
- "Compare" button — opens a diff view side-by-side (metrics only for now)

### 6. Workspace cell versioning
Update the `workspaces` Convex table cell type to include:
```ts
activeRunId: v.optional(v.string()),  // which analysisRun is currently displayed
```

## Affected Files
- `packages/web/convex/schema.ts` — add `analysisRuns` table
- `packages/web/convex/analysisRuns.ts` — **create**
- `packages/api/app/services/ontology_service.py` — add `get_version_hash()`
- `packages/api/app/services/agent_service.py` — persist runs after tool calls
- `packages/web/app/(dashboard)/workspace/page.tsx` — version history panel
- `specs/frontend.md` — document new table and functions

## Acceptance Criteria
- [ ] Each analysis tool call creates an `analysisRun` record in Convex
- [ ] Version history panel lists all prior runs for a cell
- [ ] "View" restores a historical result in the cell
- [ ] Each run is tagged with an ontology version hash
- [ ] Runs are not mutated — fully immutable after creation
