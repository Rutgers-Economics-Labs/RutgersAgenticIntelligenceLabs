# Work Order 23 — Pipeline Dependency Graph

## Layer
5 — Self-Updating Analyses

## Goal
Build a dependency graph that tracks which analysis outputs depend on which pipelines and ontology classes, so the system knows what needs to be re-run when data changes.

## Steps

### 1. Dependency model in Convex
Add a `dependencies` table to `convex/schema.ts`:

```ts
dependencies: defineTable({
  sourceType: v.union(v.literal("pipeline"), v.literal("ontology_class")),
  sourceSlug: v.string(),          // pipeline slug or OWL class name
  dependentType: v.union(v.literal("analysis"), v.literal("workspace_cell")),
  dependentId: v.string(),         // analysis run ID or workspace cell ID
  registeredAt: v.number(),
})
  .index("by_source", ["sourceType", "sourceSlug"])
  .index("by_dependent", ["dependentType", "dependentId"])
```

### 2. Convex functions
File: `packages/web/convex/dependencies.ts`

- `registerDependency(sourceType, sourceSlug, dependentType, dependentId)` — upsert
- `getDependentsOf(sourceType, sourceSlug)` — returns all downstream dependents
- `getDependenciesOf(dependentType, dependentId)` — returns all upstream sources
- `removeDependency(dependentType, dependentId)` — cleanup when analysis deleted

### 3. Agent registration
In `agent_service.py`, after any tool call that produces an analysis result (`run_did_analysis`, `run_panel_regression`, `execute_python` that reads ontology data), register the dependency by calling the Convex `registerDependency` mutation via the HTTP API.

### 4. Dependency graph API endpoint
File: `packages/api/app/routers/dependencies.py`

```
GET /api/v1/dependencies/graph
```

Returns a node-edge graph JSON:
```json
{
  "nodes": [
    {"id": "pipeline:nj_employment", "type": "pipeline", "label": "NJ Employment"},
    {"id": "analysis:did_001", "type": "analysis", "label": "DiD: Employment ~ Min Wage"}
  ],
  "edges": [
    {"source": "pipeline:nj_employment", "target": "analysis:did_001"}
  ]
}
```

### 5. Dependency graph UI
Add a "Dependencies" tab to the Jobs page (or a standalone `/dependencies` page).

Render the graph using `@xyflow/react` (React Flow):
- Pipelines shown as blue rectangles
- Analyses shown as green circles
- Edges show data flow direction
- Click a node to see its details

## Affected Files
- `packages/web/convex/schema.ts` — add `dependencies` table
- `packages/web/convex/dependencies.ts` — **create**
- `packages/api/app/services/agent_service.py` — register dependencies after analysis tool calls
- `packages/api/app/routers/dependencies.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/app/(dashboard)/dependencies/page.tsx` — **create**
- `packages/web/components/layout/Sidebar.tsx` — add nav item

## Acceptance Criteria
- [ ] Running an analysis via the agent registers a dependency in Convex
- [ ] `GET /api/v1/dependencies/graph` returns correct node-edge JSON
- [ ] Graph page renders pipelines and analyses as distinct node types
- [ ] Clicking a node navigates to that pipeline or analysis
