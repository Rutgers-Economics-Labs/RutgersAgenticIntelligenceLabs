# WO-3.3 — Publish to GitHub (Platform → GitHub)

**Status:** blocked  
**Spec:** `specs/api.md`, `specs/projects.md`  
**Depends on:** WO-3.1, WO-3.2  
**Blocks:** WO-4.2 (`publish_to_github` agent tool)  

---

## Goal

Let users commit config changes made on the platform back to the project's GitHub repo via a single button. Handles idempotent sync (the resulting push fires the webhook, which the platform handles without re-triggering an infinite loop).

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/api/app/routers/github.py` | **Modify** | Add `POST /github/publish` endpoint |
| `packages/web/app/[project]/settings/page.tsx` | **Modify** | Add "Publish to GitHub" button (depends on WO-2.3) |

---

## Steps

### 1. Add `POST /github/publish` in `github.py`

```python
class PublishRequest(BaseModel):
    project_slug: str
    files: list[dict]   # [{path: str, content: str}]
    commit_message: str | None = None

@router.post("/publish")
async def publish_to_github(req: PublishRequest):
    project = await convex.query("projects:getBySlug", {"slug": req.project_slug})
    if not project:
        raise HTTPException(404, "Project not found")
    
    repo = project.get("github")
    if not repo:
        raise HTTPException(422, "Project is not linked to a GitHub repo")
    
    branch = project.get("defaultBranch", "main")
    
    # Validate all paths are within allowed directories (path-safety check)
    ALLOWED_PREFIXES = ["configs/apis/", "configs/pipelines/", "configs/ontology/", "ontology/"]
    for f in req.files:
        path = f["path"]
        if not any(path.startswith(p) for p in ALLOWED_PREFIXES):
            raise HTTPException(422, f"Path not allowed: {path}")
        if ".." in path:
            raise HTTPException(422, f"Path traversal not allowed: {path}")
    
    message = req.commit_message or f"chore: sync configs from RAIL platform"
    results = []
    
    for file in req.files:
        path = file["path"]
        content = file["content"]
        
        # Get current SHA if file exists (required by GitHub API for updates)
        sha = None
        try:
            existing = await github_service.get_file(repo, path, ref=branch)
            # File exists — get its SHA
            token = await github_service.get_installation_token(repo)
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.github.com/repos/{repo}/contents/{path}",
                    params={"ref": branch},
                    headers={"Authorization": f"token {token}"},
                )
                sha = r.json().get("sha")
        except Exception:
            pass  # File doesn't exist yet — create it
        
        result = await github_service.put_file(repo, path, content, message, sha=sha)
        results.append({"path": path, **result})
    
    return {"published": len(results), "files": results}
```

### 2. "Publish to GitHub" button on Settings page

In `/[project]/settings/page.tsx`, in the GitHub Integration section:

```tsx
async function publishToGitHub() {
  // Fetch all current configs for this project
  const apiConfigs = await fetchProjectApiConfigs(projectSlug)
  const pipelineConfig = await fetchProjectPipelineConfig(projectSlug)
  
  const files = [
    ...apiConfigs.map(c => ({
      path: `configs/apis/${c.slug}.yaml`,
      content: c.content,
    })),
    pipelineConfig && {
      path: `configs/pipelines/${pipelineConfig.slug}.yaml`,
      content: pipelineConfig.content,
    },
  ].filter(Boolean)
  
  await api.github.publish({
    project_slug: projectSlug,
    files,
    commit_message: "chore: sync configs from RAIL platform",
  })
}
```

Show a confirmation dialog before publishing (lists files to be committed).

### 3. Idempotency — prevent webhook loop

The publish push fires the webhook (WO-3.2). The sync handler must detect that the incoming content matches what's already in Convex and skip the upsert + hydration trigger.

In `_sync_repo_changes`, before upserting a config:
```python
existing = await convex.query("configs:getApiBySlug", {"slug": slug})
if existing and existing.get("content") == content:
    continue  # no change — skip
```

---

## Acceptance

- [ ] "Publish to GitHub" on the settings page commits all project configs to the repo
- [ ] Files outside `configs/` or `ontology/` are rejected with 422
- [ ] Path traversal attempts (`../../../.env`) are rejected
- [ ] The resulting webhook push does not trigger re-hydration (idempotent sync)
- [ ] Commit shows in the GitHub repo with the correct message
