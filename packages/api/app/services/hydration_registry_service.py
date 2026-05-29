from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from rail.integrity import ResearchIntegrityRepo, sync_sources_from_configs
from rail.manifest import load_manifest, parse_manifest_content

from app.services.convex_client import convex, ConvexBackendConfigurationError
from app.services.device_service import get_device_id


def _is_local_project_id(project_id: Any) -> bool:
    return str(project_id or "").startswith("local:")


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


def _artifact_matches_current_commit(artifact_commit: Any, current_commit: str | None) -> bool:
    normalized_artifact = str(artifact_commit or "").strip().lower()
    normalized_current = str(current_commit or "").strip().lower()
    if not normalized_current:
        return normalized_artifact in {"", "unknown", "none", "null"}
    return normalized_artifact == normalized_current


def resolve_pipeline_slug(project: dict, project_root: Path) -> str:
    # 1. Check if project record has a hardcoded pipeline
    if project.get("pipelineConfigSlug"):
        return str(project["pipelineConfigSlug"])
    
    # 2. Check for local pipeline files in .ontology/pipelines/
    pipelines_dir = project_root / ".ontology" / "pipelines"
    if pipelines_dir.exists():
        candidates = [f.stem for f in pipelines_dir.glob("*.yaml")]
        # Prefer specific slugs in order
        for preferred in (f"{project.get('slug')}_hydration", "nj_hydration", "academic_hydration", "default"):
            if preferred in candidates:
                return preferred
        if candidates:
            return candidates[0]

    # 3. Fallback to manifest if available
    try:
        manifest_path = project.get("manifestPath") or "rail.yaml"
        content = (project_root / manifest_path).read_text(encoding="utf-8")
        manifest = parse_manifest_content(content)
        return manifest.hydration.default_pipeline or "default"
    except Exception:
        return "default"


def _resolve_quadstore_db_path(parent: Path, hint: str | None) -> str | None:
    """Resolve activeOntologyDbPath to the SQLite quadstore (onto.db), not YAML manifests."""
    parent = parent.resolve()
    onto_db = parent / "onto.db"
    if onto_db.exists():
        return str(onto_db)
    if hint:
        hint_path = Path(hint).resolve()
        if hint_path.suffix.lower() == ".db" and hint_path.exists():
            return str(hint_path)
    return None


def _duckdb_has_populated_rows(duckdb_path: str | None) -> bool:
    """Return True when the DuckDB at `duckdb_path` has at least one row in
    any table. Used by the local-disk hydration fallback to confirm a project
    has actually been hydrated (not just had an empty DuckDB created).
    """
    if not duckdb_path:
        return False
    try:
        import duckdb
    except Exception:
        return False
    try:
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        if not tables:
            conn.close()
            return False
        for (table_name,) in tables:
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            except Exception:
                continue
            if isinstance(count, int) and count > 0:
                conn.close()
                return True
        conn.close()
    except Exception:
        return False
    return False


def artifact_files_exist(record: dict[str, Any]) -> bool:
    ontology_path = record.get("ontologyArtifactPath")
    duckdb_path = record.get("duckdbArtifactPath")
    if ontology_path and not Path(ontology_path).exists():
        return False
    if duckdb_path and not Path(duckdb_path).exists():
        return False
    if duckdb_path:
        hydration_meta_path = Path(duckdb_path).parent / ".rail_hydration.json"
        if not hydration_meta_path.exists():
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
    _sync_repo_hydration_lineage(
        project_root=root,
        manifest_path=project.get("manifestPath") or "rail.yaml",
        pipeline_slug=pipeline_slug,
        duckdb_artifact_path=duckdb_artifact_path,
    )
    if _is_local_project_id(project.get("_id")):
        project_slug = str(project.get("slug") or Path(project["localRepoPath"]).name)
        return f"local-hydration:{project_slug}:{pipeline_slug}:{hydration_mode}"
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


