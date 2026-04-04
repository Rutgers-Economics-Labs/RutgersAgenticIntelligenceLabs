# WO-4.2 — New Agent Tools

**Status:** blocked  
**Spec:** `specs/agents.md`  
**Depends on:** WO-0.2, WO-3.1, WO-4.1  
**Blocks:** nothing  

---

## Goal

Add three new tools to the research agent: `discover_sources` (search connector templates), `generate_report` (save artifact to storage), and `publish_to_github` (commit files to the project repo).

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/api/app/services/agent_service.py` | **Modify** | Add 3 new tool definitions + executors |

---

## Steps

### 1. Add `discover_sources` tool

**Definition:**
```python
{
    "type": "function",
    "function": {
        "name": "discover_sources",
        "description": "Search the shared connector template registry for data sources relevant to a topic. Use this to find what data providers are available before creating a new API config.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Topic or provider to search for"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags e.g. ['economics', 'fred', 'census']"
                },
            },
            "required": ["query"],
        },
    },
}
```

**Executor:**
```python
if name == "discover_sources":
    from app.services import connector_service
    results = await connector_service.list_templates(
        q=args["query"],
        tags=args.get("tags"),
    )
    return {"results": [{"slug": r["slug"], "name": r["name"], "description": r["description"]} for r in results[:10]]}
```

### 2. Add `generate_report` tool

**Definition:**
```python
{
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": "Save a research report or analysis artifact to platform storage. Returns a storage URL. Use after producing a complete analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Report title"},
                "content": {"type": "string", "description": "Markdown report body"},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["title", "content"],
        },
    },
}
```

**Executor:**
```python
if name == "generate_report":
    from app.services.storage_service import StorageService
    import time, json as _json
    storage = StorageService()
    job_id = f"report_{int(time.time())}"
    filename = f"{args['title'].lower().replace(' ', '_')}.md"
    content = args["content"]
    
    # Write to temp file and upload
    import tempfile, pathlib
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    
    storage_key = await storage.upload(job_id, filename, tmp_path)
    pathlib.Path(tmp_path).unlink(missing_ok=True)
    return {"storage_key": storage_key, "title": args["title"], "filename": filename}
```

### 3. Add `publish_to_github` tool

**Definition:**
```python
{
    "type": "function",
    "function": {
        "name": "publish_to_github",
        "description": "Commit one or more config files to the project's GitHub repo. Only call after the user has explicitly confirmed they want to publish.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                    "description": "Files to commit. Paths must be within configs/ or ontology/.",
                },
                "commit_message": {"type": "string"},
            },
            "required": ["files"],
        },
    },
}
```

**Executor:**
```python
if name == "publish_to_github":
    if not project_slug:
        return {"error": "publish_to_github requires a project context (pass ?project= to the chat endpoint)"}
    
    # Call the publish endpoint
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/api/v1/github/publish",
            json={
                "project_slug": project_slug,
                "files": args["files"],
                "commit_message": args.get("commit_message", "chore: publish from RAIL agent"),
            }
        )
    
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()
```

**Safety:** The `publish_to_github` executor must verify that all file paths are within `configs/` or `ontology/`. This is also enforced server-side in WO-3.3, but the agent should catch it early.

### 4. Register new tools in `ALL_TOOLS`

Add the three tool definitions to the `ALL_TOOLS` list in `agent_service.py`. They will be filtered by `allowed_actions` per WO-4.1.

---

## Acceptance

- [ ] `discover_sources(query="unemployment")` returns matching connector templates
- [ ] `generate_report(title="NJ Q1 Analysis", content="# Summary...")` returns a storage key
- [ ] `publish_to_github(files=[{path: "configs/apis/test.yaml", content: "..."}])` commits to the linked repo
- [ ] `publish_to_github` with a path like `../../.env` is rejected
- [ ] All 3 tools only appear in the agent when listed in the project's `agentAllowedActions`
