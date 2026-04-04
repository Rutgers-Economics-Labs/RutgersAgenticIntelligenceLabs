# WO-2.2 — Project-Scoped Route Layout

**Status:** blocked  
**Spec:** `specs/frontend.md`  
**Depends on:** WO-2.1  
**Blocks:** WO-2.3, WO-4.3  

---

## Goal

Create the `[project]` route segment with a project-scoped sidebar and migrate all existing project-level pages under it. Keep old flat routes as redirects.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/app/[project]/layout.tsx` | **Create** | Project shell with TopBar + project-scoped Sidebar |
| `packages/web/app/[project]/ontology/classes/page.tsx` | **Create** | Moved from `/explorer` |
| `packages/web/app/[project]/ontology/graph/page.tsx` | **Create** | Moved from `/graph` |
| `packages/web/app/[project]/sql/page.tsx` | **Create** | Moved from `/sql` |
| `packages/web/app/[project]/analysis/page.tsx` | **Create** | Moved from `/analysis` |
| `packages/web/app/[project]/jobs/page.tsx` | **Create** | Moved from `/jobs` |
| `packages/web/app/[project]/quality/page.tsx` | **Create** | Moved from `/quality` |
| `packages/web/app/[project]/agent/page.tsx` | **Create** | Moved from `/workspace` |
| `packages/web/app/[project]/questions/page.tsx` | **Create** | Moved from `/questions` |
| `packages/web/app/[project]/context/page.tsx` | **Create** | Moved from `/context` |
| `packages/web/app/(dashboard)/explorer/page.tsx` | **Modify** | Redirect to `/[project]/ontology/classes` |
| `packages/web/app/(dashboard)/graph/page.tsx` | **Modify** | Redirect |
| `packages/web/app/(dashboard)/sql/page.tsx` | **Modify** | Redirect |
| `packages/web/app/(dashboard)/workspace/page.tsx` | **Modify** | Redirect |
| `packages/web/app/(dashboard)/jobs/page.tsx` | **Modify** | Redirect |
| `packages/web/app/(dashboard)/quality/page.tsx` | **Modify** | Redirect |
| `packages/web/components/layout/Sidebar.tsx` | **Modify** | Add project-scoped nav items |

---

## Steps

### 1. Create `app/[project]/layout.tsx`

```tsx
export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { project: string };
}) {
  return (
    <div className="flex h-screen flex-col">
      <TopBar projectSlug={params.project} />
      <div className="flex flex-1 overflow-hidden">
        <ProjectSidebar projectSlug={params.project} />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
```

### 2. Project-scoped sidebar items

The project sidebar (distinct from the platform sidebar) shows:
```
Overview
Ontology
  └ Classes
  └ Graph
  └ Schema
Sources
Pipelines
SQL
Questions
Agent
Analysis
Jobs
Quality
Context
──────
Registry (shared)
Settings
```

Current active page is highlighted. All links prepend `/[project]/`.

### 3. Migrate page content

For each existing page, copy the component to the new path and update:
- Any hardcoded API calls that don't pass `project_id` → pass `params.project`
- Any `useSearchParams` for `?project=` → replace with `params.project` from the route

The old pages become redirects:
```tsx
// app/(dashboard)/explorer/page.tsx
import { redirect } from "next/navigation";
export default function ExplorerRedirect() {
  // Can't redirect without project context — send to /projects
  redirect("/projects");
}
```

For pages that previously took `?project=slug`, use the URL to determine where to redirect.

### 4. Pass `project_id` through all API calls

Update each migrated page's data fetching to pass `project` param:
- SQL queries: `POST /api/v1/sql` with `{query, project_id: params.project}`
- Quality report: `GET /api/v1/quality/report?project_id={params.project}`
- Ontology: already project-aware via `activeOntologyDuckdbPath`
- Agent chat: `POST /api/v1/agent/chat` with `project` param

---

## Acceptance

- [ ] Navigating to `/nj-economics/ontology/classes` renders the class browser scoped to that project
- [ ] The project-scoped sidebar shows all project nav items
- [ ] `/explorer`, `/sql`, `/workspace`, `/jobs`, `/quality` all redirect (not 404)
- [ ] SQL queries on `/nj-economics/sql` use the NJ economics DuckDB
- [ ] TopBar shows the current project in the ProjectSwitcher