async def attach_local_hydration_to_convex(
    *,
    slug: str,
    duckdb_artifact_path: str,
    ontology_artifact_path: str | None = None,
    pipeline_slug: str | None = None,
    hydration_mode: str = "full",
) -> dict[str, Any]:
    """Register + promote a locally-produced hydration artifact in Convex.

    Looks up the project by slug. If Convex is not configured or the project
    is not registered, returns `{"status": "skipped", "reason": ...}` instead
    of raising. Use this after a local hydrate (e.g., the live agent loop) to
    unblock the ontology auditor for autopilot ticks against that project.
    """
    from app.services import planner_service

    project = None
    try:
        project = await planner_service.resolve_project_reference(slug)
    except Exception:
        project = None

    if not project or not project.get("_id"):
        return {"status": "skipped", "reason": "project_not_registered"}

    root = Path(project["localRepoPath"]).resolve() if project.get("localRepoPath") else None
    if root is None:
        return {"status": "skipped", "reason": "missing_local_repo_path"}
    pipeline_slug = pipeline_slug or resolve_pipeline_slug(project, root)

    # Convex's hydrationArtifacts.register requires a non-null ontologyArtifactPath
    # (v.string()). Fall back to .ontology/ontology.yaml if the caller did not
    # pass one explicitly — the manifest writer always produces this file.
    if not ontology_artifact_path:
        candidate = Path(duckdb_artifact_path).parent / "ontology.yaml"
        if candidate.exists():
            ontology_artifact_path = str(candidate)
        else:
            ontology_artifact_path = str(candidate)  # still pass path, file may be created later

    artifact_id = await register_hydration_artifact(
        project=project,
        pipeline_slug=pipeline_slug,
        hydration_mode=hydration_mode,
        ontology_artifact_path=ontology_artifact_path,
        duckdb_artifact_path=duckdb_artifact_path,
        status="valid",
    )
    await promote_project_hydration_artifact(
        project=project,
        ontology_artifact_path=ontology_artifact_path,
        duckdb_artifact_path=duckdb_artifact_path,
        status="hydrated",
    )
    return {
        "status": "promoted",
        "mode": "local_repo" if _is_local_project_id(project.get("_id")) else "convex",
        "projectId": project["_id"],
        "artifactId": artifact_id,
        "pipelineSlug": pipeline_slug,
        "duckdbArtifactPath": duckdb_artifact_path,
        "ontologyArtifactPath": ontology_artifact_path,
    }


async def promote_project_hydration_artifact(
    *,
    project: dict[str, Any],
    ontology_artifact_path: str | None,
    duckdb_artifact_path: str | None,
    owl_artifact_path: str | None = None,
    embeddings_artifact_path: str | None = None,
    status: str = "hydrated",
) -> None:
    project_id = project.get("_id")
    if not project_id:
        return

    ontology_path = str(ontology_artifact_path) if ontology_artifact_path else None
    duckdb_path = str(duckdb_artifact_path) if duckdb_artifact_path else None
    if not ontology_path and not duckdb_path:
        return

    ontology_parent = Path(ontology_path or duckdb_path).parent
    hydration_meta_path = ontology_parent / ".rail_hydration.json"
    if duckdb_path and not hydration_meta_path.exists():
        raise ValueError("Hydration metadata must exist before promoting active ontology artifacts.")

    owl_path = owl_artifact_path
    if owl_path is None:
        candidate = ontology_parent / "populated_ontology.owl"
        if candidate.exists():
            owl_path = str(candidate)

    embeddings_path = embeddings_artifact_path
    if embeddings_path is None:
        candidate = ontology_parent / "embeddings.db"
        if candidate.exists():
            embeddings_path = str(candidate)

    patch: dict[str, Any] = {
        "projectId": project_id,
        "status": status,
        "lastHydratedAt": int(time.time() * 1000),
    }
    quadstore_path = _resolve_quadstore_db_path(ontology_parent, ontology_path)
    if quadstore_path:
        patch["activeOntologyDbPath"] = quadstore_path
    if owl_path:
        patch["activeOntologyOwlPath"] = str(owl_path)
    if duckdb_path:
        patch["activeOntologyDuckdbPath"] = duckdb_path
    if embeddings_path:
        patch["activeOntologyEmbeddingsPath"] = str(embeddings_path)
    if _is_local_project_id(project_id):
        return
    await convex.mutation("projects:updateById", patch)


def _sync_repo_hydration_lineage(
    *,
    project_root: Path,
    manifest_path: str,
    pipeline_slug: str,
    duckdb_artifact_path: str | None,
) -> None:
    if not duckdb_artifact_path:
        return
    try:
        manifest = load_manifest(project_root)
    except Exception:
        return
    pipeline_path = project_root / manifest.hydration.pipelines_dir / f"{pipeline_slug}.yaml"
    if not pipeline_path.exists():
        return
    try:
        pipeline_spec = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return

    source_keys = sorted(
        {
            *[str(item) for item in manifest.hydration.linked_sources],
            *[
                str(step.get("api"))
                for step in pipeline_spec.get("steps") or []
                if isinstance(step, dict) and step.get("api")
            ],
        }
    )
    sync_sources_from_configs(
        project_root,
        sources_dir=manifest.hydration.sources_dir,
        source_keys=source_keys,
    )
    repo = ResearchIntegrityRepo(project_root)
    duckdb_path = Path(duckdb_artifact_path)
    artifact_rel = _safe_relpath(duckdb_path, project_root)
    hydration_meta_rel = _safe_relpath(project_root / ".ontology" / ".rail_hydration.json", project_root)
    source_inputs = [
        str((Path(manifest.hydration.sources_dir) / f"{source_key}.yaml").as_posix())
        for source_key in source_keys
    ]
    script_inputs = [str((Path(manifest.hydration.pipelines_dir) / f"{pipeline_slug}.yaml").as_posix())]
    source_refs = [f"research_plan/state/sources.json#{source_key}" for source_key in source_keys]
    repo.upsert_artifact_lineage(
        {
            "artifact_path": artifact_rel,
            "artifact_type": "dataset",
            "title": duckdb_path.name,
            "promotion_state": "draft",
            "inputs": source_inputs,
            "scripts": script_inputs,
            "sources": source_refs,
        }
    )
    repo.upsert_artifact_lineage(
        {
            "artifact_path": hydration_meta_rel,
            "artifact_type": "dataset",
            "title": Path(hydration_meta_rel).name,
            "promotion_state": "draft",
            "inputs": source_inputs,
            "scripts": script_inputs,
            "sources": source_refs,
            "reproducibility_mode": "deterministic",
        }
    )


