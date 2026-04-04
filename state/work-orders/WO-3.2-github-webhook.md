# WO-3.2 — GitHub Webhook (GitHub → Platform)

**Status:** blocked  
**Spec:** `specs/api.md` (/github router), `specs/projects.md`  
**Depends on:** WO-3.1, WO-0.3  
**Blocks:** WO-3.3  

---

## Goal

Implement the webhook endpoint that receives GitHub push events, fetches changed config files from the repo, syncs them to Convex, and triggers re-hydration if a pipeline config changed.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/api/app/routers/github.py` | **Create** | GitHub router with all endpoints |
| `packages/api/app/main.py` | **Modify** | Mount github router |

---

## Steps

### 1. Create `packages/api/app/routers/github.py`

```python
import hashlib, hmac, json
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.services.github_service import github_service
from app.services.convex_client import convex
from app.core.config import settings

router = APIRouter(prefix="/github", tags=["github"])

# Config files in a project repo that we care about
WATCHED_PATTERNS = [
    "configs/apis/",
    "configs/pipelines/",
    "configs/ontology/",
    "ontology/extension.yaml",
    "rail.yaml",
]

def _is_watched(path: str) -> bool:
    return any(path.startswith(p) for p in WATCHED_PATTERNS)
```

### 2. `POST /github/sync` — Webhook handler

```python
@router.post("/sync")
async def github_sync(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    if not github_service.verify_webhook(body, signature):
        raise HTTPException(401, "Invalid webhook signature")
    
    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event")
    
    if event != "push":
        return {"ignored": True, "event": event}
    
    repo = payload["repository"]["full_name"]
    before_sha = payload["before"]
    after_sha = payload["after"]
    
    # Find the project linked to this repo
    project = await convex.query("projects:getByGithubRepo", {"github": repo})
    if not project:
        return {"ignored": True, "reason": "no project linked to this repo"}
    
    background_tasks.add_task(_sync_repo_changes, repo, before_sha, after_sha, project)
    return {"synced": True, "project": project["slug"]}


async def _sync_repo_changes(repo: str, before_sha: str, after_sha: str, project: dict):
    """Background: fetch changed files and sync to Convex, then maybe trigger hydration."""
    changed = await github_service.list_changed_files(repo, before_sha, after_sha)
    watched = [f for f in changed if _is_watched(f)]
    
    synced_count = 0
    pipeline_changed = False
    
    for path in watched:
        content = await github_service.get_file(repo, path, ref=after_sha)
        
        if path.startswith("configs/apis/"):
            slug = path.removeprefix("configs/apis/").removesuffix(".yaml")
            await convex.mutation("configs:upsertApi", {"slug": slug, "content": content, "source": "github"})
            synced_count += 1
        elif path.startswith("configs/pipelines/"):
            slug = path.removeprefix("configs/pipelines/").removesuffix(".yaml")
            await convex.mutation("configs:upsertPipeline", {"slug": slug, "content": content, "source": "github"})
            pipeline_changed = True
            synced_count += 1
        elif path.startswith("configs/ontology/"):
            slug = path.removeprefix("configs/ontology/").removesuffix(".yaml")
            await convex.mutation("configs:upsertOntology", {"slug": slug, "content": content, "source": "github"})
            synced_count += 1
    
    # Trigger hydration if pipeline or ontology changed
    if pipeline_changed and project.get("pipelineConfigSlug"):
        from app.routers.jobs import _trigger_job
        await _trigger_job(project["pipelineConfigSlug"], project["_id"])
```

### 3. `GET /github/status/{project_slug}`

```python
@router.get("/status/{project_slug}")
async def github_status(project_slug: str):
    project = await convex.query("projects:getBySlug", {"slug": project_slug})
    if not project:
        raise HTTPException(404, "Project not found")
    return {
        "github": project.get("github"),
        "defaultBranch": project.get("defaultBranch", "main"),
        "lastHydratedAt": project.get("lastHydratedAt"),
        "in_sync": True,  # placeholder — implement content hash comparison later
    }
```

### 4. `POST /github/link`

```python
class LinkRequest(BaseModel):
    project_slug: str
    github_repo: str  # "owner/repo"

@router.post("/link")
async def link_github(req: LinkRequest):
    # Validate the repo is accessible with current GitHub App installation
    try:
        await github_service.get_installation_token(req.github_repo)
    except Exception as e:
        raise HTTPException(422, f"Cannot access {req.github_repo}: {e}")
    
    await convex.mutation("projects:updateBySlug", {
        "slug": req.project_slug,
        "github": req.github_repo,
        "defaultBranch": "main",
    })
    return {"linked": True, "repo": req.github_repo}
```

### 5. Add `projects:getByGithubRepo` Convex function

In `convex/projects.ts`, add a query that looks up a project by its `github` field. Add an index `by_github` on the `projects` table.

### 6. Mount router in `main.py`

```python
from app.routers import github
app.include_router(github.router, prefix="/api/v1")
```

---

## Acceptance

- [ ] Sending a push webhook with valid HMAC signature triggers sync
- [ ] Changed `configs/apis/*.yaml` files are upserted in Convex
- [ ] If a pipeline config changed, hydration is triggered automatically
- [ ] Invalid signature returns 401
- [ ] `GET /github/status/{slug}` returns repo and sync info
- [ ] `POST /github/link` successfully links a project to a repo
