# WO-2.1 — Top Bar + Project Switcher

**Status:** ready  
**Spec:** `specs/frontend.md`  
**Depends on:** nothing  
**Blocks:** WO-2.2  

---

## Goal

Add a persistent top bar with a project switcher dropdown to the platform. This is the foundation for the project-scoped navigation model.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/components/layout/TopBar.tsx` | **Create** | Platform top bar |
| `packages/web/components/layout/ProjectSwitcher.tsx` | **Create** | Dropdown listing all projects |
| `packages/web/app/layout.tsx` or `(platform)/layout.tsx` | **Modify** | Render TopBar at root |

---

## Steps

### 1. Create `TopBar.tsx`

```tsx
// Fixed height bar (h-12), dark background, full width
// Left: "RAIL" logo/wordmark (links to /projects)
// Center: ProjectSwitcher component (only shown when inside a project route)
// Right: "New Project" button (links to /projects?new=1)
```

Props: `{ projectSlug?: string }` — passed from layout based on active route.

### 2. Create `ProjectSwitcher.tsx`

A Convex-reactive dropdown that:
- Uses `useQuery(api.projects.list)` to get all projects
- Displays current project name + status badge
- Opens a popover listing all projects with status dots (draft=gray, ready=yellow, hydrated=green)
- Clicking a project navigates to `/[project]/overview` (or current relative page within that project)
- "All Projects" link at bottom → `/projects`

```tsx
// Use shadcn Popover + Command for searchable dropdown
<ProjectSwitcher currentSlug={slug} />
```

### 3. Mount in layout

In the root `app/layout.tsx` (or whichever layout wraps all pages), add `<TopBar />` above the existing sidebar + content layout. The TopBar should be sticky at the top.

Update the existing sidebar to not render project-level links when inside the platform-level (non-project) routes.

---

## Acceptance

- [ ] TopBar appears on every page
- [ ] ProjectSwitcher shows all projects with status dots
- [ ] Clicking a project in the switcher navigates correctly
- [ ] "New Project" button navigates to `/projects` or opens a modal
- [ ] TopBar does not break existing pages (sidebar still renders)
