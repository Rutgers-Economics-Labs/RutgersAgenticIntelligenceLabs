# WO-1.2 — Ontology Templates

**Status:** blocked  
**Spec:** `specs/ontology-kernel.md`  
**Depends on:** WO-0.3  
**Blocks:** WO-2.3 (project creation flow)  

---

## Goal

Build the ontology template system: Convex table, API router, seed initial templates (us-geography, economic-indicators, demographics, platform-objects), and a template picker in the project creation flow.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/convex/schema.ts` | **Modify** | Add `ontologyTemplates` table |
| `packages/web/convex/ontologyTemplates.ts` | **Create** | CRUD functions |
| `packages/api/app/routers/ontology_templates.py` | **Create** | REST router |
| `packages/api/app/main.py` | **Modify** | Mount ontology-templates router |
| `packages/api/app/routers/projects.py` | **Modify** | Apply selected templates on `POST /` project creation |
| `packages/web/app/(platform)/registry/ontology-templates/page.tsx` | **Create** | Template gallery (depends on WO-1.1 tab structure) |
| `scripts/seed_convex.py` | **Modify** | Seed 4 initial templates |

---

## Steps

### 1. Add `ontologyTemplates` to `packages/web/convex/schema.ts`

Same shape as `connectorTemplates`:

```typescript
ontologyTemplates: defineTable({
  slug: v.string(),
  name: v.string(),
  description: v.string(),
  version: v.string(),
  tags: v.array(v.string()),
  content: v.string(),       // ontology YAML (classes, properties)
  createdAt: v.number(),
  updatedAt: v.number(),
}).index("by_slug", ["slug"]),
```

Run `npx convex deploy` after.

### 2. Create `packages/web/convex/ontologyTemplates.ts`

Export: `getBySlug`, `list`, `listByTag`, `create`, `update`, `remove`.

### 3. Create `packages/api/app/routers/ontology_templates.py`

Routes per `specs/api.md`:
- `GET /` — list with optional `tags` filter
- `GET /{slug}` — single template
- `POST /` — create
- `PUT /{slug}` — update
- `DELETE /{slug}` — delete
- `POST /{slug}/validate` — validate content as `config_type: "ontology"`

Mount in `main.py` at `/api/v1/ontology-templates`.

### 4. Seed initial templates in `scripts/seed_convex.py`

#### `us-geography` template
Classes: `Nation`, `State`, `County`, `Municipality`, `ZipCode`
Properties: `hasFIPS`, `hasStateAbbreviation`, `hasStateName`, `hasRegion`, `hasPopulation`
Object properties: `isPartOf` (State→Nation, County→State, Municipality→County)

#### `economic-indicators` template  
Classes: `LaborIndicator`, `HousingIndicator`, `IncomeIndicator`, `GDPIndicator`
Properties: `hasValue`, `hasUnit`, `hasDate`, `hasSeries`, `hasFrequency`, `hasSeasonal`
Object properties: `measuredIn` (indicator→geography)

#### `demographics` template
Classes: `DemographicGroup`, `AgeGroup`, `RaceEthnicityGroup`
Properties: `hasCount`, `hasPercent`, `hasYear`
Object properties: `characterizes` (demographic→geography)

#### `platform-objects` template
Classes: `DataSource`, `Pipeline`, `AgentSession`, `Project`
Properties: `hasPipelineSlug`, `hasProjectSlug`, `hasRunStatus`, `hasStartedAt`, `hasEndedAt`

### 5. Apply templates on project creation

In `POST /api/v1/projects/`, when `ontologyTemplates` is provided:

```python
if data.get("ontologyTemplates"):
    # Fetch each template, merge their YAML into the project's initial ontology config
    merged_onto = {"uri": f"http://rail.rutgers.edu/ontology/{slug}", "classes": [], "data_properties": [], "object_properties": []}
    for template_slug in data["ontologyTemplates"]:
        tpl = await convex.query("ontologyTemplates:getBySlug", {"slug": template_slug})
        tpl_content = yaml.safe_load(tpl["content"])
        merged_onto["classes"].extend(tpl_content.get("classes", []))
        merged_onto["data_properties"].extend(tpl_content.get("data_properties", []))
        merged_onto["object_properties"].extend(tpl_content.get("object_properties", []))
    # Create as the project's initial ontologyConfig
    await convex.mutation("configs:createOntology", {...})
```

---

## Acceptance

- [ ] `ontologyTemplates` Convex table exists after `npx convex deploy`
- [ ] `GET /api/v1/ontology-templates` returns seeded templates
- [ ] Creating a project with `ontologyTemplates: ["us-geography", "economic-indicators"]` generates a merged ontology config
- [ ] Template gallery renders in `/registry` (Ontology Templates tab)
