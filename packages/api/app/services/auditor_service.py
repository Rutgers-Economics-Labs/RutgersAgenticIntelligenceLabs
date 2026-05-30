from __future__ import annotations

from pathlib import Path
from typing import Any
import csv

from app.services.hydration_registry_service import get_hydration_status
from app.services.integrity_service import evaluate_integrity_gate, load_integrity_indexes
from app.services.question_expansion_service import missing_expansion_task_blockers, parse_follow_up_questions
from app.services.reconciliation_service import (
    _artifact_path_is_registry_candidate,
    _artifact_path_should_ignore_drift,
    project_reality_status,
)
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
        relative_path = path.relative_to(project_root)
        if any(part.startswith(".") for part in relative_path.parts):
            continue
        relative = str(relative_path).replace("\\", "/")
        if _artifact_path_should_ignore_drift(relative) or not _artifact_path_is_registry_candidate(relative):
            continue
        files.append(relative)
    return sorted(files)


_PLATFORM_CLAIM_MARKERS = {
    "ontology",
    "hydration",
    "rail",
    "verification",
    "lineage",
    "closeout",
    "artifact",
    "pipeline",
    "registry",
}

_ANALYSIS_MARKERS = {
    "analysis",
    "model",
    "regression",
    "difference-in-differences",
    "did",
    "counterfactual",
    "benchmark",
    "trend",
    "decomposition",
    "robustness",
    "statistical",
    "correlation",
    "comparison",
    "concentration",
    "hhi",
    "share",
    "normalized",
    "rate",
    "estimate",
}


def _word_count(text: str) -> int:
    import re

    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or ""))


def _artifact_text(project_root: Path, artifact_path: str) -> str:
    path = project_root / artifact_path
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".tex", ".csv", ".json"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    if suffix == ".pdf":
        # Prefer the canonical source report beside rendered PDFs. Most local
        # RAIL PDF artifacts are generated from Markdown or TeX, and relying on
        # that source keeps this auditor dependency-light.
        for sibling_suffix in (".md", ".tex", ".txt"):
            sibling = path.with_suffix(sibling_suffix)
            if sibling.exists():
                return sibling.read_text(encoding="utf-8", errors="ignore")
    return ""


def _subject_research_claims(indexes: Any) -> list[Any]:
    claims = []
    for claim in getattr(indexes, "claims", []) or []:
        text = str(getattr(claim, "claim_text", "") or "").strip()
        if not text or not getattr(claim, "source_keys", []):
            continue
        lowered = text.lower()
        marker_hits = sum(1 for marker in _PLATFORM_CLAIM_MARKERS if marker in lowered)
        if marker_hits >= 2:
            continue
        if str(getattr(claim, "status", "") or "") not in {"supported", "partially_verified"}:
            continue
        claims.append(claim)
    return claims


def _has_substantive_data_artifact(project_root: Path, indexes: Any) -> bool:
    for record in getattr(indexes, "artifact_lineage", []) or []:
        artifact_path = str(getattr(record, "artifact_path", "") or "")
        if not artifact_path.endswith(".csv"):
            continue
        path = project_root / artifact_path
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except Exception:
            continue
        fields = rows[0].keys() if rows else []
        if len(rows) >= 20 and len(list(fields)) >= 4:
            return True
    return False


