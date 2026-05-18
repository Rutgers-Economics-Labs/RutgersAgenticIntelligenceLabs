from __future__ import annotations

from pathlib import Path
from typing import Any

from app.runners import session_lifecycle
from app.services import hydration_registry_service, planner_service, running_agent_service
from app.services.audit_service import audit_gate_status, repair_stale_session_audits
from app.services.integrity_service import load_integrity_indexes
from rail.manifest import load_manifest


async def repair_stale_active_sessions(project: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    if not project_root or not project_root.exists():
        return {"repairedSessionIds": []}
    active_sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    repaired: list[str] = []
    for session in active_sessions:
        root = session_lifecycle._resolve_session_root_path(session, project_root=project_root)
        if root is None or not root.exists():
            continue
        state = session_lifecycle.session_files.read_state(root)
        status = str(state.get("status") or "")
        if status not in session_lifecycle.TERMINAL_STATUSES:
            continue
        await running_agent_service.finalize_running_agent(
            str(session["_id"]),
            status=status,
        )
        repaired.append(str(session["_id"]))
    return {"repairedSessionIds": repaired}


def _preferred_hydration_artifact_path(hydration: dict[str, Any]) -> str | None:
    reusable = hydration.get("reusableArtifact") or {}
    if reusable.get("duckdbArtifactPath"):
        return str(reusable["duckdbArtifactPath"])
    current = hydration.get("currentDeviceArtifacts") or []
    preferred = next(
        (
            item
            for item in current
            if item.get("duckdbArtifactPath")
            and item.get("filesExist")
            and item.get("isCurrentCommit")
            and item.get("isCurrentManifest")
        ),
        None,
    )
    if preferred and preferred.get("duckdbArtifactPath"):
        return str(preferred["duckdbArtifactPath"])
    fallback = next((item for item in current if item.get("duckdbArtifactPath") and item.get("filesExist")), None)
    if fallback and fallback.get("duckdbArtifactPath"):
        return str(fallback["duckdbArtifactPath"])
    return None


async def repair_active_ontology_registry_drift(project: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    if project_root is None or not project_root.exists():
        return {"repaired": False}
    try:
        hydration = await hydration_registry_service.get_hydration_status(project=project)
    except Exception:
        return {"repaired": False}

    expected_duckdb_path = _preferred_hydration_artifact_path(hydration)
    active_duckdb_path = str(project.get("activeOntologyDuckdbPath") or "").strip() or None
    active_exists = bool(active_duckdb_path and Path(active_duckdb_path).exists())
    if not expected_duckdb_path:
        return {"repaired": False}
    if active_duckdb_path == expected_duckdb_path and active_exists:
        return {"repaired": False}

    reusable = hydration.get("reusableArtifact") or {}
    await hydration_registry_service.promote_project_hydration_artifact(
        project=project,
        ontology_artifact_path=reusable.get("ontologyArtifactPath"),
        duckdb_artifact_path=expected_duckdb_path,
        owl_artifact_path=reusable.get("owlArtifactPath"),
        embeddings_artifact_path=reusable.get("embeddingsArtifactPath"),
        status=str(project.get("status") or "hydrated"),
    )
    return {
        "repaired": True,
        "previousDuckdbPath": active_duckdb_path,
        "nextDuckdbPath": expected_duckdb_path,
    }


async def project_reality_snapshot(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None = None,
    active_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = planner_service.project_root_from_record(project)
    if root is None or not root.exists():
        return {
            "duplicateTaskFiles": [],
            "taskSessionMismatchTaskIds": [],
            "staleRuntimeSessionIds": [],
            "staleAuditSessionIds": [],
            "terminalSessionIds": [],
            "activeRuntimeSessionIds": [str(item.get("_id")) for item in (active_sessions or []) if item.get("_id")],
        }

    runtime_tasks = tasks if tasks is not None else await planner_service.list_tasks("main", project=project)
    runtime_active_sessions = (
        active_sessions
        if active_sessions is not None
        else await running_agent_service.list_project_running_agents(project["_id"], active_only=True, limit=50)
    )

    task_by_id = {str(task.get("_id") or ""): task for task in runtime_tasks}
    mismatch_task_ids: list[str] = []
    for session_root in planner_service._session_task_roots(root):
        state = session_lifecycle.session_files.read_state(session_root)
        task_id = str(state.get("task_id") or "").strip()
        if not task_id or task_id not in task_by_id:
            continue
        patch = planner_service._terminal_task_patch_from_session_state(
            state,
            str(state.get("session_id") or session_root.name),
        )
        if patch is None:
            continue
        task = task_by_id[task_id]
        if (
            str(task.get("status") or "") != patch["status"]
            or task.get("blockerCategory") != patch["blockerCategory"]
            or str(task.get("latestRunSummary") or "") != patch["latestRunSummary"]
            or (task.get("approvalState") is not None and patch["status"] in {"done", "cancelled", "blocked"})
        ):
            mismatch_task_ids.append(task_id)

    stale_runtime_session_ids: list[str] = []
    for session in runtime_active_sessions:
        session_root = session_lifecycle._resolve_session_root_path(session, project_root=root)
        if session_root is None or not session_root.exists():
            continue
        state = session_lifecycle.session_files.read_state(session_root)
        status = str(state.get("status") or "")
        if status in session_lifecycle.TERMINAL_STATUSES:
            stale_runtime_session_ids.append(str(session.get("_id") or ""))

    duplicate_task_files: list[str] = []
    task_dir = root / "research_plan" / "tasks"
    if task_dir.is_dir():
        seen: dict[tuple[str, str], Path] = {}
        for path in sorted(task_dir.glob("*.md")):
            task = planner_service._task_to_runtime(path)
            key = planner_service._task_dedupe_key(task)
            if key == ("", ""):
                continue
            if key in seen:
                duplicate_task_files.append(str(path.relative_to(root)))
            else:
                seen[key] = path

    gate = audit_gate_status(root)
    stale_audit_session_ids = [str(item) for item in (gate.get("staleSessionIds") or []) if item]
    terminal_session_ids = [str(item) for item in (gate.get("terminalSessionIds") or []) if item]
    ontology_artifact_drift: dict[str, Any] = {
        "hasDrift": False,
        "activeDuckdbPath": str(project.get("activeOntologyDuckdbPath") or "") or None,
        "expectedDuckdbPath": None,
        "reason": None,
    }
    try:
        hydration = await hydration_registry_service.get_hydration_status(project=project)
        expected_duckdb_path = _preferred_hydration_artifact_path(hydration)
        active_duckdb_path = ontology_artifact_drift["activeDuckdbPath"]
        active_exists = bool(active_duckdb_path and Path(active_duckdb_path).exists())
        ontology_artifact_drift["expectedDuckdbPath"] = expected_duckdb_path
        if expected_duckdb_path:
            if not active_duckdb_path:
                ontology_artifact_drift = {
                    **ontology_artifact_drift,
                    "hasDrift": True,
                    "reason": "project_missing_active_ontology_pointer",
                }
            elif not active_exists:
                ontology_artifact_drift = {
                    **ontology_artifact_drift,
                    "hasDrift": True,
                    "reason": "active_ontology_path_missing_on_disk",
                }
            elif active_duckdb_path != expected_duckdb_path:
                ontology_artifact_drift = {
                    **ontology_artifact_drift,
                    "hasDrift": True,
                    "reason": "active_ontology_pointer_out_of_date",
                }
    except Exception:
        pass
    artifact_registry_drift: dict[str, Any] = {
        "hasDrift": False,
        "untrackedArtifactPaths": [],
        "missingArtifactPaths": [],
    }
    try:
        manifest = load_manifest(root)
        indexes = load_integrity_indexes(root)
        artifacts_root = root / manifest.paths.artifacts_root
        disk_artifacts = sorted(
            str(path.relative_to(root)).replace("\\", "/")
            for path in artifacts_root.rglob("*")
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts)
        ) if artifacts_root.exists() else []
        tracked_artifacts = sorted(
            str(item.artifact_path)
            for item in indexes.artifact_lineage
            if item.artifact_type != "dataset"
            and (
                str(item.artifact_path) == manifest.paths.artifacts_root
                or str(item.artifact_path).startswith(f"{manifest.paths.artifacts_root}/")
            )
        )
        tracked_set = set(tracked_artifacts)
        disk_set = set(disk_artifacts)
        untracked = sorted(path for path in disk_artifacts if path not in tracked_set)
        missing = sorted(path for path in tracked_artifacts if path not in disk_set)
        artifact_registry_drift = {
            "hasDrift": bool(untracked or missing),
            "untrackedArtifactPaths": untracked,
            "missingArtifactPaths": missing,
        }
    except Exception:
        pass

    return {
        "duplicateTaskFiles": duplicate_task_files,
        "taskSessionMismatchTaskIds": mismatch_task_ids,
        "staleRuntimeSessionIds": stale_runtime_session_ids,
        "staleAuditSessionIds": stale_audit_session_ids,
        "terminalSessionIds": terminal_session_ids,
        "activeRuntimeSessionIds": [str(item.get("_id")) for item in runtime_active_sessions if item.get("_id")],
        "ontologyArtifactDrift": ontology_artifact_drift,
        "artifactRegistryDrift": artifact_registry_drift,
    }


async def project_reality_status(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None = None,
    active_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = await project_reality_snapshot(project, tasks=tasks, active_sessions=active_sessions)
    duplicate_count = len(snapshot["duplicateTaskFiles"])
    mismatch_count = len(snapshot["taskSessionMismatchTaskIds"])
    stale_runtime_count = len(snapshot["staleRuntimeSessionIds"])
    stale_audit_count = len(snapshot["staleAuditSessionIds"])
    terminal_count = len(snapshot["terminalSessionIds"])
    active_runtime_count = len(snapshot["activeRuntimeSessionIds"])
    ontology_artifact_drift_count = 1 if snapshot.get("ontologyArtifactDrift", {}).get("hasDrift") else 0
    artifact_registry_drift = snapshot.get("artifactRegistryDrift") or {}
    artifact_registry_drift_count = len(artifact_registry_drift.get("untrackedArtifactPaths") or []) + len(artifact_registry_drift.get("missingArtifactPaths") or [])

    return {
        "hasDrift": bool(
            duplicate_count
            or mismatch_count
            or stale_runtime_count
            or stale_audit_count
            or ontology_artifact_drift_count
            or artifact_registry_drift_count
        ),
        "duplicateTaskFileCount": duplicate_count,
        "taskSessionMismatchCount": mismatch_count,
        "staleRuntimeSessionCount": stale_runtime_count,
        "staleAuditSessionCount": stale_audit_count,
        "terminalSessionCount": terminal_count,
        "activeRuntimeSessionCount": active_runtime_count,
        "ontologyArtifactDriftCount": ontology_artifact_drift_count,
        "artifactRegistryDriftCount": artifact_registry_drift_count,
        "details": snapshot,
    }


async def reconcile_project_reality(project: dict[str, Any]) -> dict[str, Any]:
    root = planner_service.project_root_from_record(project)
    removed_task_files: list[str] = []
    updated_task_ids: list[str] = []
    updated_approval_ids: list[str] = []
    repaired_session_ids: list[str] = []
    repaired_audit_session_ids: list[str] = []
    repaired_ontology_artifact: dict[str, Any] | None = None

    removed_task_files = list((await planner_service.reconcile_task_files(project)).get("removed") or [])
    updated_task_ids = list((await planner_service.reconcile_task_session_states(project)).get("updated") or [])
    metadata_repair = await planner_service.reconcile_planner_metadata(project)
    metadata_task_updates = [str(item) for item in (metadata_repair.get("updatedTaskIds") or []) if item]
    updated_task_ids = list(dict.fromkeys(updated_task_ids + metadata_task_updates))
    updated_approval_ids = [str(item) for item in (metadata_repair.get("updatedApprovalIds") or []) if item]
    repaired_session_ids = list((await repair_stale_active_sessions(project)).get("repairedSessionIds") or [])
    if root is not None and root.exists():
        repaired_audit_session_ids = list((await repair_stale_session_audits(project, root)).get("repairedSessionIds") or [])
    ontology_repair = await repair_active_ontology_registry_drift(project)
    if ontology_repair.get("repaired"):
        repaired_ontology_artifact = ontology_repair

    return {
        "removedTaskFiles": removed_task_files,
        "updatedTaskIds": updated_task_ids,
        "updatedApprovalIds": updated_approval_ids,
        "repairedSessionIds": repaired_session_ids,
        "repairedAuditSessionIds": repaired_audit_session_ids,
        "repairedOntologyArtifact": repaired_ontology_artifact,
        "hasChanges": bool(
            removed_task_files
            or updated_task_ids
            or updated_approval_ids
            or repaired_session_ids
            or repaired_audit_session_ids
            or repaired_ontology_artifact
        ),
    }
