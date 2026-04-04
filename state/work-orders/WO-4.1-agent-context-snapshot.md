# WO-4.1 — Project-Scoped Agent Context

**Status:** blocked  
**Spec:** `specs/agents.md`  
**Depends on:** WO-0.3  
**Blocks:** WO-4.2, WO-4.3  

---

## Goal

Update the research agent to accept a `project` parameter, assemble a structured context snapshot, filter tools to the project's `allowed_actions`, and emit a `context_snapshot` SSE event at the start of each conversation.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/api/app/services/agent_service.py` | **Modify** | Accept `project_slug`, load context snapshot, filter tools |
| `packages/api/app/routers/agent.py` | **Modify** | Pass `project` query param to `run_chat()` |

---

## Steps

### 1. Add `project_slug` to `run_chat()` in `agent_service.py`

```python
async def run_chat(
    user_message: str,
    history: list[dict],
    model: str | None = None,
    project_slug: str | None = None,
) -> AsyncGenerator[dict, None]:
```

### 2. Assemble context snapshot when `project_slug` is set

```python
context_snapshot = None
if project_slug:
    try:
        # Call the /projects/{slug}/context endpoint internally
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://localhost:8000/api/v1/projects/{project_slug}/context"
            )
            if resp.status_code == 200:
                context_snapshot = resp.json()
    except Exception:
        pass
```

Or, better: directly call the service functions rather than making an HTTP call to self:

```python
async def _build_context_snapshot(project_slug: str) -> dict:
    from app.services.convex_client import convex
    from app.services import sql_service
    
    project = await convex.query("projects:getBySlug", {"slug": project_slug})
    if not project:
        return {}
    
    context = {"project": {...}, "ontology": {}, "data_sources": [], "pipelines": []}
    
    if project.get("activeOntologyDuckdbPath"):
        sql_service.set_path(project["activeOntologyDuckdbPath"])
        context["ontology"]["schema_ddl"] = sql_service.get_schema_ddl()
        # Get class/instance counts from DuckDB
        tables = sql_service.list_tables()
        counts = []
        for t in tables:
            try:
                r = sql_service.run_query(f"SELECT COUNT(*) as n FROM {t}")
                counts.append({"name": t, "instance_count": r["rows"][0][0]})
            except Exception:
                pass
        context["ontology"]["classes"] = counts
    
    # ... data_sources, pipelines from project fields
    return context
```

### 3. Emit `context_snapshot` SSE event before the first text

```python
if context_snapshot:
    yield {"type": "context_snapshot", "data": context_snapshot}
    
    # Inject into system prompt
    import json
    context_block = f"\n\n## Project Context\n```json\n{json.dumps(context_snapshot, indent=2)}\n```\n"
    system_prompt = BASE_SYSTEM_PROMPT + context_block
else:
    system_prompt = BASE_SYSTEM_PROMPT
```

### 4. Filter tools to `allowed_actions`

```python
allowed = None
if context_snapshot:
    project_data = context_snapshot.get("project", {})
    allowed = project_data.get("agentAllowedActions")  # None = all allowed

def _filter_tools(tools: list[dict], allowed: list[str] | None) -> list[dict]:
    if allowed is None:
        return tools
    allowed_set = set(allowed)
    return [t for t in tools if t["function"]["name"] in allowed_set]

filtered_tools = _filter_tools(ALL_TOOLS, allowed)
```

### 5. Pass `project` from router to service

In `routers/agent.py`, `POST /chat`:

```python
@router.post("/chat")
async def agent_chat(req: ChatRequest, project: str | None = Query(default=None)):
    async def event_stream():
        async for event in agent_service.run_chat(
            user_message=req.message,
            history=req.history,
            model=req.model,
            project_slug=project,
        ):
            yield f"data: {json.dumps(event)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## Acceptance

- [ ] `POST /api/v1/agent/chat?project=nj-economics` emits a `context_snapshot` event before the first text
- [ ] Context snapshot includes class names, instance counts, and schema DDL
- [ ] If `agentAllowedActions` is set on the project, only those tools are available to the LLM
- [ ] Without `?project=`, the agent works as before (no regression)
- [ ] Agent correctly queries the project's DuckDB (not the global one)
