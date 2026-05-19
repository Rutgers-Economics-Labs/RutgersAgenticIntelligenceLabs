from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.hydration_registry_service import get_hydration_status
from app.services.integrity_service import evaluate_integrity_gate, load_integrity_indexes
from app.services.question_expansion_service import missing_expansion_task_blockers, parse_follow_up_questions
from app.services.reconciliation_service import project_reality_status
from rail.manifest import load_manifest

ONTOLOGY_READY_STATES = {"hydrated_on_this_device", "hydrated_on_another_device", "hydrating"}

_HYDRATION_STATE_CLASSIFICATIONS: dict[str, str] = {
    "hydrated_on_this_device": "ready",
    "hydrating": "in_progress",
    "hydrated_on_another_device": "ready",
    "stale_on_this_device": "stale",
    "not_hydrated": "not_started",
}


def classify_hydration_state(state: str) -> str:
    """Map a raw hydration state string to a lifecycle phase classification."""
    return _HYDRATION_STATE_CLASSIFICATIONS.get(str(state or "").strip(), "unavailable")


def _manifest_project_mode(project: dict[str, Any]) -> str | None:
    """Read project.mode from rail.yaml when localRepoPath is available."""
    root = project.get("localRepoPath")
    if not root:
        return None
    rail_yaml = Path(str(root)).resolve() / "rail.yaml"
    if not rail_yaml.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(rail_yaml.read_text(encoding="utf-8")) or {}
        return str((data.get("project") or {}).get("mode") or "").strip() or None
    except Exception:
        return None


def _is_ontology_project(project: dict[str, Any]) -> bool:
    """True when ontology hydration health gates apply to this project."""
    mode = _manifest_project_mode(project)
    if mode == "research_first":
        return False
    if mode == "ontology_first":
        return True
    approach = str(project.get("approach") or "").strip().lower()
    if approach in {"research-first", "research_first"}:
        return False
    if approach == "ontology-first":
        return True
    root = project.get("localRepoPath")
    if not root:
        return False
    ontology_root = Path(str(root)).resolve() / ".ontology"
    if not ontology_root.exists():
        return False
    # A bare .ontology scaffold without DuckDB is not an ontology-first archetype.
    return (ontology_root / "onto.duckdb").is_file()


def _duckdb_has_populated_rows(duckdb_path: str | None) -> bool:
    if not duckdb_path:
        return False
    try:
        import duckdb  # type: ignore
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
                count = conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]
            except Exception:
                continue
            if isinstance(count, int) and count > 0:
                conn.close()
                return True
        conn.close()
    except Exception:
        return False
    return False


def _hydration_duckdb_path(hydration: dict[str, Any]) -> str | None:
    reusable = hydration.get("reusableArtifact") or {}
    if reusable.get("duckdbArtifactPath"):
        return str(reusable["duckdbArtifactPath"])
    current_artifacts = hydration.get("currentDeviceArtifacts") or []
    for artifact in current_artifacts:
        if artifact.get("duckdbArtifactPath"):
            return str(artifact["duckdbArtifactPath"])
    return None


def _missing_follow_up_task_blockers(tasks: list[dict[str, Any]], project_root: Path) -> list[str]:
    task_titles = {str(task.get("title") or "") for task in tasks}
    questions = parse_follow_up_questions(project_root)
    return missing_expansion_task_blockers(questions, task_titles)


def _list_final_artifact_files(project_root: Path, artifacts_root: str) -> list[str]:
    root = (project_root / artifacts_root).resolve()
    if not root.exists():
        return []
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(project_root).parts):
            continue
        files.append(str(path.relative_to(project_root)).replace("\\", "/"))
    return sorted(files)


