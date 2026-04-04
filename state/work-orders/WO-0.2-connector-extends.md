# WO-0.2 — Connector `extends` Resolution

**Status:** ready  
**Spec:** `specs/connectors.md`, `specs/yaml-config.md`  
**Depends on:** nothing  
**Blocks:** WO-1.1, WO-4.2  

---

## Goal

Build the connector template system end-to-end: Convex table + CRUD + deep-merge resolution in the hydration worker + YAML validation support + seeded initial templates.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/web/convex/schema.ts` | **Modify** | Add `connectorTemplates` table |
| `packages/web/convex/connectors.ts` | **Create** | CRUD functions |
| `packages/api/app/services/connector_service.py` | **Create** | `resolve()` function |
| `packages/api/app/services/hydration_worker.py` | **Modify** | Call resolve() before writing tmpdir |
| `packages/api/app/services/yaml_service.py` | **Modify** | Allow `extends` and `fields_append` fields |
| `packages/api/app/routers/connectors.py` | **Create** | REST router for connectorTemplates |
| `packages/api/app/main.py` | **Modify** | Mount connectors router |
| `scripts/seed_convex.py` | **Modify** | Seed initial 15+ connector templates |

---

## Steps

### 1. Add `connectorTemplates` to `packages/web/convex/schema.ts`

```typescript
connectorTemplates: defineTable({
  slug: v.string(),
  name: v.string(),
  description: v.string(),
  version: v.string(),
  tags: v.array(v.string()),
  content: v.string(),       // raw YAML (below the --- divider)
  usageCount: v.number(),
  createdBy: v.optional(v.string()),
  createdAt: v.number(),
  updatedAt: v.number(),
}).index("by_slug", ["slug"]),
```

Run `npx convex deploy` after.

### 2. Create `packages/web/convex/connectors.ts`

Export: `getBySlug`, `list`, `listByTag`, `create`, `update`, `remove`, `incrementUsage`.

### 3. Create `packages/api/app/services/connector_service.py`

```python
import yaml
from app.services.convex_client import convex

SCALAR_TYPES = (str, int, float, bool, type(None))

def _deep_merge(base: dict, override: dict) -> dict:
    """Project config (override) wins on conflict. fields_append appends to template fields list."""
    result = {**base}
    for key, val in override.items():
        if key == "fields_append":
            result["fields"] = result.get("fields", []) + val
        elif key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    result.pop("extends", None)
    result.pop("fields_append", None)
    return result

async def resolve(base_content: str, extends_slug: str) -> str:
    """Fetch template from Convex, deep-merge with base_content, return resolved YAML."""
    template = await convex.query("connectors:getBySlug", {"slug": extends_slug})
    if not template:
        raise ValueError(f"Connector template not found: {extends_slug}")
    template_data = yaml.safe_load(template["content"])
    project_data = yaml.safe_load(base_content)
    merged = _deep_merge(template_data, project_data)
    return yaml.dump(merged, default_flow_style=False)

async def list_templates(q: str | None = None, tags: list[str] | None = None) -> list[dict]:
    items = await convex.query("connectors:list", {})
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in i.get("name","").lower()
                 or q_lower in i.get("description","").lower()
                 or any(q_lower in t for t in i.get("tags",[]))]
    if tags:
        items = [i for i in items if any(t in i.get("tags",[]) for t in tags)]
    return items
```

### 4. Update `hydration_worker.py`

After fetching api_configs and before writing to tmpdir:

```python
from app.services import connector_service

for slug, content in list(api_configs.items()):
    parsed = yaml.safe_load(content)
    if "extends" in parsed:
        try:
            content = await connector_service.resolve(content, parsed["extends"])
            api_configs[slug] = content
        except ValueError as e:
            await _log(job_id, f"[warning] {e} — using config as-is")
```

### 5. Update `yaml_service.validate()` for `"api"` type

In the api validation block, skip the "unknown field" check for `extends` and `fields_append`:

```python
ALLOWED_TOP_LEVEL_API_FIELDS = {
    "name", "type", "url", "path", "params", "headers", "response_format",
    "response_path", "fields", "foreach", "cache_ttl", "extends", "fields_append"
}
```

### 6. Create `packages/api/app/routers/connectors.py`

Implement routes per `specs/api.md`:
- `GET /` — list with optional `q` and `tags` params
- `GET /{slug}` — single template
- `POST /` — create
- `PUT /{slug}` — update
- `DELETE /{slug}` — delete
- `POST /{slug}/validate` — validate content YAML
- `POST /resolve` — preview deep-merged result

Mount in `main.py`: `app.include_router(connectors.router, prefix="/api/v1/connectors")`

### 7. Seed connector templates in `scripts/seed_convex.py`

Add at least these templates (YAML content in the script):

| Slug | Provider | Description |
|------|----------|-------------|
| `fred-observations` | FRED | Series observations endpoint |
| `fred-series-info` | FRED | Series metadata (units, frequency, title) |
| `census-acs5-table` | Census | ACS 5-year estimates, any table |
| `census-decennial` | Census | Decennial population table |
| `census-tigerweb-counties` | Census | County geometry/FIPS list |
| `bls-series` | BLS | Single time series from BLS API v2 |
| `bls-lau` | BLS | Local Area Unemployment Statistics |
| `worldbank-indicator` | World Bank | Country indicator time series |
| `worldbank-country-info` | World Bank | Country metadata |
| `bea-regional` | BEA | Regional economic accounts |
| `oecd-dataset` | OECD | OECD SDMX-JSON dataset |
| `csv-local` | local | Local CSV file |
| `excel-local` | local | Local Excel file (.xlsx) |
| `json-rest` | generic | Generic REST API returning JSON |
| `csv-url` | generic | CSV served at a URL |

---

## Acceptance

- [ ] `connectorTemplates` table exists in Convex schema (after `npx convex deploy`)
- [ ] `GET /api/v1/connectors` returns seeded templates
- [ ] `POST /api/v1/connectors/resolve` with a project config + extends_slug returns merged YAML
- [ ] A pipeline config using `extends: fred-observations` hydrates correctly (engine sees no `extends` field)
- [ ] `yaml_service.validate("api", yaml_with_extends)` returns no errors
