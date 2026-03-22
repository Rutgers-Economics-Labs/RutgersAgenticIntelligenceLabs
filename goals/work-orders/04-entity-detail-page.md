# Work Order 04 — Entity Detail Page

## Goal
Implement `/explorer/[id]` as a full entity detail page showing all properties, relationships, and a 1-hop force graph.

## Current State
The route `app/(dashboard)/explorer/[id]/page.tsx` does not exist. The Explorer page links to it but the destination is a 404.

## Steps

### 1. Create the page file
`packages/web/app/(dashboard)/explorer/[id]/page.tsx`

The `id` param is the entity's URI-encoded `_id` string (e.g. `State_34`).

### 2. Fetch entity data
On mount, call both in parallel:
- `ontology.entity(id)` → `EntityDetail` (properties + relationships list)
- `ontology.entityGraph(id)` → `GraphData` (1-hop nodes + links)

Show a loading skeleton while fetching. Show an error state if the entity is not found (404 from API).

### 3. Header section
- Entity name (`properties.hasName` or `id` fallback)
- Class badge (e.g. "State", "County")
- IRI in monospace, small, copyable

### 4. Properties panel
Table or grid of all `properties` key/value pairs. Format:
- Numbers: formatted with `toLocaleString()`
- Dates: human-readable
- Strings: plain text

### 5. Relationships panel
Table of `relationships`:
| Property | Target | Link |
|----------|--------|------|
| `isPartOf` | Hudson County | → |

Each target links to `/explorer/{targetId}`.

### 6. 1-hop graph
Reuse the `react-force-graph-2d` pattern from `/graph`. Dynamic import, SSR disabled. Show only the nodes and links returned by `ontology.entityGraph(id)`. Center node highlighted differently (larger, brighter color).

### 7. Back navigation
Breadcrumb: `Explorer > {class_name} > {entity_name}`. Back button returns to `/explorer`.

## Affected Files
- `packages/web/app/(dashboard)/explorer/[id]/page.tsx` — **create**

## Acceptance Criteria
- [ ] Navigating from Explorer entity card opens the detail page
- [ ] Properties table shows all fields from the API response
- [ ] Relationships table links to other entities correctly
- [ ] 1-hop graph renders with the focal entity centered
- [ ] Page handles unknown entity ID gracefully (error message, not crash)