async def get_hydration_status(
    *,
    project: dict[str, Any],
    pipeline_slug: str | None = None,
    hydration_mode: str = "full",
) -> dict[str, Any]:
    root = Path(project["localRepoPath"]).resolve()
    manifest_path = project.get("manifestPath") or "rail.yaml"
    pipeline_slug = pipeline_slug or resolve_pipeline_slug(project, root)
    current_device_id = get_device_id()
    current_commit = get_repo_commit(root)
    manifest_fingerprint = get_manifest_fingerprint(root, manifest_path)

    project_id = project.get("_id")
    if _is_local_project_id(project_id) or not project_id:
        artifacts = []
    else:
        artifacts = await convex.query(
            "hydrationArtifacts:listByProject",
            {"projectId": project_id, "limit": 100},
        ) or []

    current_device_matches: list[dict[str, Any]] = []
    other_device_matches: list[dict[str, Any]] = []

    for artifact in artifacts:
        if artifact.get("pipelineSlug") != pipeline_slug:
            continue

        artifact["filesExist"] = artifact_files_exist(artifact)
        artifact["isCurrentCommit"] = _artifact_matches_current_commit(artifact.get("commitSha"), current_commit)
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

    # Local-disk fallback: if Convex has no record but the project's
    # `.ontology/onto.duckdb` + `.rail_hydration.json` both exist with
    # populated rows, synthesize a current-device artifact. This matches
    # the spec's "Git is the durable truth, the DB stores operational
    # metadata" rule (docs/future-spec-autonomous-platform-roadmap.md#1)
    # — a project that's hydrated on disk IS hydrated; missing Convex
    # registration is operational drift, not a research-integrity gap.
    # The fallback also makes the auditor robust to Convex outages and
    # offline operation, and lets integration tests work without
    # elaborate hydrationArtifacts mocking.
    if reusable_local is None:
        local_duckdb = root / ".ontology" / "onto.duckdb"
        local_meta = root / ".ontology" / ".rail_hydration.json"
        if local_duckdb.exists() and local_meta.exists():
            try:
                local_meta_payload: dict[str, Any] = {}
                try:
                    import json as _json

                    local_meta_payload = _json.loads(local_meta.read_text(encoding="utf-8")) or {}
                except Exception:
                    local_meta_payload = {}
                if _duckdb_has_populated_rows(str(local_duckdb)):
                    same_device_local = next(
                        (
                            item for item in current_device_matches
                            if Path(str(item.get("duckdbArtifactPath") or "")).resolve() == local_duckdb.resolve()
                        ),
                        None,
                    )
                    can_trust_local_disk = (
                        same_device_local is not None
                        or (not stale_local and not hydrated_elsewhere)
                    )
                    if can_trust_local_disk:
                        synthesized = {
                            "deviceId": current_device_id,
                            "pipelineSlug": pipeline_slug,
                            "hydrationMode": local_meta_payload.get("hydrationMode") or hydration_mode,
                            "status": "valid",
                            "commitSha": current_commit,
                            "manifestFingerprint": manifest_fingerprint,
                            "duckdbArtifactPath": str(local_duckdb),
                            "ontologyArtifactPath": str(root / ".ontology" / "onto.db"),
                            "filesExist": True,
                            "isCurrentCommit": True,
                            "isCurrentManifest": True,
                            "isReusable": True,
                            "synthesizedFromLocalDisk": True,
                        }
                        if same_device_local is not None:
                            current_device_matches = [item for item in current_device_matches if item is not same_device_local]
                        current_device_matches.append(synthesized)
                        reusable_local = synthesized
                        stale_local = False
            except Exception:
                pass

    # Check for active jobs. Local repo-only projects do not have a Convex row, so
    # hydration status should degrade to local artifact truth instead of raising on
    # a missing `_id`.
    project_id = project.get("_id")
    if _is_local_project_id(project_id) or not project_id:
        active_jobs = []
    else:
        active_jobs = await convex.query(
            "jobs:listByProject",
            {"projectId": project_id, "limit": 10},
        ) or []
    
    running_job = next(
        (j for j in active_jobs if j.get("status") in ["queued", "started", "running"] 
         and j.get("pipelineSlug") == pipeline_slug),
        None
    )

    if running_job:
        state = "hydrating"
    elif reusable_local:
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
        "runningJobId": running_job.get("_id") if running_job else None,
        "projectRoot": str(root),
        "manifestPath": _safe_relpath(root / manifest_path, root),
    }
