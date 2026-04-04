# WO-1.1 — Connector Template UI

**Status:** blocked  
**Spec:** `specs/connectors.md`, `specs/frontend.md`  
**Depends on:** WO-0.2  
**Blocks:** nothing  

---

## Goal

Redesign `/registry` into a two-tab gallery (Connectors / Ontology Templates), add a YAML editor for creating/editing connector templates, and add a "Use Template" button that forks a template into a project API config.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/app/(platform)/registry/page.tsx` | **Modify** | Add tabs: Connectors + Ontology Templates |
| `packages/web/app/(platform)/registry/connectors/page.tsx` | **Create** | Connector gallery page |
| `packages/web/app/(platform)/registry/ontology-templates/page.tsx` | **Create** | Ontology template gallery page |
| `packages/web/components/registry/ConnectorCard.tsx` | **Create** | Card with name, description, tags, "Use" button |
| `packages/web/components/registry/ConnectorEditor.tsx` | **Create** | YAML editor + validate + save |
| `packages/web/lib/api.ts` | **Modify** | Add `connectors` namespace |

---

## Steps

### 1. Update `/registry/page.tsx`

Replace current single-page registry with a tabbed layout:

```tsx
// Tab 1: "Connectors" → /registry/connectors
// Tab 2: "Ontology Templates" → /registry/ontology-templates
// Tab 3: "Data Catalog" → keep existing dataSourceRegistry view
```

Use shadcn `Tabs` component. Each tab routes to a sub-page.

### 2. Create `ConnectorCard.tsx`

Props: `{slug, name, description, version, tags[], usageCount}`

Display:
- Name + version badge
- Description (one sentence)
- Tag chips (economics, census, real-time, etc.)
- Usage count (faded)
- "View YAML" toggle — inline code block with the template content
- "Use Template" button — opens a dialog with a fork form

### 3. "Use Template" fork dialog

When user clicks "Use Template":
1. Show a form: Name, Slug, Project (dropdown of their projects)
2. Pre-fill slug from template slug + project suffix
3. On submit: call `POST /api/v1/configs/apis` with `{name, slug, content: "extends: <template-slug>\nparams: {}\n"}`
4. Show success toast with link to the configs page

### 4. Create `ConnectorEditor.tsx`

Full-screen YAML editor for creating/editing connector templates.

- Monaco-style textarea (use existing `YamlEditor.tsx` if available)
- "Validate" button → `POST /api/v1/connectors/{slug}/validate` → show errors inline
- "Preview Resolved" button → `POST /api/v1/connectors/resolve` with the current content → show merged YAML in a side panel
- "Save" button → `PUT /api/v1/connectors/{slug}` or `POST /api/v1/connectors`

### 5. Add `connectors` namespace to `lib/api.ts`

```typescript
connectors: {
  list: (q?: string, tags?: string[]) => GET("/connectors"),
  get: (slug: string) => GET(`/connectors/${slug}`),
  create: (data: ConnectorTemplate) => POST("/connectors", data),
  update: (slug: string, data: Partial<ConnectorTemplate>) => PUT(`/connectors/${slug}`, data),
  remove: (slug: string) => DELETE(`/connectors/${slug}`),
  validate: (slug: string) => POST(`/connectors/${slug}/validate`, {}),
  resolve: (basContent: string, extendsSlug: string) => POST("/connectors/resolve", {...}),
}
```

### 6. Connector gallery page (`/registry/connectors`)

- Search bar (filters by name/description/tags)
- Provider filter chips (FRED, Census, BLS, WorldBank, generic, ...)
- Grid of `ConnectorCard`s
- "+ New Connector" button → opens `ConnectorEditor` in create mode

---

## Acceptance

- [ ] `/registry` shows three tabs: Connectors, Ontology Templates, Data Catalog
- [ ] Connector gallery loads templates from `GET /api/v1/connectors`
- [ ] Clicking "Use Template" creates a new API config in the selected project
- [ ] "Validate" in the editor returns errors/success from the API
- [ ] "Preview Resolved" shows the deep-merged YAML
- [ ] "+ New Connector" allows creating a template stored in Convex
