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
