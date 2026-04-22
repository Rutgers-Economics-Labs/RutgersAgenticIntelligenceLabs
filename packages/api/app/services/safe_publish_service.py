from __future__ import annotations

import time
from typing import Any

from app.services.convex_client import convex
from app.services.github_service import github_service
from app.services.repo_contract_service import (
    build_config_files,
    infer_github_repo,
    render_rail_manifest,
)


SAFE_SYNC_MODES = {"auto_safe", "auto_all"}
MANIFEST_BACKED_FIELDS = {
    "name",
    "description",
    "defaultBranch",
    "ontologyConfigSlug",
    "apiConfigSlugs",
    "pipelineConfigSlug",
}


async def should_auto_publish(project: dict[str, Any]) -> bool:
    mode = project.get("githubSyncMode") or "manual"
    repo = infer_github_repo(project.get("github") or project.get("gitRepoUrl"))
    return mode in SAFE_SYNC_MODES and bool(repo)


def commit_message_for_config(kind: str, slug: str, action: str) -> str:
    noun = {"apis": "source", "ontologies": "ontology", "pipelines": "pipeline"}[kind]
    verb = "create" if action == "create" else "update"
    return f"chore: {verb} {noun} config {slug}"


def commit_message_for_manifest(slug: str) -> str:
    return f"chore: sync project manifest for {slug}"


async def publish_config_files(project: dict[str, Any], kind: str, slug: str, content: str, *, action: str) -> dict[str, Any]:
    repo = infer_github_repo(project.get("github") or project.get("gitRepoUrl"))
    if not repo:
        raise RuntimeError("Project is not linked to a GitHub repository")
    branch = project.get("defaultBranch") or "main"
    files = [file.__dict__ for file in build_config_files(kind, slug, content)]
    result = await github_service.commit_files(
        repo,
        branch,
        files,
        commit_message_for_config(kind, slug, action),
    )
    return {"published": True, **result}


async def publish_manifest(project: dict[str, Any]) -> dict[str, Any]:
    repo = infer_github_repo(project.get("github") or project.get("gitRepoUrl"))
    if not repo:
        raise RuntimeError("Project is not linked to a GitHub repository")
    branch = project.get("defaultBranch") or "main"
    existing = await github_service.get_file_metadata(repo, "rail.yaml", ref=branch)
    content = render_rail_manifest(project, existing["content"] if existing else None)
    result = await github_service.commit_files(
        repo,
        branch,
        [{"path": "rail.yaml", "content": content}],
        commit_message_for_manifest(project["slug"]),
    )
    return {"published": True, "rendered_manifest": content, **result}


async def record_publish_success(project_id: str, publish_result: dict[str, Any]) -> None:
    await convex.mutation("projects:updateById", {
        "projectId": project_id,
        "lastPublishedCommitSha": publish_result.get("commit_sha"),
        "lastPublishedAt": int(time.time() * 1000),
        "lastPublishError": "",
    })


async def record_publish_failure(project_id: str, message: str) -> None:
    await convex.mutation("projects:updateById", {
        "projectId": project_id,
        "lastPublishError": message,
    })


async def rollback_project_update(project_id: str, previous: dict[str, Any]) -> None:
    patch = {
        "projectId": project_id,
        "name": previous.get("name"),
        "description": previous.get("description"),
        "gitRepoUrl": previous.get("gitRepoUrl"),
        "localRepoPath": previous.get("localRepoPath"),
        "manifestPath": previous.get("manifestPath"),
        "ontologyConfigSlug": previous.get("ontologyConfigSlug"),
        "apiConfigSlugs": previous.get("apiConfigSlugs") or [],
        "pipelineConfigSlug": previous.get("pipelineConfigSlug"),
        "status": previous.get("status"),
        "creationStatus": previous.get("creationStatus"),
        "briefHash": previous.get("briefHash"),
        "researchGraphSummary": previous.get("researchGraphSummary"),
        "sourceReadinessCounts": previous.get("sourceReadinessCounts"),
        "lastJobId": previous.get("lastJobId"),
        "activeOntologyDbPath": previous.get("activeOntologyDbPath"),
        "activeOntologyOwlPath": previous.get("activeOntologyOwlPath"),
        "activeOntologyDuckdbPath": previous.get("activeOntologyDuckdbPath"),
        "activeOntologyEmbeddingsPath": previous.get("activeOntologyEmbeddingsPath"),
        "github": previous.get("github"),
        "defaultBranch": previous.get("defaultBranch"),
        "githubSyncMode": previous.get("githubSyncMode") or "manual",
        "lastPublishedCommitSha": previous.get("lastPublishedCommitSha"),
        "lastPublishedAt": previous.get("lastPublishedAt"),
        "lastPublishError": previous.get("lastPublishError"),
        "ontologyTemplates": previous.get("ontologyTemplates"),
        "agentModel": previous.get("agentModel"),
        "agentAllowedActions": previous.get("agentAllowedActions"),
        "lastHydratedAt": previous.get("lastHydratedAt"),
    }
    await convex.mutation("projects:updateById", patch)


async def rollback_config_update(kind: str, slug: str, previous: dict[str, Any] | None) -> None:
    if previous is None:
        await convex.mutation(f"configs:delete{_kind_name(kind)}", {"slug": slug})
        return

    payload = {
        "slug": slug,
        "content": previous["content"],
        "parsedSpec": previous.get("parsedSpec") or {},
        "name": previous["name"],
        "isPublic": previous.get("isPublic", False),
    }
    if kind == "apis":
        payload["tags"] = previous.get("tags") or []
        await convex.mutation("configs:updateApi", payload)
    elif kind == "ontologies":
        await convex.mutation("configs:updateOntology", payload)
    else:
        payload["tags"] = previous.get("tags") or []
        payload["referencedApiSlugs"] = previous.get("referencedApiSlugs") or []
        await convex.mutation("configs:updatePipeline", payload)


def _kind_name(kind: str) -> str:
    return {"apis": "Api", "ontologies": "Ontology", "pipelines": "Pipeline"}[kind]