async def audit_ontology_health(
    project: dict[str, Any],
    *,
    ontology_artifact_drift: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured ontology health result for a project.

    Returns a dict with:
      healthy (bool), state (str), stateClassification (str),
      duckdbPath (str|None), hasPopulatedRows (bool),
      driftReason (str|None), blockers (list[str])
    """
    if not _is_ontology_project(project):
        return {
            "healthy": True,
            "state": "not_applicable",
            "stateClassification": "not_applicable",
            "duckdbPath": None,
            "hasPopulatedRows": False,
            "driftReason": None,
            "blockers": [],
        }

    blockers: list[str] = []
    state: str = "unknown"
    duckdb_path: str | None = None
    has_populated_rows = False

    try:
        hydration = await get_hydration_status(project=project)
        state = str(hydration.get("state") or "unknown")
        duckdb_path = _hydration_duckdb_path(hydration) or str(project.get("activeOntologyDuckdbPath") or "") or None
        if not duckdb_path:
            duckdb_path = None
        has_populated_rows = _duckdb_has_populated_rows(duckdb_path)

        if state not in ONTOLOGY_READY_STATES:
            blockers.append(f"Ontology hydration state is `{state}`.")
        elif not has_populated_rows:
            blockers.append("Ontology artifact exists but does not contain populated rows.")
    except Exception as exc:
        state = "error"
        blockers.append(f"Could not read hydration status: {exc}")

    drift_reason: str | None = None
    if ontology_artifact_drift and ontology_artifact_drift.get("hasDrift"):
        drift_reason = str(ontology_artifact_drift.get("reason") or "unknown_reason")
        blockers.append(f"Active ontology artifact pointer drift detected: {drift_reason}.")

    return {
        "healthy": len(blockers) == 0,
        "state": state,
        "stateClassification": classify_hydration_state(state),
        "duckdbPath": duckdb_path,
        "hasPopulatedRows": has_populated_rows,
        "driftReason": drift_reason,
        "blockers": blockers,
    }


async def build_auditor_statuses(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None = None,
    active_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    reality = await project_reality_status(project, tasks=tasks, active_sessions=active_sessions)

    session_status = {
        "status": "blocked"
        if (
            reality["staleRuntimeSessionCount"]
            or reality.get("zombieSessionCount")
            or reality.get("runningAgentStatusDriftCount")
            or reality.get("runningAgentRoleDriftCount")
            or reality.get("runningAgentRunnerDriftCount")
        )
        else "ready",
        "blockers": [
            *(
                [f"{reality['staleRuntimeSessionCount']} stale runtime session(s) still marked active."]
                if reality["staleRuntimeSessionCount"]
                else []
            ),
            *(
                [f"{reality['zombieSessionCount']} zombie session(s): active in DB but runner process is dead."]
                if reality.get("zombieSessionCount")
                else []
            ),
            *(
                [f"{reality['runningAgentStatusDriftCount']} running-agent session status alias row(s) detected."]
                if reality.get("runningAgentStatusDriftCount")
                else []
            ),
            *(
                [f"{reality['runningAgentRoleDriftCount']} running-agent session role alias row(s) detected."]
                if reality.get("runningAgentRoleDriftCount")
                else []
            ),
            *(
                [f"{reality['runningAgentRunnerDriftCount']} running-agent session runner alias row(s) detected."]
                if reality.get("runningAgentRunnerDriftCount")
                else []
            ),
        ],
    }
    _PLANNER_SATURATION_THRESHOLD = 10
    open_tasks = [t for t in (tasks or []) if t.get("status") not in {"done", "cancelled"}]
    task_saturation_count = len(open_tasks) if len(open_tasks) > _PLANNER_SATURATION_THRESHOLD else 0
    planner_status = {
        "status": "blocked"
        if reality["duplicateTaskFileCount"] or reality["taskSessionMismatchCount"] or reality["staleAuditSessionCount"] or reality.get("secretPolicyRoleDriftCount") or reality.get("roleConfigAliasDriftCount")
        else "ready",
        "blockers": [
            *([f"{reality['duplicateTaskFileCount']} duplicate task file(s) detected."] if reality["duplicateTaskFileCount"] else []),
            *([f"{reality['taskSessionMismatchCount']} task/session state mismatch(es) detected."] if reality["taskSessionMismatchCount"] else []),
            *([f"{reality['staleAuditSessionCount']} terminal session audit(s) are stale or missing."] if reality["staleAuditSessionCount"] else []),
            *(
                [f"{reality['secretPolicyRoleDriftCount']} agent secret policy role alias row(s) detected."]
                if reality.get("secretPolicyRoleDriftCount")
                else []
            ),
            *(
                [f"{reality['roleConfigAliasDriftCount']} role config alias declaration(s) detected."]
                if reality.get("roleConfigAliasDriftCount")
                else []
            ),
        ],
        "taskSaturationCount": task_saturation_count,
    }

    ontology_reality = (reality.get("details") or {}).get("ontologyArtifactDrift") or {}
    health = await audit_ontology_health(project, ontology_artifact_drift=ontology_reality or None)
    ontology_status: dict[str, Any] = {
        "status": "ready" if health["healthy"] else "blocked",
        "blockers": health["blockers"],
        "state": health["state"] if health["state"] not in {"not_applicable", "unknown"} else None,
        "stateClassification": health["stateClassification"],
        "duckdbPath": health["duckdbPath"],
    }

    integrity_status: dict[str, Any] = {"status": "ready", "blockers": []}
    critic_status: dict[str, Any] = {"status": "ready", "blockers": []}
    closeout_status: dict[str, Any] = {"status": "ready", "blockers": []}
    if root and root.exists() and (root / "rail.yaml").is_file():
        manifest = load_manifest(root)
        artifact_gate = evaluate_integrity_gate(root, manifest, action="artifact_generation")
        if artifact_gate.get("blocked"):
            integrity_status = {
                "status": "blocked",
                "blockers": [str(item) for item in (artifact_gate.get("reasons") or [])],
            }
        artifact_registry_drift = (reality.get("details") or {}).get("artifactRegistryDrift") or {}
        if artifact_registry_drift.get("hasDrift"):
            blockers = list(integrity_status.get("blockers") or [])
            untracked = list(artifact_registry_drift.get("untrackedArtifactPaths") or [])[:3]
            missing = list(artifact_registry_drift.get("missingArtifactPaths") or [])[:3]
            if untracked:
                blockers.append(f"Artifacts exist on disk without lineage records: {', '.join(str(item) for item in untracked)}.")
            if missing:
                blockers.append(f"Artifact lineage points to missing files: {', '.join(str(item) for item in missing)}.")
            integrity_status = {
                "status": "blocked",
                "blockers": blockers,
            }
        indexes = load_integrity_indexes(root)
        critic_blockers: list[str] = []
        weakened_or_rejected = [item for item in indexes.hypotheses if item.status in {"weakened", "rejected"}]
        if weakened_or_rejected:
            sample = ", ".join(item.hypothesis_id for item in weakened_or_rejected[:5])
            critic_blockers.append(f"{len(weakened_or_rejected)} hypothesis(es) flagged by critic review: {sample}.")
        if critic_blockers:
            critic_status = {"status": "blocked", "blockers": critic_blockers}
        unfinished = [task for task in (tasks or []) if task.get("status") not in {"done", "cancelled"}]
        closeout_blockers: list[str] = []
        if (active_sessions or []):
            closeout_blockers.append(f"{len(active_sessions or [])} active session(s) still exist.")
        if unfinished:
            closeout_blockers.append(f"{len(unfinished)} non-terminal task(s) remain.")
        if reality["staleAuditSessionCount"]:
            closeout_blockers.append(
                f"{reality['staleAuditSessionCount']} terminal session audit(s) are stale or missing."
            )
        if ontology_status.get("status") == "blocked":
            closeout_blockers.extend(list(ontology_status.get("blockers") or [])[:1])
        closeout_blockers.extend(_missing_follow_up_task_blockers(tasks or [], root)[:3])
        closeout_requirements = set(getattr(manifest.lifecycle, "closeout_requires", []) or [])
        if "final_artifacts_present" in closeout_requirements:
            artifact_files = _list_final_artifact_files(root, manifest.paths.artifacts_root)
            if not artifact_files:
                closeout_blockers.append("No final artifacts are present under the configured artifacts root.")
            else:
                indexes = load_integrity_indexes(root)
                tracked = {
                    str(item.artifact_path)
                    for item in indexes.artifact_lineage
                    if item.artifact_type != "dataset"
                    and (
                        str(item.artifact_path) == manifest.paths.artifacts_root
                        or str(item.artifact_path).startswith(f"{manifest.paths.artifacts_root}/")
                    )
                }
                untracked = [path for path in artifact_files if path not in tracked]
                if untracked:
                    sample = ", ".join(untracked[:3])
                    closeout_blockers.append(
                        f"Final artifacts exist on disk without lineage records: {sample}."
                    )
        closeout_gate = evaluate_integrity_gate(root, manifest, action="closeout")
        if closeout_gate.get("blocked"):
            closeout_blockers.extend([str(item) for item in (closeout_gate.get("reasons") or [])[:3]])
        if closeout_blockers:
            closeout_status = {"status": "blocked", "blockers": closeout_blockers}

    return {
        "session": session_status,
        "planner": planner_status,
        "ontology": ontology_status,
        "integrity": integrity_status,
        "critic": critic_status,
        "closeout": closeout_status,
    }
