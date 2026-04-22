import json
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.services.github_service import github_service
from app.services.convex_client import convex
from app.services.repo_contract_service import (
    dedupe_changed_paths,
    manifest_updates_from_content,
    parse_config_path,
)
from app.services.safe_publish_service import record_publish_success

router = APIRouter(prefix="/github", tags=["github"])

class PublishRequest(BaseModel):
    project_slug: str
    files: list[dict]
    commit_message: str | None = None
    strategy: str = "direct_commit"

@router.post("/publish")
async def publish_to_github(req: PublishRequest):
    project = await convex.query("projects:getBySlug", {"slug": req.project_slug})
    if not project:
        raise HTTPException(404, "Project not found")

    repo = project.get("github")
    if not repo:
        raise HTTPException(422, "Project is not linked to a GitHub repo")

    branch = project.get("defaultBranch", "main")
    if req.strategy != "direct_commit":
        raise HTTPException(422, f"Unsupported publish strategy: {req.strategy}")

    # Validate all paths are within allowed directories
    ALLOWED_PREFIXES = [
        "configs/apis/",
        "configs/pipelines/",
        "configs/ontology/",
        ".ontology/ontologies/",
        ".ontology/pipelines/",
        ".ontology/sources/",
        "rail.yaml",
    ]
    for f in req.files:
        path = f["path"]
        if not (path == "rail.yaml" or any(path.startswith(p) for p in ALLOWED_PREFIXES)):
            raise HTTPException(422, f"Path not allowed: {path}")
        if ".." in path:
            raise HTTPException(422, f"Path traversal not allowed: {path}")

    message = req.commit_message or f"chore: sync configs from RAIL platform"
    result = await github_service.commit_files(repo, branch, req.files, message)
    response = {
        "published": len(result["files"]),
        "strategy": req.strategy,
        "commit_sha": result["commit_sha"],
        "branch": result["branch"],
        "changed": result["changed"],
        "files": result["files"],
    }
    await record_publish_success(project["_id"], response)
    return response

# Config files in a project repo that we care about
WATCHED_PATTERNS = [
    "configs/apis/",
    "configs/pipelines/",
    "configs/ontology/",
    ".ontology/ontologies/",
    ".ontology/pipelines/",
    ".ontology/sources/",
    "rail.yaml",
]

def _is_watched(path: str) -> bool:
    return any(path.startswith(p) for p in WATCHED_PATTERNS)

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
    watched = dedupe_changed_paths([f for f in changed if _is_watched(f)])

    synced_count = 0
    pipeline_changed = False

    for path in watched:
        content = await github_service.get_file(repo, path, ref=after_sha)
        if path == "rail.yaml":
            updates = manifest_updates_from_content(content)
            if updates:
                await convex.mutation("projects:update", {
                    "slug": project["slug"],
                    **updates,
                })
                synced_count += 1
            continue

        parsed = parse_config_path(path)
        if not parsed:
            continue
        kind, slug = parsed
        if kind == "apis":
            existing = await convex.query("configs:getApi", {"slug": slug})
            if existing and existing.get("content") == content:
                continue
            await convex.mutation("configs:upsertApi", {"slug": slug, "content": content, "source": "github"})
        elif kind == "pipelines":
            existing = await convex.query("configs:getPipeline", {"slug": slug})
            if existing and existing.get("content") == content:
                continue
            await convex.mutation("configs:upsertPipeline", {"slug": slug, "content": content, "source": "github"})
            pipeline_changed = True
        else:
            existing = await convex.query("configs:getOntology", {"slug": slug})
            if existing and existing.get("content") == content:
                continue
            await convex.mutation("configs:upsertOntology", {"slug": slug, "content": content, "source": "github"})
        synced_count += 1

    # Trigger hydration if pipeline or ontology changed
    if pipeline_changed and project.get("pipelineConfigSlug"):
        from app.routers.jobs import _trigger_job
        await _trigger_job(project["pipelineConfigSlug"], project["_id"])

@router.get("/status/{project_slug}")
async def github_status(project_slug: str):
    project = await convex.query("projects:get", {"slug": project_slug})
    if not project:
        raise HTTPException(404, "Project not found")
    return {
        "github": project.get("github"),
        "defaultBranch": project.get("defaultBranch", "main"),
        "githubSyncMode": project.get("githubSyncMode", "manual"),
        "lastPublishedCommitSha": project.get("lastPublishedCommitSha"),
        "lastPublishedAt": project.get("lastPublishedAt"),
        "lastPublishError": project.get("lastPublishError"),
        "lastHydratedAt": project.get("lastHydratedAt"),
        "in_sync": True,  # placeholder — implement content hash comparison later
    }

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

    await convex.mutation("projects:update", {
        "slug": req.project_slug,
        "github": req.github_repo,
        "defaultBranch": "main",
    })
    return {"linked": True, "repo": req.github_repo}