def audit_research_quality(project_root: Path, artifacts_root: str, indexes: Any | None = None) -> dict[str, Any]:
    """Fail closeout when the final artifact is packaged but not research.

    This is intentionally heuristic and conservative: it does not grade taste or
    novelty, but it does require a final report to contain enough question,
    method, evidence, analysis, and subject-matter claims to avoid passing source
    inventories or platform-status memos as research papers.
    """
    indexes = indexes or load_integrity_indexes(project_root)
    blockers: list[str] = []
    report_records = [
        record
        for record in getattr(indexes, "artifact_lineage", []) or []
        if str(getattr(record, "artifact_path", "") or "").startswith(f"{artifacts_root}/")
        and str(getattr(record, "artifact_type", "") or "") == "report"
        and str(getattr(record, "promotion_state", "") or "") in {"partially_verified", "verified"}
        and (project_root / str(getattr(record, "artifact_path", "") or "")).exists()
    ]
    finalish = [
        record
        for record in report_records
        if any(token in str(getattr(record, "artifact_path", "") or "").lower() for token in ("final", "paper", "report"))
        or any(token in str(getattr(record, "title", "") or "").lower() for token in ("final", "paper", "report"))
    ]
    candidates = finalish or report_records
    if not candidates:
        return {"status": "blocked", "blockers": ["No promoted final research report is registered in artifact lineage."]}

    combined_text = "\n\n".join(_artifact_text(project_root, str(getattr(record, "artifact_path", "") or "")) for record in candidates)
    lowered = combined_text.lower()
    words = _word_count(combined_text)
    subject_claims = _subject_research_claims(indexes)
    has_data = _has_substantive_data_artifact(project_root, indexes)
    has_table = "|" in combined_text and "---" in combined_text
    analysis_hits = sorted(marker for marker in _ANALYSIS_MARKERS if marker in lowered)

    if words < 900:
        blockers.append(f"Final report is too thin for research closeout ({words} words; expected at least 900).")
    if len(subject_claims) < 2:
        blockers.append("Fewer than two supported subject-matter research claims have source-backed evidence.")
    if not has_data:
        blockers.append("No substantive analysis dataset/table artifact is registered for the final report.")
    if len(analysis_hits) < 3:
        blockers.append("Final report lacks enough analysis markers such as model, trend, benchmark, robustness, comparison, or concentration.")
    required_sections = {
        "research question": ("research question", "question"),
        "method": ("method", "methodology", "design"),
        "findings": ("finding", "result"),
        "limitations": ("limitation", "caveat"),
    }
    for label, options in required_sections.items():
        if not any(option in lowered for option in options):
            blockers.append(f"Final report is missing an explicit {label} section or discussion.")
    if not has_table:
        blockers.append("Final report does not include a results table.")

    return {
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "wordCount": words,
        "subjectClaimCount": len(subject_claims),
        "analysisMarkers": analysis_hits,
    }


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
    cached_reality = project.get("__controlPlaneReality")
    if isinstance(cached_reality, dict):
        reality = cached_reality
    else:
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
    research_quality_status: dict[str, Any] = {"status": "ready", "blockers": []}
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
        research_quality_status = audit_research_quality(root, manifest.paths.artifacts_root, indexes)
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
        if research_quality_status.get("status") == "blocked":
            closeout_blockers.extend([str(item) for item in (research_quality_status.get("blockers") or [])[:3]])
        if closeout_blockers:
            closeout_status = {"status": "blocked", "blockers": closeout_blockers}

    # research_allowed vs promotion_allowed split (background-health-governance spec).
    #
    # research_allowed: agents may continue producing candidate work even when
    #   ontology/integrity/closeout auditors are flagging issues. Only hard
    #   control-plane safety problems (session/planner) suspend research.
    # promotion_allowed: artifact promotion, claim verification, closeout, and
    #   any other "trust this output" transition. Strict and fail-closed across
    #   every auditor.
    #
    # Critic findings (weakened/rejected hypotheses) are advisory for research
    # but blocking for promotion.
    research_blocking = {"session", "planner"}
    promotion_blocking = {"session", "planner", "ontology", "integrity", "critic", "research_quality", "closeout"}

    auditors = {
        "session": session_status,
        "planner": planner_status,
        "ontology": ontology_status,
        "integrity": integrity_status,
        "critic": critic_status,
        "research_quality": research_quality_status,
        "closeout": closeout_status,
    }

    def _blocked(name: str) -> bool:
        return (auditors.get(name) or {}).get("status") == "blocked"

    research_allowed = not any(_blocked(name) for name in research_blocking)
    promotion_allowed = not any(_blocked(name) for name in promotion_blocking)

    return {
        **auditors,
        "researchAllowed": research_allowed,
        "promotionAllowed": promotion_allowed,
    }
