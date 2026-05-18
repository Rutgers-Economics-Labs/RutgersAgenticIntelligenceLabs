from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.hydration_registry_service import get_hydration_status
from app.services.integrity_service import evaluate_integrity_gate, load_integrity_indexes
from app.services.reconciliation_service import project_reality_status
from rail.manifest import load_manifest

ONTOLOGY_READY_STATES = {"hydrated_on_this_device", "hydrated_on_another_device", "hydrating"}


def _is_ontology_project(project: dict[str, Any]) -> bool:
    root = project.get("localRepoPath")
    if not root:
        return False
    if project.get("approach") == "ontology-first":
        return True
    return (Path(root).resolve() / ".ontology").exists()


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


def _parse_ontology_follow_up_questions(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "research_plan" / "ontology_answerable_follow_up_questions.md"
    if not path.exists():
        return []

    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            if current:
                questions.append(current)
            current = {"title": line[4:].strip(), "classification": None}
            continue
        if current is None:
            continue
        if line.startswith("- Classification:"):
            marker = line.split("`")
            if len(marker) >= 2:
                current["classification"] = marker[1].strip()
            else:
                current["classification"] = line.removeprefix("- Classification:").strip()
    if current:
        questions.append(current)
    return questions


def _missing_follow_up_task_blockers(tasks: list[dict[str, Any]], project_root: Path) -> list[str]:
    task_titles = {str(task.get("title") or "") for task in tasks}
    blockers: list[str] = []
    for question in _parse_ontology_follow_up_questions(project_root):
        title = str(question.get("title") or "").strip()
        classification = str(question.get("classification") or "").strip().lower()
        if not title:
            continue
        if classification == "requires_expansion":
            expected = f"Expand ontology coverage for: {title}"
            if expected not in task_titles:
                blockers.append(f"Missing ontology expansion task for follow-up question: {title}")
        elif classification == "blocked_by_data":
            expected = f"Resolve data blocker for: {title}"
            if expected not in task_titles:
                blockers.append(f"Missing data-blocker task for follow-up question: {title}")
    return blockers


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


async def build_auditor_statuses(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]] | None = None,
    active_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(str(project.get("localRepoPath") or "")).resolve() if project.get("localRepoPath") else None
    reality = await project_reality_status(project, tasks=tasks, active_sessions=active_sessions)

    session_status = {
        "status": "blocked" if reality["staleRuntimeSessionCount"] else "ready",
        "blockers": (
            [f"{reality['staleRuntimeSessionCount']} stale runtime session(s) still marked active."]
            if reality["staleRuntimeSessionCount"]
            else []
        ),
    }
    planner_status = {
        "status": "blocked"
        if reality["duplicateTaskFileCount"] or reality["taskSessionMismatchCount"] or reality.get("secretPolicyRoleDriftCount") or reality.get("roleConfigAliasDriftCount")
        else "ready",
        "blockers": [
            *([f"{reality['duplicateTaskFileCount']} duplicate task file(s) detected."] if reality["duplicateTaskFileCount"] else []),
            *([f"{reality['taskSessionMismatchCount']} task/session state mismatch(es) detected."] if reality["taskSessionMismatchCount"] else []),
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
    }

    ontology_status: dict[str, Any] = {"status": "ready", "blockers": [], "state": None}
    ontology_reality = (reality.get("details") or {}).get("ontologyArtifactDrift") or {}
    if _is_ontology_project(project):
        try:
            hydration = await get_hydration_status(project=project)
            ontology_status["state"] = hydration.get("state")
            duckdb_path = _hydration_duckdb_path(hydration) or project.get("activeOntologyDuckdbPath")
            if hydration.get("state") not in ONTOLOGY_READY_STATES:
                ontology_status = {
                    "status": "blocked",
                    "blockers": [f"Ontology hydration state is `{hydration.get('state')}`."],
                    "state": hydration.get("state"),
                }
            elif not _duckdb_has_populated_rows(duckdb_path):
                ontology_status = {
                    "status": "blocked",
                    "blockers": ["Ontology artifact exists but does not contain populated rows."],
                    "state": hydration.get("state"),
                }
        except Exception as exc:
            ontology_status = {"status": "blocked", "blockers": [f"Could not read hydration status: {exc}"], "state": None}
        if ontology_reality.get("hasDrift"):
            blockers = list(ontology_status.get("blockers") or [])
            blockers.append(
                f"Active ontology artifact pointer drift detected: {ontology_reality.get('reason') or 'unknown_reason'}."
            )
            ontology_status = {
                "status": "blocked",
                "blockers": blockers,
                "state": ontology_status.get("state"),
            }

    integrity_status: dict[str, Any] = {"status": "ready", "blockers": []}
    closeout_status: dict[str, Any] = {"status": "ready", "blockers": []}
    if root and root.exists():
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
        unfinished = [task for task in (tasks or []) if task.get("status") not in {"done", "cancelled"}]
        closeout_blockers: list[str] = []
        if (active_sessions or []):
            closeout_blockers.append(f"{len(active_sessions or [])} active session(s) still exist.")
        if unfinished:
            closeout_blockers.append(f"{len(unfinished)} non-terminal task(s) remain.")
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
        "closeout": closeout_status,
    }
