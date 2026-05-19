from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any

from app.services.convex_client import convex
from app.services.github_service import github_service
from app.services.repo_contract_service import (
    build_config_files,
    infer_github_repo,
    render_rail_manifest,
)
from rail.manifest import load_manifest


SAFE_SYNC_MODES = {"auto_safe", "auto_all"}
MANIFEST_BACKED_FIELDS = {
    "name",
    "description",
    "defaultBranch",
    "ontologyConfigSlug",
    "apiConfigSlugs",
    "pipelineConfigSlug",
}
DEFAULT_REPO_PUBLISH_PREFIXES = (
    ".ontology/",
    "agents/",
    "artifacts/",
    "research/",
    "research_plan/",
    "scripts/",
    "skills/",
    "specs/",
    "topics/",
)
DEFAULT_REPO_PUBLISH_FILES = {
    "rail.yaml",
    "README.md",
}
DEFAULT_REPO_SKIP_PREFIXES = (
    ".git/",
    ".rail/",
    "__pycache__/",
)
log = logging.getLogger(__name__)


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


def normalize_repo_publish_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def is_repo_publish_path_allowed(path: str, *, allowed_paths: list[str] | None = None) -> bool:
    normalized = normalize_repo_publish_path(path)
    if not normalized or normalized.startswith("../") or "/../" in normalized or normalized == "..":
        return False
    if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in DEFAULT_REPO_SKIP_PREFIXES):
        return False
    if allowed_paths:
        prefixes = [normalize_repo_publish_path(item).rstrip("/") for item in allowed_paths if normalize_repo_publish_path(item)]
        return any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in prefixes)
    if normalized in DEFAULT_REPO_PUBLISH_FILES:
        return True
    return any(normalized.startswith(prefix) for prefix in DEFAULT_REPO_PUBLISH_PREFIXES)


def _read_publishable_content(path: Path) -> str | bytes:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw


def _is_artifact_publish_path(path: str, artifacts_root: str) -> bool:
    normalized = normalize_repo_publish_path(path)
    root = normalize_repo_publish_path(artifacts_root).rstrip("/")
    return bool(root) and (normalized == root or normalized.startswith(f"{root}/"))


async def _enforce_publish_auditors(
    project: dict[str, Any],
    *,
    repo_root: Path,
    files: list[dict[str, str | bytes]],
) -> None:
    from app.services.auditor_service import build_auditor_statuses

    if not files:
        return
    try:
        manifest = load_manifest(repo_root)
    except Exception:
        return

    artifact_paths = [
        str(file.get("path") or "")
        for file in files
        if _is_artifact_publish_path(str(file.get("path") or ""), manifest.paths.artifacts_root)
    ]
    if not artifact_paths:
        return

    auditors = await build_auditor_statuses(project)
    blocked: list[str] = []
    for key in ("ontology", "integrity"):
        status = auditors.get(key) or {}
        if str(status.get("status") or "") != "blocked":
            continue
        blocker = next((str(item) for item in (status.get("blockers") or []) if str(item).strip()), "blocked")
        blocked.append(f"{key}: {blocker}")
    if blocked:
        raise RuntimeError(
            "Artifact publish blocked by auditor state: "
            + "; ".join(blocked)
        )


def collect_publishable_files(
    repo_root: Path,
    changed_paths: list[str],
    *,
    allowed_paths: list[str] | None = None,
) -> tuple[list[dict[str, str | bytes]], list[str]]:
    files: list[dict[str, str | bytes]] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for raw_path in changed_paths:
        normalized = normalize_repo_publish_path(raw_path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if not is_repo_publish_path_allowed(normalized, allowed_paths=allowed_paths):
            skipped.append(normalized)
            continue
        absolute = (repo_root / normalized).resolve()
        try:
            absolute.relative_to(repo_root.resolve())
        except ValueError:
            skipped.append(normalized)
            continue
        if not absolute.exists() or not absolute.is_file():
            skipped.append(normalized)
            continue
        files.append({"path": normalized, "content": _read_publishable_content(absolute)})
    return files, skipped


async def publish_repo_files(
    project: dict[str, Any],
    *,
    repo_root: Path,
    changed_paths: list[str],
    commit_message: str,
    allowed_paths: list[str] | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    repo = infer_github_repo(project.get("github") or project.get("gitRepoUrl"))
    if not repo:
        raise RuntimeError("Project is not linked to a GitHub repository")
    target_branch = branch or project.get("defaultBranch") or "main"
    files, skipped = collect_publishable_files(
        repo_root,
        changed_paths,
        allowed_paths=allowed_paths,
    )
    await _enforce_publish_auditors(project, repo_root=repo_root, files=files)
    if not files:
        head_sha = await github_service.get_branch_head(repo, target_branch)
        return {
            "published": False,
            "strategy": "github_app_commit",
            "commit_sha": head_sha,
            "branch": target_branch,
            "changed": False,
            "files": [],
            "skipped_files": skipped,
        }
    result = await github_service.commit_files(repo, target_branch, files, commit_message)
    return {
        "published": True,
        "strategy": "github_app_commit",
        "commit_sha": result.get("commit_sha"),
        "branch": result.get("branch") or target_branch,
        "changed": result.get("changed", False),
        "files": result.get("files") or [],
        "skipped_files": skipped,
    }


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
    # The current Convex project schema does not accept publish metadata
    # fields yet, so keep this as a no-op instead of emitting noisy failed
    # mutations during otherwise successful publish flows.
    _ = (project_id, publish_result, time.time())


async def record_publish_failure(project_id: str, message: str) -> None:
    _ = (project_id, message)


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
        "lastJobId": previous.get("lastJobId"),
        "activeOntologyDbPath": previous.get("activeOntologyDbPath"),
        "activeOntologyOwlPath": previous.get("activeOntologyOwlPath"),
        "activeOntologyDuckdbPath": previous.get("activeOntologyDuckdbPath"),
        "activeOntologyEmbeddingsPath": previous.get("activeOntologyEmbeddingsPath"),
        "github": previous.get("github"),
        "defaultBranch": previous.get("defaultBranch"),
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
