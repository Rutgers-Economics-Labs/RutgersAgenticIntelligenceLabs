#!/usr/bin/env python3
"""
Sync GitHub repo URLs for local RAIL projects into Convex.

The script:
- loads the Convex deployment URL and deploy key from `.env`
- inspects known local project directories and their git remotes
- updates matching Convex project rows with `gitRepoUrl`, `github`, `defaultBranch`
- creates missing Convex project rows for git-backed local projects that have a `rail.yaml`

Run from the repo root:
  python scripts/sync_project_github_links.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
ENV_PATH = ROOT / ".env"


def _read_env_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if not ENV_PATH.exists():
        return ""
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return ""


CONVEX_URL = _read_env_value("CONVEX_URL").rstrip("/")
CONVEX_DEPLOY_KEY = _read_env_value("CONVEX_DEPLOY_KEY")

if not CONVEX_URL or not CONVEX_DEPLOY_KEY:
    raise SystemExit("Missing CONVEX_URL or CONVEX_DEPLOY_KEY in environment or .env")


def query(path: str, args: dict) -> object:
    response = httpx.post(
        f"{CONVEX_URL}/api/query",
        json={"path": path, "args": args},
        headers={"Authorization": f"Convex {CONVEX_DEPLOY_KEY}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error":
        raise RuntimeError(f"Convex query failed for {path}: {payload.get('errorMessage', payload)}")
    return payload.get("value", payload)


def mutation(path: str, args: dict) -> object:
    response = httpx.post(
        f"{CONVEX_URL}/api/mutation",
        json={"path": path, "args": args},
        headers={"Authorization": f"Convex {CONVEX_DEPLOY_KEY}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error":
        raise RuntimeError(f"Convex mutation failed for {path}: {payload.get('errorMessage', payload)}")
    return payload.get("value", payload)


def normalize_git_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized[len("git@github.com:") :]
    if normalized.startswith("ssh://git@github.com/"):
        normalized = "https://github.com/" + normalized[len("ssh://git@github.com/") :]
    parts = urlsplit(normalized)
    if parts.netloc.endswith("github.com"):
        normalized = urlunsplit((parts.scheme or "https", "github.com", parts.path, "", ""))
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.rstrip("/")


def github_slug_from_url(url: str) -> str:
    normalized = normalize_git_url(url)
    prefix = "https://github.com/"
    if normalized.startswith(prefix):
        return normalized[len(prefix) :]
    return ""


def git_remote_url(project_root: Path) -> str:
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return ""
    result = subprocess.run(
        ["git", "-C", str(project_root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return normalize_git_url(result.stdout.strip())


def manifest_metadata(project_root: Path) -> dict:
    manifest_path = project_root / "rail.yaml"
    if not manifest_path.exists():
        return {}
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    project = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    hydration = raw.get("hydration") if isinstance(raw.get("hydration"), dict) else {}
    return {
        "name": project.get("name") or project_root.name,
        "slug": project.get("slug") or project_root.name,
        "description": project.get("description") or "",
        "defaultBranch": project.get("default_branch") or project.get("defaultBranch") or "main",
        "pipelineConfigSlug": hydration.get("default_pipeline") or hydration.get("pipeline") or None,
    }


def discover_local_projects() -> list[dict]:
    candidates = [
        *sorted((WORKSPACE_ROOT).glob("RAIL-*")),
        *sorted((ROOT / "generated_projects").glob("*")),
    ]
    projects: list[dict] = []
    for path in candidates:
        if not path.is_dir():
            continue
        manifest = manifest_metadata(path)
        if not manifest:
            continue
        remote_url = git_remote_url(path)
        if not remote_url:
            continue
        projects.append(
            {
                "root": path,
                "name": manifest["name"],
                "slug": manifest["slug"],
                "description": manifest["description"],
                "defaultBranch": manifest["defaultBranch"],
                "pipelineConfigSlug": manifest["pipelineConfigSlug"],
                "gitRepoUrl": remote_url,
                "github": github_slug_from_url(remote_url),
            }
        )
    return projects


def best_project_row(rows: list[dict]) -> dict:
    def score(row: dict) -> tuple[int, int, int, float]:
        return (
            1 if row.get("status") == "hydrated" else 0,
            1 if row.get("gitRepoUrl") else 0,
            1 if row.get("github") else 0,
            float(row.get("updatedAt") or row.get("_creationTime") or 0),
        )

    return max(rows, key=score)


def find_existing_project(local: dict, db_projects: list[dict]) -> dict | None:
    slug = local["slug"]
    git_repo_url = local["gitRepoUrl"]
    local_repo_path = str(local["root"])
    github = local["github"]

    matches = [
        project
        for project in db_projects
        if project.get("slug") == slug
        or project.get("gitRepoUrl") == git_repo_url
        or project.get("localRepoPath") == local_repo_path
        or (github and project.get("github") == github)
    ]
    if not matches:
        return None
    return best_project_row(matches)


def main() -> None:
    db_projects = query("projects:list", {}) or []
    by_slug: dict[str, list[dict]] = {}
    for project in db_projects:
        by_slug.setdefault(project["slug"], []).append(project)

    local_projects = discover_local_projects()
    created: list[str] = []
    updated: list[str] = []
    duplicates: list[str] = []

    for slug, rows in by_slug.items():
        if len(rows) > 1:
            duplicates.append(slug)

    for local in local_projects:
        existing = find_existing_project(local, db_projects)
        payload = {
            "name": local["name"],
            "description": local["description"],
            "gitRepoUrl": local["gitRepoUrl"],
            "github": local["github"],
            "localRepoPath": str(local["root"]),
            "manifestPath": "rail.yaml",
            "defaultBranch": local["defaultBranch"],
        }
        if local["pipelineConfigSlug"]:
            payload["pipelineConfigSlug"] = local["pipelineConfigSlug"]

        if existing:
            needs_update = any((existing.get(key) or "") != value for key, value in payload.items())
            if needs_update:
                mutation("projects:updateById", {"projectId": existing["_id"], **payload})
                updated.append(existing["slug"])
        else:
            project_id = mutation(
                "projects:create",
                {
                    "slug": local["slug"],
                    "name": local["name"],
                    "description": local["description"],
                    "approach": "ontology-first",
                    "gitRepoUrl": local["gitRepoUrl"],
                    "localRepoPath": str(local["root"]),
                    "manifestPath": "rail.yaml",
                },
            )
            mutation("projects:updateById", {"projectId": project_id, **payload})
            created.append(local["slug"])

    summary = {
        "updated": sorted(updated),
        "created": sorted(created),
        "duplicate_slugs_detected": sorted(duplicates),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
