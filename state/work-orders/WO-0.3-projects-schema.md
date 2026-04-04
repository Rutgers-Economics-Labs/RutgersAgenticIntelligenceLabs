# WO-0.3 — Projects Schema Update

**Status:** ready  
**Spec:** `specs/projects.md`  
**Depends on:** nothing  
**Blocks:** WO-1.2, WO-2.3, WO-3.1, WO-4.1  

---

## Goal

Add the missing fields to the `projects` Convex table and expose the `/context` endpoint that returns a structured agent context snapshot for a project.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/convex/schema.ts` | **Modify** | Add 6 missing fields to `projects` table |
| `packages/web/convex/projects.ts` | **Modify** | Handle new fields in CRUD |
| `packages/api/app/routers/projects.py` | **Modify** | Add `GET /{slug}/context` endpoint |

---

## Steps

### 1. Update `projects` table in `packages/web/convex/schema.ts`

Add to the existing `projects` table definition:

```typescript
github: v.optional(v.string()),          // "owner/repo" e.g. "rutgers-rail/nj-econ"
defaultBranch: v.optional(v.string()),   // default "main"
ontologyTemplates: v.optional(v.array(v.string())),  // slugs of applied templates
agentModel: v.optional(v.string()),      // LiteLLM model string override
agentAllowedActions: v.optional(v.array(v.string())),  // allowed tool names
lastHydratedAt: v.optional(v.number()), // ms timestamp
```

Run `npx convex deploy` after.

### 2. Update `convex/projects.ts`

Ensure `create`, `update`, and `getBySlug`/`getById` functions pass through the new fields. No breaking changes — all new fields are optional.

### 3. Add `GET /api/v1/projects/{slug}/context` in `projects.py`

```python
@router.get("/{slug}/context")
async def get_project_context(slug: str):
    """Returns a structured context snapshot for agent initialization."""
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")
    
    context = {
        "project": {
            "name": project["name"],
            "slug": project["slug"],
            "status": project.get("status"),
            "last_hydrated": project.get("lastHydratedAt"),
        },
        "ontology": {},
        "data_sources": [],
        "pipelines": [],
        "analysis_plugins": [],
    }
    
    # Fetch ontology info if project is hydrated
    if project.get("activeOntologyDuckdbPath"):
        try:
            from app.services import sql_service, ontology_service
            sql_service.set_path(project["activeOntologyDuckdbPath"])
            schema = sql_service.get_schema()
            classes = await ontology_service._run(ontology_service.list_classes)
            context["ontology"] = {
                "classes": classes,
                "schema_ddl": sql_service.get_schema_ddl(),
            }
        except Exception:
            pass
    
    # Fetch data sources
    api_slugs = project.get("apiConfigSlugs", [])
    for slug_s in api_slugs:
        cfg = await convex.query("configs:getApiBySlug", {"slug": slug_s})
        if cfg:
            context["data_sources"].append({"slug": cfg["slug"], "name": cfg["name"]})
    
    # Fetch pipeline info
    pipeline_slug = project.get("pipelineConfigSlug")
    if pipeline_slug:
        pipeline = await convex.query("configs:getPipelineBySlug", {"slug": pipeline_slug})
        if pipeline:
            context["pipelines"].append({"slug": pipeline["slug"], "name": pipeline["name"]})
    
    return context
```

### 4. Update `hydration_worker.py` to set `lastHydratedAt`

After a successful hydration (step 7 in the worker), add:

```python
if project_id:
    await convex.mutation("projects:updateById", {
        "projectId": project_id,
        "lastHydratedAt": int(time.time() * 1000),
        "status": "hydrated",
    })
```

---

## Acceptance

- [ ] `projects` table has all 6 new fields after `npx convex deploy`
- [ ] `GET /api/v1/projects/{slug}/context` returns `{project, ontology, data_sources, pipelines}` for a hydrated project
- [ ] `lastHydratedAt` is set on the project record after a successful hydration run
- [ ] Existing project CRUD endpoints continue to work (no regressions)
