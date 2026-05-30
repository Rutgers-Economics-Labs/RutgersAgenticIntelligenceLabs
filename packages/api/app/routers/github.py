import json
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.services.github_service import github_service
from app.services.convex_client import convex
from app.services import planner_service
from app.services.repo_contract_service import (
    dedupe_changed_paths,
    manifest_updates_from_content,
    parse_config_path,
    render_rail_manifest,
)
from app.services.safe_publish_service import record_publish_success
from app.services.safe_publish_service import is_repo_publish_path_allowed

router = APIRouter(prefix="/github", tags=["github"])


async def _resolve_project_by_slug(slug: str) -> dict | None:
    try:
        project = await planner_service.resolve_project_reference(slug)
    except Exception:
        project = None
    return project if isinstance(project, dict) else None


async def _resolve_project_by_github_repo(repo: str) -> dict | None:
    try:
        return await planner_service.get_project_by_github_repo(repo)
    except Exception:
        return None


async def _persist_github_project_patch(project: dict, patch: dict) -> dict:
    project_id = str(project.get("_id") or "")
    if project_id.startswith("local:"):
        project_root = planner_service.project_root_from_record(project)
        if project_root is None:
            raise HTTPException(400, "Project has no local repo path configured")
        manifest_path = project_root / (project.get("manifestPath") or "rail.yaml")
        existing_content = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        updated_project = {**project, **patch}
        manifest_path.write_text(render_rail_manifest(updated_project, existing_content), encoding="utf-8")
        refreshed = await planner_service.resolve_project_reference(str(project.get("slug") or ""))
        return refreshed

    await convex.mutation("projects:update", {"slug": project["slug"], **patch})
    try:
        refreshed = await planner_service.resolve_project_reference(str(project.get("slug") or ""))
    except Exception:
        refreshed = None
    if isinstance(refreshed, dict):
        return refreshed
    return {**project, **patch}

class PublishRequest(BaseModel):
    project_slug: str
    files: list[dict]
    commit_message: str | None = None
    strategy: str = "direct_commit"

@router.post("/publish")
async def publish_to_github(req: PublishRequest):
    project = await _resolve_project_by_slug(req.project_slug)
    if not project:
        raise HTTPException(404, "Project not found")

    repo = project.get("github")
    if not repo:
        raise HTTPException(422, "Project is not linked to a GitHub repo")

    branch = project.get("defaultBranch", "main")
    if req.strategy != "direct_commit":
        raise HTTPException(422, f"Unsupported publish strategy: {req.strategy}")

    # Validate all paths are within allowed directories
    for f in req.files:
        path = f["path"]
        if not is_repo_publish_path_allowed(path):
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
    if not str(project.get("_id") or "").startswith("local:"):
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
    project = await _resolve_project_by_github_repo(repo)
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
        if path == "rail.yaml":
            content = await github_service.get_file(repo, path, ref=after_sha)
            updates = manifest_updates_from_content(content)
            if updates:
                project = await _persist_github_project_patch(project, updates)
                synced_count += 1
            continue

        parsed = parse_config_path(path)
        if not parsed:
            continue
        content = await github_service.get_file(repo, path, ref=after_sha)
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
        await _trigger_job(project["pipelineConfigSlug"], project.get("slug"))

@router.get("/status/{project_slug}")
async def github_status(project_slug: str):
    project = await _resolve_project_by_slug(project_slug)
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

    project = await _resolve_project_by_slug(req.project_slug)
    if not project:
        raise HTTPException(404, "Project not found")

    await _persist_github_project_patch(project, {
        "github": req.github_repo,
        "gitRepoUrl": f"https://github.com/{req.github_repo}",
        "defaultBranch": "main",
    })
    return {"linked": True, "repo": req.github_repo}
