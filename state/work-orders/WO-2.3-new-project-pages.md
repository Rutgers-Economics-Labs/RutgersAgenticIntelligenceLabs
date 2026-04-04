# WO-2.3 — New Project Pages

**Status:** blocked  
**Spec:** `specs/frontend.md`  
**Depends on:** WO-2.2  
**Blocks:** WO-4.3  

---

## Goal

Build the four new project-level pages that don't exist yet: Overview dashboard, Sources (with connector picker), Ontology Schema viewer, and Settings.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/app/[project]/overview/page.tsx` | **Create** | Project dashboard |
| `packages/web/app/[project]/sources/page.tsx` | **Create** | Data sources + connector gallery |
| `packages/web/app/[project]/ontology/schema/page.tsx` | **Create** | Merged ontology YAML viewer |
| `packages/web/app/[project]/settings/page.tsx` | **Create** | Project settings + danger zone |
| `packages/web/app/[project]/page.tsx` | **Create** | Redirect → /[project]/overview |

---

## Steps

### 1. `/[project]/overview` — Project Dashboard

Four metric cards in a grid:
- **Status** — draft / ready / hydrated with color
- **Individuals** — total OWL individual count from DuckDB (query `SELECT COUNT(*) FROM sqlite_master` or sum across tables)
- **Classes** — count of classes from `GET /ontology/classes`
- **Last hydrated** — relative time from `lastHydratedAt`

Below the cards:
- **Recent jobs** — last 5 hydration jobs with status chips (`useQuery(api.jobs.listByProject)`)
- **Class breakdown chart** — horizontal bar chart (recharts) of instance counts per class

Data sources:
```tsx
const project = useQuery(api.projects.getBySlug, { slug: params.project })
const jobs = useQuery(api.jobs.listByProject, { projectSlug: params.project, limit: 5 })
// Classes from FastAPI
const { data: classes } = useSWR(`/api/v1/ontology/classes?project=${params.project}`, fetcher)
```

### 2. `/[project]/sources` — Data Sources

Split-pane layout:
- **Left panel:** Active data sources for this project (from `project.apiConfigSlugs`). Each card shows slug, last fetched, config preview button. "+ Add Source" button.
- **Right panel:** Connector template gallery (same as `/registry/connectors` but with a streamlined "Add to project" flow).

"Add Source" flow:
1. User picks a connector template from right panel
2. "Use" opens a modal: Name, Slug, any overrides (params)
3. On save: `POST /configs/apis`, then `projects:updateById` to add slug to `apiConfigSlugs`

### 3. `/[project]/ontology/schema` — Merged YAML Viewer

Read-only view of the project's compiled ontology:
- Fetch the project's `ontologyConfigSlug`, then `GET /configs/ontologies/{slug}`
- Also fetch kernel YAML (from `/api/v1/ontology-kernel` or embed directly)
- Show tabs: "Project Extension", "Kernel", "Merged"
- "Merged" tab shows what the engine actually sees — kernel + project merged

Display as a syntax-highlighted YAML block (use `packages/web/components/shared/YamlEditor.tsx` in read-only mode).

### 4. `/[project]/settings` — Project Settings

Sections:

**General**
- Project name (editable), slug (read-only), description (editable)
- Save button → `PUT /api/v1/projects/{slug}`

**GitHub Integration** (grayed out if WO-3.1 not done)
- Repository field (`owner/repo`)
- Default branch
- Last sync status + timestamp
- "Link to GitHub" button → `POST /api/v1/github/link`
- "Publish to GitHub" button → `POST /api/v1/github/publish`

**Agent Configuration**
- Model override dropdown (from `GET /agent/models`)
- Allowed actions checklist

**Danger Zone**
- "Reset project" — clears all data sources and pipeline link, sets status to draft
- "Delete project" — confirmation dialog, then `DELETE /api/v1/projects/{slug}`

---

## Acceptance

- [ ] `/[project]/overview` shows metric cards and recent jobs for the correct project
- [ ] `/[project]/sources` lists active sources and shows the connector gallery
- [ ] Adding a source from the gallery creates an API config and attaches it to the project
- [ ] `/[project]/ontology/schema` renders the project's ontology YAML
- [ ] `/[project]/settings` saves name/description changes
- [ ] Navigating to `/[project]` redirects to `/[project]/overview`
