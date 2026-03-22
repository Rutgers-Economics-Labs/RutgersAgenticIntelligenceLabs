# Work Order 05 — Project Forking

## Goal
Add the ability to fork a project — deep-copying all its referenced configs with new slugs — so researchers can start new work from an existing baseline without modifying the original.

## Current State
The `projects` Convex table exists. The `/projects` page exists but is scaffolded. There is no fork functionality anywhere.

## Steps

### 1. Add `forkProject` Convex mutation
File: `packages/web/convex/projects.ts` (create or extend)

```typescript
export const forkProject = mutation({
  args: { projectId: v.string(), newName: v.string() },
  handler: async (ctx, { projectId, newName }) => {
    // 1. Fetch the source project
    // 2. Fetch all referenced apiConfigs, ontologyConfig, pipelineConfig
    // 3. For each config, insert a copy with slug = `${original_slug}-fork-${Date.now()}`
    // 4. Insert new project row pointing at the copied config slugs
    // 5. Return { newProjectId }
  }
})
```

Slug collision strategy: append `-copy` then a short timestamp suffix.

### 2. Add fork button to Projects page
File: `packages/web/app/(dashboard)/projects/page.tsx`

On each project card, add a "Fork" button (icon: `GitFork` from lucide-react). Clicking it:
1. Opens a small modal asking for the new project name (pre-filled with `{original} (fork)`)
2. Calls `useMutation(api.projects.forkProject)`
3. On success: navigates to the new project's page or shows a toast

### 3. Implement Projects page list view
The Projects page currently shows nothing useful. Implement:
- `useQuery(api.projects.list)` — reactive list
- Project cards: name, status badge (`draft`/`ready`/`hydrated`), approach tag, config count, Fork button, Delete button
- "New Project" button opens a create form

### 4. Add `list` and `get` queries to `convex/projects.ts`
```typescript
export const list = query({ ... })   // returns all projects ordered by createdAt desc
export const get = query({ args: { projectId }, ... })
```

### 5. Run `npx convex deploy`
After schema/function changes.

## Affected Files
- `packages/web/convex/projects.ts` — add `list`, `get`, `forkProject`
- `packages/web/app/(dashboard)/projects/page.tsx` — implement list view + fork button
- `packages/web/convex/schema.ts` — verify `projects` table matches (no change expected)

## Acceptance Criteria
- [ ] Projects page shows existing projects as cards
- [ ] Fork button + name modal appears on each card
- [ ] Forking a project creates copies of all referenced configs with new slugs
- [ ] New project appears immediately in the list (reactive)
- [ ] Forked project can be independently modified without affecting the original
