from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from rail.manifest import load_manifest

from app.services.convex_client import convex
from app.services.device_service import get_device_id


def _safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def get_repo_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def get_manifest_fingerprint(project_root: Path, manifest_path: str = "rail.yaml") -> str:
    manifest_file = (project_root / manifest_path).resolve()
    content = manifest_file.read_bytes()
    return hashlib.sha256(content).hexdigest()


def resolve_pipeline_slug(project_root: Path, manifest_path: str = "rail.yaml") -> str:
    manifest = load_manifest(project_root / manifest_path)
    return manifest.hydration.default_pipeline or "default"


def artifact_files_exist(record: dict[str, Any]) -> bool:
    ontology_path = record.get("ontologyArtifactPath")
    duckdb_path = record.get("duckdbArtifactPath")
    if ontology_path and not Path(ontology_path).exists():
        return False
    if duckdb_path and not Path(duckdb_path).exists():
        return False
    return bool(ontology_path or duckdb_path)


async def register_hydration_artifact(
    *,
    project: dict[str, Any],
    pipeline_slug: str,
    hydration_mode: str,
    ontology_artifact_path: str | None,
    duckdb_artifact_path: str | None,
    status: str = "valid",
) -> str:
    root = Path(project["localRepoPath"]).resolve()
    return await convex.mutation(
        "hydrationArtifacts:register",
        {
            "projectId": project["_id"],
            "deviceId": get_device_id(),
            "commitSha": get_repo_commit(root) or "unknown",
            "manifestFingerprint": get_manifest_fingerprint(root, project.get("manifestPath") or "rail.yaml"),
            "pipelineSlug": pipeline_slug,
            "hydrationMode": hydration_mode,
            "ontologyArtifactPath": ontology_artifact_path,
            "duckdbArtifactPath": duckdb_artifact_path,
            "status": status,
        },
    )


async def get_hydration_status(
    *,
    project: dict[str, Any],
    pipeline_slug: str | None = None,
    hydration_mode: str = "full",
) -> dict[str, Any]:
    root = Path(project["localRepoPath"]).resolve()
    manifest_path = project.get("manifestPath") or "rail.yaml"
    pipeline_slug = pipeline_slug or resolve_pipeline_slug(root, manifest_path)
    current_device_id = get_device_id()
    current_commit = get_repo_commit(root)
    manifest_fingerprint = get_manifest_fingerprint(root, manifest_path)

    artifacts = await convex.query(
        "hydrationArtifacts:listByProject",
        {"projectId": project["_id"], "limit": 100},
    ) or []

    current_device_matches: list[dict[str, Any]] = []
    other_device_matches: list[dict[str, Any]] = []

    for artifact in artifacts:
        if artifact.get("pipelineSlug") != pipeline_slug:
            continue

        artifact["filesExist"] = artifact_files_exist(artifact)
        artifact["isCurrentCommit"] = artifact.get("commitSha") == current_commit
        artifact["isCurrentManifest"] = artifact.get("manifestFingerprint") == manifest_fingerprint
        artifact["isReusable"] = (
            artifact.get("status") == "valid"
            and artifact["filesExist"]
            and artifact["isCurrentCommit"]
            and artifact["isCurrentManifest"]
            and artifact.get("hydrationMode") == hydration_mode
        )
        if artifact.get("deviceId") == current_device_id:
            current_device_matches.append(artifact)
        else:
            other_device_matches.append(artifact)

    reusable_local = next((item for item in current_device_matches if item["isReusable"]), None)
    stale_local = any(item["filesExist"] and not item["isReusable"] for item in current_device_matches)
    hydrated_elsewhere = any(item["filesExist"] for item in other_device_matches)

    if reusable_local:
        state = "hydrated_on_this_device"
    elif stale_local:
        state = "stale_on_this_device"
    elif hydrated_elsewhere:
        state = "hydrated_on_another_device"
    else:
        state = "not_hydrated"

    return {
        "state": state,
        "deviceId": current_device_id,
        "pipelineSlug": pipeline_slug,
        "hydrationMode": hydration_mode,
        "commitSha": current_commit,
        "manifestFingerprint": manifest_fingerprint,
        "reusableArtifact": reusable_local,
        "currentDeviceArtifacts": current_device_matches,
        "otherDeviceArtifacts": other_device_matches,
        "projectRoot": str(root),
        "manifestPath": _safe_relpath(root / manifest_path, root),
    }
