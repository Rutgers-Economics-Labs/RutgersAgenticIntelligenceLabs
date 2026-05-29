from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

from app.services.audit_service import _session_roots, list_recent_audits, read_latest_audit
from app.services.auditor_service import build_auditor_statuses
from app.services import goal_service, session_files
from app.services.integrity_service import load_integrity_indexes, summarize_agent_workflow_health
from app.services.reconciliation_service import project_reality_status
from rail.integrity import build_artifact_trust_summary, build_source_state


TEXT_PREVIEW_LIMIT = 80_000
TABLE_PREVIEW_ROWS = 25
CONTROL_PLANE_SNAPSHOT_VERSION = 1
CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH = "research_plan/state/control_plane_snapshot.json"


WORKFLOW_PRESETS: dict[str, dict[str, Any]] = {
    "feasibility_memo": {
        "label": "Feasibility memo",
        "role": "research",
        "skills": ["web-research", "source-inventory", "citations"],
        "outputs": ["topics/feasibility_memo.md", "topics/source_inventory.md"],
    },
    "source_inventory": {
        "label": "Source inventory",
        "role": "research",
        "skills": ["source-inventory", "web-research", "data-provenance"],
        "outputs": ["topics/source_inventory.md", "research_plan/graph/sources.yaml"],
    },
    "literature_review": {
        "label": "Literature review",
        "role": "research",
        "skills": ["literature-review", "citations"],
        "outputs": ["topics/literature_review.md"],
    },
    "data_pipeline": {
        "label": "Data pipeline",
        "role": "data",
        "skills": ["data-provenance", "verification"],
        "outputs": [".ontology/sources/", ".ontology/pipelines/", "topics/data_provenance.md"],
    },
    "econometric_model": {
        "label": "Econometric model",
        "role": "coding",
        "skills": ["econometric-design", "verification", "data-provenance"],
        "outputs": ["artifacts/model_outputs/", "topics/model_design.md"],
    },
    "policy_memo": {
        "label": "Policy memo",
        "role": "research",
        "skills": ["policy-analysis", "citations"],
        "outputs": ["artifacts/policy_memo.md"],
    },
    "technical_report": {
        "label": "Technical report",
        "role": "artifact",
        "skills": ["citations", "verification"],
        "outputs": ["artifacts/technical_report.md"],
    },
    "presentation_deck": {
        "label": "Presentation deck",
        "role": "artifact",
        "skills": ["citations"],
        "outputs": ["artifacts/presentation_deck.md"],
    },
    "data_workbook": {
        "label": "Data workbook/dashboard",
        "role": "artifact",
        "skills": ["data-provenance", "verification"],
        "outputs": ["artifacts/data_workbook.csv", "artifacts/dashboard.md"],
    },
    "integrity_review": {
        "label": "Integrity review",
        "role": "health",
        "skills": ["verification", "data-provenance"],
        "outputs": ["research_plan/review/health_report.md", "research_plan/review/blockers.md"],
    },
}


def project_root(project: dict) -> Path:
    planner_service, _ = _runtime_services()
    root = planner_service.project_root_from_record(project) if planner_service else None
    if root is None and project.get("localRepoPath"):
        root = Path(str(project["localRepoPath"]))
    if root is None:
        raise ValueError("Project does not have a localRepoPath configured")
    return root


def _runtime_services() -> tuple[Any | None, Any | None]:
    try:
        from app.services import planner_service, running_agent_service
    except ModuleNotFoundError:
        return None, None
    return planner_service, running_agent_service


def _read(path: Path, limit: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit] if limit else text


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def control_plane_snapshot_path(root: Path) -> Path:
    return root / CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH


def _command_center_snapshot_fields(center: dict[str, Any]) -> dict[str, Any]:
    return {
        "currentPlan": center.get("currentPlan"),
        "missionBrief": center.get("missionBrief"),
        "goal": center.get("goal"),
        "nextAction": center.get("nextAction"),
        "taskCounts": center.get("taskCounts"),
        "plannerSnapshot": center.get("plannerSnapshot"),
        "latestTruth": center.get("latestTruth"),
        "recentArtifacts": center.get("recentArtifacts"),
        "sourceSummary": center.get("sourceSummary"),
        "skillSummary": center.get("skillSummary"),
        "integritySummary": center.get("integritySummary"),
        "hypothesisTaskLinks": center.get("hypothesisTaskLinks"),
        "ontologyFollowUps": center.get("ontologyFollowUps"),
        "auditedTruth": center.get("auditedTruth"),
        "recentAudits": center.get("recentAudits"),
        "lifecyclePhase": center.get("lifecyclePhase"),
        "closeoutCertificate": center.get("closeoutCertificate"),
        "currentBlocker": center.get("currentBlocker"),
        "blockerSummary": center.get("blockerSummary"),
        "repairQueue": center.get("repairQueue"),
        "recommendedRepairTask": center.get("recommendedRepairTask"),
        "projectReality": center.get("projectReality"),
        "auditors": center.get("auditors"),
        "repoHealth": center.get("repoHealth"),
    }


def read_control_plane_snapshot(project: dict[str, Any]) -> dict[str, Any] | None:
    try:
        root = project_root(project)
    except Exception:
        return None

    path = control_plane_snapshot_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("snapshotVersion") or 0) != CONTROL_PLANE_SNAPSHOT_VERSION:
        return None
    command_center = payload.get("commandCenter")
    if not isinstance(command_center, dict):
        return None
    return {
        "snapshotVersion": CONTROL_PLANE_SNAPSHOT_VERSION,
        "generatedAt": int(payload.get("generatedAt") or 0),
        "commandCenter": command_center,
        "path": CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH,
    }


def control_plane_snapshot_meta(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "loaded": bool(snapshot),
        "path": (snapshot or {}).get("path") or CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH,
        "generatedAt": (snapshot or {}).get("generatedAt"),
        "version": (snapshot or {}).get("snapshotVersion") or CONTROL_PLANE_SNAPSHOT_VERSION,
    }


def load_control_plane_summary(project: dict[str, Any]) -> dict[str, Any]:
    snapshot = read_control_plane_snapshot(project)
    return {
        "summary": (snapshot or {}).get("commandCenter") or {},
        "snapshot": control_plane_snapshot_meta(snapshot),
    }


async def persist_control_plane_snapshot(project: dict[str, Any]) -> dict[str, Any]:
    root = project_root(project)
    center = await _build_live_command_center(project)
    payload = {
        "snapshotVersion": CONTROL_PLANE_SNAPSHOT_VERSION,
        "generatedAt": int(time.time()),
        "commandCenter": _command_center_snapshot_fields(center),
    }
    path = control_plane_snapshot_path(root)
    _write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {
        "path": CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH,
        "generatedAt": payload["generatedAt"],
    }


def _derive_next_action(
    *,
    pending_approvals: list[dict[str, Any]],
    active_sessions: list[dict[str, Any]],
    task_counts: dict[str, Any] | None,
) -> str:
    total_tasks = int((task_counts or {}).get("total") or 0)
    if pending_approvals:
        return "Review pending approvals"
    if active_sessions:
        return "Monitor active agent sessions"
    if total_tasks:
        return "Select the next ready task or launch a research workflow"
    return "Start a research workflow"


def _planner_snapshot(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    def _rows(*statuses: str, limit: int | None = None) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for task in tasks:
            if str(task.get("status") or "") not in statuses:
                continue
            items.append(
                {
                    "id": str(task.get("_id") or ""),
                    "title": str(task.get("title") or ""),
                    "status": str(task.get("status") or ""),
                    "description": str(task.get("description") or ""),
                }
            )
            if limit is not None and len(items) >= limit:
                break
        return items

    return {
        "now": _rows("running", "ready"),
        "next": _rows("awaiting_approval", limit=3),
        "later": _rows("backlog", limit=3),
        "done": _rows("done", limit=3),
        "blocked": _rows("blocked"),
    }


def _latest_truth_snapshot(integrity_indexes: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    claims = list(getattr(integrity_indexes, "claims", []) or [])
    rows: list[dict[str, Any]] = []
    for claim in claims[:limit]:
        statement = str(getattr(claim, "statement", "") or "").strip()
        status = str(getattr(claim, "status", "") or "")
        evidence_paths = list(getattr(claim, "evidence_paths", []) or [])
        rows.append(
            {
                "claim": statement,
                "confidence": 0.95 if status == "verified" else 0.7,
                "evidenceRefs": evidence_paths,
                "verified": status == "verified",
            }
        )
    return rows


def _command_center_from_snapshot(
    project: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    active_sessions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
) -> dict[str, Any]:
    center = dict(snapshot.get("commandCenter") or {})
    task_counts = center.get("taskCounts") or {"total": 0, "byStatus": {}}
    center["project"] = {
        "id": project.get("_id") or project.get("slug") or "",
        "name": project.get("name"),
        "slug": project.get("slug"),
        "status": project.get("status"),
        "localRepoPath": project.get("localRepoPath"),
        "defaultBranch": project.get("defaultBranch") or "main",
    }
    center["activeSessions"] = active_sessions
    center["pendingApprovals"] = pending_approvals
    center["nextAction"] = _derive_next_action(
        pending_approvals=pending_approvals,
        active_sessions=active_sessions,
        task_counts=task_counts,
    )
    center["snapshot"] = control_plane_snapshot_meta(snapshot)
    return center


def _title_from_markdown(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


def _summary_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        return stripped[:240]
    return ""


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _safe_status(value: Any, default: str = "candidate") -> str:
    status = str(value or default).lower().replace(" ", "_").replace("-", "_")
    if status in {"ready", "draft_for_review"}:
        return "candidate"
    if status in {"missing_auth_or_manual", "missing"}:
        return "missing_auth_or_manual"
    if status not in {"candidate", "validated", "blocked", "rejected", "missing_auth_or_manual"}:
        return default
    return status


def list_project_skills(project: dict) -> dict[str, Any]:
    root = project_root(project)
    skill_rows: list[dict[str, Any]] = []
    role_skill_access: dict[str, bool] = {}

    for agent_path in sorted((root / "agents").glob("*.yaml")):
        data = _load_yaml(agent_path)
        role = str(data.get("role") or agent_path.stem)
        role_skill_access[role] = bool(data.get("skills", {}).get("allow_use"))

    allowed_roles = sorted(role for role, allowed in role_skill_access.items() if allowed)
    for path in sorted((root / "skills").glob("*.md")):
        content = _read(path)
        slug = path.stem
        skill_rows.append(
            {
                "slug": slug,
                "name": _title_from_markdown(content, slug.replace("-", " ").title()),
                "summary": _summary_from_markdown(content),
                "path": _rel(path, root),
                "content": content,
                "usedBy": allowed_roles,
            }
        )

    return {
        "skills": skill_rows,
        "summary": {
            "count": len(skill_rows),
            "agentRolesWithSkillAccess": allowed_roles,
        },
    }


def _source_row_from_candidate(item: dict[str, Any], path: str) -> dict[str, Any]:
    return {
        "id": str(item.get("slug") or item.get("externalId") or item.get("name") or path),
        "name": str(item.get("name") or item.get("slug") or "Source"),
        "publisher": str(item.get("publisher") or item.get("provider") or "unknown"),
        "provider": str(item.get("provider") or "unknown"),
        "status": _safe_status(item.get("status") or item.get("readiness")),
        "accessMethod": str(item.get("accessMethod") or item.get("configKind") or item.get("type") or "unknown"),
        "geography": str(item.get("geography") or item.get("coverage") or ""),
        "timeCoverage": str(item.get("timeCoverage") or item.get("time_window") or ""),
        "updateFrequency": str(item.get("updateFrequency") or ""),
        "keyFields": item.get("keyFields") or item.get("fields") or [],
        "qualityNotes": str(item.get("qualityNotes") or item.get("reason") or item.get("description") or ""),
        "linkedFiles": [path],
    }


def list_project_sources(project: dict, *, root: Path | None = None, indexes: Any | None = None) -> dict[str, Any]:
    root = root or project_root(project)
    rows: dict[str, dict[str, Any]] = {}
    indexes = indexes if indexes is not None else _project_integrity_indexes(project)
    repo_sources = {row.source_key: row for row in (indexes.sources if indexes is not None else [])}

    graph_sources = root / "research_plan" / "graph" / "sources.yaml"
    if graph_sources.exists():
        payload = _load_yaml(graph_sources)
        for item in payload.get("sources", []) if isinstance(payload, dict) else []:
            if isinstance(item, dict):
                row = _source_row_from_candidate(item, _rel(graph_sources, root))
                rows[row["id"]] = row

    for source_path in sorted((root / ".ontology" / "sources").glob("*.y*ml")):
        data = _load_yaml(source_path)
        if not isinstance(data, dict):
            data = {}
        row = {
            "id": source_path.stem,
            "name": str(data.get("name") or data.get("slug") or source_path.stem),
            "publisher": str(data.get("publisher") or data.get("provider") or data.get("type") or "unknown"),
            "provider": str(data.get("provider") or data.get("type") or "unknown"),
            "status": _safe_status(data.get("status"), "validated"),
            "accessMethod": str(data.get("type") or data.get("accessMethod") or "config"),
            "geography": str(data.get("geography") or ""),
            "timeCoverage": str(data.get("timeCoverage") or ""),
            "updateFrequency": str(data.get("updateFrequency") or ""),
            "keyFields": data.get("fields") or data.get("keyFields") or [],
            "qualityNotes": str(data.get("description") or ""),
            "linkedFiles": [_rel(source_path, root)],
        }
        existing = rows.get(row["id"])
        if existing:
            existing["linkedFiles"] = sorted(set(existing["linkedFiles"] + row["linkedFiles"]))
            existing["status"] = "validated"
        else:
            rows[row["id"]] = row

    for source_key, source in repo_sources.items():
        state = _source_state(source)
        existing = rows.get(source_key)
        if existing:
            existing["freshnessStatus"] = source.freshness_status
            existing["qualityStatus"] = source.quality_status
            existing["sourceState"] = state
            existing["publisher"] = existing.get("publisher") or str(source.origin or "unknown")
            existing["provider"] = existing.get("provider") or str(source.source_type or "unknown")
        else:
            rows[source_key] = {
                "id": source_key,
                "name": source.title,
                "publisher": str(source.origin or "unknown"),
                "provider": str(source.source_type or "unknown"),
                "status": _safe_status(source.quality_status, "validated"),
                "accessMethod": str(source.access_method or source.source_type or "unknown"),
                "geography": "",
                "timeCoverage": "",
                "updateFrequency": "",
                "keyFields": list(source.provenance.get("fields") or []),
                "qualityNotes": str(source.quality_notes or source.notes or ""),
                "linkedFiles": [source.source_path],
                "freshnessStatus": source.freshness_status,
                "qualityStatus": source.quality_status,
                "sourceState": state,
            }

    notes_path = root / "topics" / "source_notes.md"
    source_notes = _read(notes_path, 40_000) if notes_path.exists() else ""
    status_counts: dict[str, int] = {}
    freshness_counts: dict[str, int] = {}
    admissibility_counts: dict[str, int] = {}
    admissibility_highlights: list[dict[str, str]] = []
    for row in rows.values():
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        freshness = str(row.get("freshnessStatus") or "unknown")
        freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1
        admissibility = str((row.get("sourceState") or {}).get("admissibilityStatus") or "unknown")
        admissibility_counts[admissibility] = admissibility_counts.get(admissibility, 0) + 1
        if admissibility not in {"observed", "derived"}:
            admissibility_highlights.append(
                {
                    "id": str(row.get("id") or ""),
                    "name": str(row.get("name") or row.get("id") or "Source"),
                    "admissibilityStatus": admissibility,
                    "freshnessStatus": freshness,
                    "qualityStatus": str(row.get("qualityStatus") or row.get("status") or "unknown"),
                }
            )

    admissibility_highlights.sort(key=lambda item: (item["admissibilityStatus"], item["name"]))

    return {
        "sources": list(rows.values()),
        "summary": {
            "count": len(rows),
            "statusCounts": status_counts,
            "freshnessCounts": freshness_counts,
            "admissibilityCounts": admissibility_counts,
            "admissibilityHighlights": admissibility_highlights[:6],
            "notesPath": _rel(notes_path, root) if notes_path.exists() else None,
        },
        "notes": source_notes,
    }


def _artifact_type(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in {"md", "markdown"}:
        return "markdown"
    if ext in {"csv", "tsv"}:
        return "table"
    if ext in {"json", "yaml", "yml", "ndjson"}:
        return "structured"
    if ext in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return "image"
    if ext in {"html", "htm"}:
        return "html"
    if ext in {"pdf", "ppt", "pptx", "xls", "xlsx"}:
        return ext
    return "file"


def _preview_artifact(path: Path) -> dict[str, Any]:
    atype = _artifact_type(path)
    preview: dict[str, Any] = {"kind": atype}
    if atype in {"markdown", "structured", "html"}:
        preview["content"] = _read(path, TEXT_PREVIEW_LIMIT)
    elif atype == "table":
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        rows: list[list[str]] = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for idx, row in enumerate(reader):
                if idx >= TABLE_PREVIEW_ROWS:
                    break
                rows.append(row)
        preview["rows"] = rows
    elif atype == "image":
        preview["imagePath"] = str(path)
    return preview


def _project_integrity_indexes(project: dict) -> Any | None:
    root = project_root(project)
    if not root.exists():
        return None
    try:
        return load_integrity_indexes(root)
    except Exception:
        return None


def _task_hypothesis_links(root: Path) -> dict[str, list[str]]:
    hypothesis_path = root / "research_plan" / "state" / "hypotheses.json"
    if not hypothesis_path.exists():
        return {}
    try:
        payload = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    links: dict[str, list[str]] = {}
    if not isinstance(payload, list):
        return links
    for row in payload:
        if not isinstance(row, dict):
            continue
        hypothesis_id = str(row.get("id") or row.get("hypothesis_id") or "").strip()
        if not hypothesis_id:
            continue
        for task_id in row.get("task_ids") or []:
            task_key = str(task_id).strip()
            if not task_key:
                continue
            links.setdefault(task_key, []).append(hypothesis_id)
    return links


def _boost_ready_tasks_with_hypotheses(project: dict, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranking = rank_hypotheses(project)
    if not ranking:
        return tasks
    ranking_by_id = {str(item.get("id")): item for item in ranking}
    root = project_root(project)
    task_links = _task_hypothesis_links(root)
    boosted: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task.get("_id") or "")
        links = task_links.get(task_id, [])
        best = max(
            (ranking_by_id.get(item) for item in links if ranking_by_id.get(item)),
            key=lambda x: x["computedScore"],
            default=None,
        )
        updated = dict(task)
        if best is not None:
            updated["_hypothesisPriorityBoost"] = int(round(float(best["computedScore"]) * 100))
            updated["hypothesisLinks"] = links
            updated["hypothesisScore"] = float(best["computedScore"])
        boosted.append(updated)
    return boosted


def _reference_key(reference: str) -> str:
    return reference.split("#", 1)[-1].strip()


def _claim_needs_evidence(claim: dict[str, Any]) -> bool:
    status = str(claim.get("status") or "draft")
    evidence_kind = claim.get("evidence_kind")
    has_evidence = bool(claim.get("evidence_paths") or claim.get("source_keys") or claim.get("evidence_chunk_keys"))
    return (
        status in {"draft", "unsupported", "needs_evidence", "stale", "conflicted"}
        or (status == "supported" and not has_evidence)
        or (status == "supported" and evidence_kind == "semantic_suggestion")
    )


def _build_agent_workflow_summary(
    assumptions: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    artifact_lineage: list[dict[str, Any]],
    verification_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    source_by_key = {str(item.get("source_key")): item for item in sources}
    claim_by_key = {str(item.get("claim_key")): item for item in claims}

    datasets_missing_provenance = [
        row["artifact_path"]
        for row in artifact_lineage
        if row.get("artifact_type") == "dataset"
        and (
            not row.get("sources")
            or any(
                not (source_by_key.get(_reference_key(reference), {}).get("provenance") or {})
                for reference in row.get("sources") or []
            )
        )
    ]
    analysis_missing_lineage = [
        row["artifact_path"]
        for row in artifact_lineage
        if row.get("artifact_type") != "dataset"
        and not (row.get("inputs") and row.get("scripts"))
    ]
    analysis_missing_verification = [
        row["artifact_path"]
        for row in artifact_lineage
        if row.get("artifact_type") != "dataset"
        and not row.get("verification_runs")
        and row.get("reproducibility_mode") not in {"manual", "non_reproducible"}
    ]
    unsupported_claim_keys = {row["claim_key"] for row in claims if _claim_needs_evidence(row)}
    artifacts_with_unsupported_claims = [
        row["artifact_path"]
        for row in artifact_lineage
        if {
            _reference_key(reference)
            for reference in row.get("claims") or []
        }.intersection(unsupported_claim_keys)
    ]
    stale_source_keys = [
        row["source_key"]
        for row in sources
        if row.get("freshness_status") in {"needs_refresh", "stale"}
    ]
    reproducibility_gaps = [
        row["artifact_path"]
        for row in artifact_lineage
        if row.get("artifact_type") != "dataset"
        and row.get("reproducibility_mode") is None
        and not (row.get("inputs") and row.get("scripts"))
    ]
    missing_evidence_claims = sorted(unsupported_claim_keys)
    verification_failures = [
        row["run_id"]
        for row in verification_runs
        if row.get("status") in {"failed", "blocked"}
    ]

    def _status(blockers: list[str]) -> str:
        return "blocked" if blockers else "ready"

    return {
        "research": {
            "status": _status([]),
            "requirements": [
                "Separate facts, interpretations, and open questions in research outputs.",
                "Record caveats for non-final empirical claims.",
            ],
        },
        "data": {
            "status": _status(datasets_missing_provenance),
            "datasetsMissingProvenance": datasets_missing_provenance,
            "requirements": [
                "Datasets must retain source provenance and freshness metadata.",
            ],
        },
        "coding": {
            "status": _status(sorted(set(analysis_missing_lineage + analysis_missing_verification))),
            "artifactsMissingLineage": analysis_missing_lineage,
            "artifactsMissingVerification": analysis_missing_verification,
            "requirements": [
                "Analysis outputs must declare inputs and scripts.",
                "Deterministic analyses must carry verification runs before handoff.",
            ],
        },
        "artifact": {
            "status": _status(artifacts_with_unsupported_claims),
            "artifactsWithUnsupportedClaims": artifacts_with_unsupported_claims,
            "requirements": [
                "Artifact narratives must preserve evidence links.",
                "Artifacts with unsupported claims cannot be treated as trusted.",
            ],
        },
        "health": {
            "status": _status(sorted(set(missing_evidence_claims + stale_source_keys + reproducibility_gaps + verification_failures))),
            "missingEvidenceClaims": missing_evidence_claims,
            "staleSources": stale_source_keys,
            "reproducibilityGaps": reproducibility_gaps,
            "failedVerificationRuns": verification_failures,
            "requirements": [
                "Detect missing evidence, stale sources, and reproducibility gaps.",
            ],
        },
    }


def _artifact_verification_status(path: str, lineage: Any | None, verification_runs: list[Any]) -> str:
    if lineage and lineage.promotion_state == "stale":
        return "stale"
    if lineage and lineage.verification_runs:
        statuses = [
            run.status
            for run in verification_runs
            if any(_reference_key(reference) == run.run_id for reference in lineage.verification_runs)
        ]
        if statuses:
            if "failed" in statuses:
                return "failed"
            if "blocked" in statuses:
                return "blocked"
            if "pending" in statuses:
                return "pending"
            if all(status == "passed" for status in statuses):
                return "passed"
    matching_runs = [run.status for run in verification_runs if path in run.artifact_paths]
    if matching_runs:
        if "failed" in matching_runs:
            return "failed"
        if "blocked" in matching_runs:
            return "blocked"
        if "pending" in matching_runs:
            return "pending"
        if all(status == "passed" for status in matching_runs):
            return "passed"
    return "unverified"


def _source_state(row: Any) -> dict[str, Any]:
    return build_source_state(row)


def _artifact_trust_state(lineage: Any, verification_status: str) -> dict[str, Any]:
    return build_artifact_trust_summary(
        lineage,
        verification_status=verification_status,
        artifact_blocked=lineage.promotion_state in {"blocked", "needs_evidence"},
    )


def rank_hypotheses(project: dict, *, indexes: Any | None = None) -> list[dict[str, Any]]:
    indexes = indexes if indexes is not None else _project_integrity_indexes(project)
    if indexes is None:
        return []
    source_by_key = {item.source_key: item for item in indexes.sources}
    claim_by_key = {item.claim_key: item for item in indexes.claims}

    ranked: list[dict[str, Any]] = []
    for hypothesis in indexes.hypotheses:
        linked_claims = [claim_by_key[key] for key in hypothesis.claim_keys if key in claim_by_key]
        claim_count = len(linked_claims)
        supported_count = sum(1 for claim in linked_claims if claim.status == "supported")
        stale_count = sum(1 for claim in linked_claims if claim.status in {"stale", "needs_evidence", "unsupported", "conflicted"})
        linked_source_keys = sorted({key for claim in linked_claims for key in claim.source_keys})
        linked_sources = [source_by_key[key] for key in linked_source_keys if key in source_by_key]
        fresh_sources = sum(1 for source in linked_sources if source.freshness_status == "fresh")
        reproducible_artifacts = sum(
            1
            for artifact in indexes.artifact_lineage
            if artifact.artifact_path in hypothesis.artifact_paths
            and (
                artifact.reproducibility_mode in {"deterministic", "manual"}
                or bool(artifact.inputs and artifact.scripts and artifact.verification_runs)
            )
        )
        artifact_count = len(hypothesis.artifact_paths)
        evidence_coverage = (supported_count / claim_count) if claim_count else 0.0
        data_ready = (fresh_sources / len(linked_sources)) if linked_sources else 0.0
        reproducibility = (reproducible_artifacts / artifact_count) if artifact_count else 0.0
        score = round((0.5 * evidence_coverage) + (0.3 * data_ready) + (0.2 * reproducibility), 4)
        reasons: list[str] = []
        reasons.append(f"evidence_coverage={evidence_coverage:.2f} ({supported_count}/{claim_count or 1} claims supported)")
        reasons.append(f"data_ready={data_ready:.2f} ({fresh_sources}/{len(linked_sources) or 1} linked sources fresh)")
        reasons.append(f"reproducibility={reproducibility:.2f} ({reproducible_artifacts}/{artifact_count or 1} linked artifacts reproducible)")
        if stale_count:
            reasons.append(f"{stale_count} linked claims are stale or under-supported")
        ranked.append(
            {
                **hypothesis.model_dump(mode="json", by_alias=True),
                "computedScore": score,
                "scoreBreakdown": {
                    "evidenceCoverage": round(evidence_coverage, 4),
                    "dataReady": round(data_ready, 4),
                    "reproducibility": round(reproducibility, 4),
                },
                "rankingReasons": reasons,
            }
        )
    ranked.sort(key=lambda item: item["computedScore"], reverse=True)
    return ranked


def _write_hypothesis_ranking_decisions(project: dict, rankings: list[dict[str, Any]]) -> None:
    root = project_root(project)
    decision_path = root / "research_plan" / "decisions.md"
    lines = ["## Hypothesis ranking", ""]
    if not rankings:
        lines.append("- No hypotheses available for ranking.")
    for item in rankings[:5]:
        lines.append(f"- `{item['id']}` score={item['computedScore']:.2f} status={item.get('status') or 'draft'}")
    lines.extend(["", ""])
    with decision_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def list_project_integrity(project: dict, *, root: Path | None = None, indexes: Any | None = None) -> dict[str, Any]:
    root = root or project_root(project)
    indexes = indexes if indexes is not None else _project_integrity_indexes(project)
    if indexes is None:
        empty = {
            "assumptions": [],
            "sources": [],
            "claims": [],
            "artifact_lineage": [],
            "verification_runs": [],
        }
        return {
            "indexes": empty,
            "summary": {
                "assumptionCount": 0,
                "sourceCount": 0,
                "sourceFreshnessCounts": {},
                "sourceAdmissibilityCounts": {},
                "claimCount": 0,
                "artifactCount": 0,
                "staleArtifactCount": 0,
                "verificationRunCount": 0,
                "verificationStatusCounts": {},
                "promotionStateCounts": {},
            },
            "agentWorkflow": _build_agent_workflow_summary([], [], [], [], []),
            "staleOutputs": [],
            "hypothesisRanking": [],
        }

    assumptions = [row.model_dump(mode="json") for row in indexes.assumptions]
    sources = []
    for row in indexes.sources:
        payload = row.model_dump(mode="json")
        payload["sourceState"] = _source_state(row)
        sources.append(payload)
    claims = [row.model_dump(mode="json") for row in indexes.claims]
    artifact_lineage = []
    for row in indexes.artifact_lineage:
        payload = row.model_dump(mode="json")
        verification_status = _artifact_verification_status(row.artifact_path, row, indexes.verification_runs)
        payload["verificationStatus"] = verification_status
        payload["trustState"] = _artifact_trust_state(row, verification_status)
        artifact_lineage.append(payload)
    verification_runs = [row.model_dump(mode="json") for row in indexes.verification_runs]

    promotion_state_counts: dict[str, int] = {}
    verification_status_counts: dict[str, int] = {}
    source_freshness_counts: dict[str, int] = {}
    source_admissibility_counts: dict[str, int] = {}
    for row in indexes.sources:
        source_freshness_counts[row.freshness_status] = source_freshness_counts.get(row.freshness_status, 0) + 1
        admissibility = str(_source_state(row).get("admissibilityStatus") or "unknown")
        source_admissibility_counts[admissibility] = source_admissibility_counts.get(admissibility, 0) + 1
    for row in indexes.artifact_lineage:
        promotion_state_counts[row.promotion_state] = promotion_state_counts.get(row.promotion_state, 0) + 1
        status = _artifact_verification_status(row.artifact_path, row, indexes.verification_runs)
        verification_status_counts[status] = verification_status_counts.get(status, 0) + 1

    stale_outputs = []
    for row in indexes.artifact_lineage:
        if row.promotion_state != "stale" and not row.stale_reasons:
            continue
        payload = row.model_dump(mode="json")
        verification_status = _artifact_verification_status(row.artifact_path, row, indexes.verification_runs)
        payload["verificationStatus"] = verification_status
        payload["trustState"] = _artifact_trust_state(row, verification_status)
        stale_outputs.append(payload)
    agent_workflow = summarize_agent_workflow_health(root)

    return {
        "indexes": {
            "assumptions": assumptions,
            "sources": sources,
            "claims": claims,
            "hypotheses": [row.model_dump(mode="json", by_alias=True) for row in indexes.hypotheses],
            "artifact_lineage": artifact_lineage,
            "verification_runs": verification_runs,
        },
        "summary": {
            "assumptionCount": len(assumptions),
            "sourceCount": len(sources),
            "sourceFreshnessCounts": source_freshness_counts,
            "sourceAdmissibilityCounts": source_admissibility_counts,
            "claimCount": len(claims),
            "hypothesisCount": len(indexes.hypotheses),
            "artifactCount": len(artifact_lineage),
            "staleArtifactCount": len(stale_outputs),
            "verificationRunCount": len(verification_runs),
            "verificationStatusCounts": verification_status_counts,
            "promotionStateCounts": promotion_state_counts,
        },
        "agentWorkflow": agent_workflow,
        "staleOutputs": stale_outputs,
        "hypothesisRanking": rank_hypotheses(project, indexes=indexes),
    }


def list_project_artifacts(
    project: dict,
    *,
    root: Path | None = None,
    indexes: Any | None = None,
    include_previews: bool = True,
) -> dict[str, Any]:
    root = root or project_root(project)
    artifact_root = root / "artifacts"
    indexes = indexes if indexes is not None else _project_integrity_indexes(project)
    lineage_by_path = {
        row.artifact_path: row for row in (indexes.artifact_lineage if indexes is not None else [])
    }
    verification_runs = indexes.verification_runs if indexes is not None else []
    artifacts: list[dict[str, Any]] = []
    if artifact_root.is_dir():
        for path in sorted(p for p in artifact_root.rglob("*") if p.is_file()):
            stat = path.stat()
            rel_path = _rel(path, root)
            lineage = lineage_by_path.get(rel_path)
            promotion_state = lineage.promotion_state if lineage else "exploratory"
            verification_status = _artifact_verification_status(rel_path, lineage, verification_runs)
            stale_reasons = list(lineage.stale_reasons) if lineage else []
            trust_state = _artifact_trust_state(lineage, verification_status) if lineage else {
                "currentState": promotion_state,
                "verificationStatus": verification_status,
                "isTrusted": False,
                "isBlocked": False,
                "isStale": False,
                "hasEvidence": False,
                "hasFreshSources": False,
                "isReproducible": False,
                "staleReasons": stale_reasons,
                "blockingReasons": [],
                "eligibleTransitions": [],
                "promotableTargets": [],
                "blockingClaims": [],
                "blockingSources": [],
                "blockingArtifacts": [],
                "blockingVerificationRuns": [],
                "recommendedNextAction": "Attach claims or sources so the artifact has explicit lineage.",
            }
            previewable = _artifact_type(path) in {"markdown", "table", "structured", "image", "html"}
            artifacts.append(
                {
                    "name": path.name,
                    "path": rel_path,
                    "type": _artifact_type(path),
                    "sizeBytes": stat.st_size,
                    "modifiedAt": int(stat.st_mtime * 1000),
                    "previewable": previewable,
                    "preview": _preview_artifact(path) if include_previews and previewable else None,
                    "promotionState": promotion_state,
                    "verificationStatus": verification_status,
                    "trustState": trust_state,
                    "assumptions": list(lineage.assumptions) if lineage else [],
                    "sources": list(lineage.sources) if lineage else [],
                    "claims": list(lineage.claims) if lineage else [],
                    "inputs": list(lineage.inputs) if lineage else [],
                    "scripts": list(lineage.scripts) if lineage else [],
                    "verificationRuns": list(lineage.verification_runs) if lineage else [],
                    "staleReasons": stale_reasons,
                    "generatedAt": lineage.generated_at if lineage else None,
                }
            )
    type_counts: dict[str, int] = {}
    promotion_counts: dict[str, int] = {}
    verification_counts: dict[str, int] = {}
    for artifact in artifacts:
        type_counts[artifact["type"]] = type_counts.get(artifact["type"], 0) + 1
        promotion = artifact["promotionState"]
        verification = artifact["verificationStatus"]
        promotion_counts[promotion] = promotion_counts.get(promotion, 0) + 1
        verification_counts[verification] = verification_counts.get(verification, 0) + 1
    return {
        "artifacts": artifacts,
        "summary": {
            "count": len(artifacts),
            "typeCounts": type_counts,
            "promotionStateCounts": promotion_counts,
            "verificationStatusCounts": verification_counts,
            "staleCount": sum(1 for artifact in artifacts if artifact["promotionState"] == "stale"),
            "trustedCount": sum(1 for artifact in artifacts if artifact["trustState"]["isTrusted"]),
            "blockedCount": sum(1 for artifact in artifacts if artifact["trustState"]["isBlocked"]),
        },
    }


def _summarize_current_plan(project: dict) -> dict[str, Any]:
    planner_service, _ = _runtime_services()
    root = planner_service.project_root_from_record(project) if planner_service else None
    if root is None and project.get("localRepoPath"):
        root = Path(str(project["localRepoPath"]))
    if root is None:
        return {"path": None, "summary": ""}
    path = root / "research_plan" / "current_plan.md"
    if not path.exists():
        return {"path": None, "summary": ""}
    content = _read(path, 20_000)
    return {"path": _rel(path, root), "summary": _summary_from_markdown(content), "content": content}


def _count_phrase(value: int, noun: str) -> str:
    return f"{value} {noun}" if value == 1 else f"{value} {noun}s"


def _ensure_sentence(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _session_snapshot(root: Path) -> dict[str, Any]:
    state = session_files.read_state(root)
    summary = session_files.normalize_completion_summary(
        state.get("completion_summary"),
        status=str(state.get("status") or "initialized"),
    )
    return {
        "sessionId": str(state.get("session_id") or root.name),
        "role": str(state.get("role") or root.parent.name or "agent"),
        "status": str(state.get("status") or "unknown"),
        "updatedAt": str(state.get("updated_at") or ""),
        "reviewStatus": str(state.get("review_status") or ""),
        "completionSummary": summary,
    }


def _session_sort_key(root: Path) -> tuple[int, int, int, str, float]:
    state_path = root / "state.json"
    snapshot = _session_snapshot(root)
    completion = snapshot.get("completionSummary") or {}
    populated_fields = sum(
        1
        for key in ("artifacts_created", "sources_used", "blockers", "recommended_next_tasks", "verification_results")
        if completion.get(key)
    )
    status = str(snapshot.get("status") or "")
    role = str(snapshot.get("role") or "")
    meaningful_status = 0 if status == "initialized" else 1
    non_planner = 0 if role == "planner" else 1
    updated_at = str(snapshot.get("updatedAt") or "")
    try:
        mtime = state_path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    return (populated_fields, meaningful_status, non_planner, updated_at, mtime)


def _latest_session_snapshot(root: Path) -> dict[str, Any] | None:
    session_roots = _session_roots(root)
    if not session_roots:
        return None
    session_root = max(session_roots, key=_session_sort_key)
    snapshot = _session_snapshot(session_root)
    if not snapshot:
        return None
    return snapshot


def _compact_task_title(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return "review the board"
    return text[:-1] if text.endswith(".") else text


def _build_mission_brief(
    *,
    root: Path,
    current_plan: dict[str, Any],
    next_action: str,
    lifecycle_phase: str,
    status_counts: dict[str, int],
    active_sessions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
    recent_artifacts: list[dict[str, Any]],
    source_summary: dict[str, Any],
    blocker_summary: dict[str, Any] | None,
    recommended_repair_task: dict[str, Any] | None,
    auditors: dict[str, Any],
) -> dict[str, Any]:
    latest_session = _latest_session_snapshot(root)
    open_queue = sum(
        count for status, count in status_counts.items() if status not in {"done", "cancelled", "backlog"}
    )
    ready_count = int(status_counts.get("ready") or 0)
    waiting_count = int(status_counts.get("awaiting_approval") or 0)
    running_count = int(status_counts.get("running") or 0)
    artifact_count = len(recent_artifacts)
    source_count = int(source_summary.get("count") or 0)
    current_bits = [
        f"This project is in {lifecycle_phase.replace('_', ' ')}.",
        f"It currently has {_count_phrase(open_queue, 'open task')} across {_count_phrase(running_count, 'running task')}, {_count_phrase(waiting_count, 'approval gate')}, and {_count_phrase(ready_count, 'ready task')}.",
    ]
    if latest_session:
        role = str(latest_session.get("role") or "agent").replace("_", " ")
        status = str(latest_session.get("status") or "unknown").replace("_", " ")
        current_bits.append(f"The latest {role} session is {status}.")
    elif active_sessions:
        current_bits.append("Agent work is active now.")
    elif current_plan.get("summary"):
        current_bits.append(str(current_plan["summary"]).strip())
    if blocker_summary and blocker_summary.get("blocked") and blocker_summary.get("headline"):
        current_bits.append(_ensure_sentence(blocker_summary["headline"]))
    current_bits.append(
        f"The repo currently surfaces {_count_phrase(artifact_count, 'recent artifact')} and {_count_phrase(source_count, 'tracked source')}."
    )

    next_bits: list[str] = []
    session_next_tasks = []
    session_blockers = []
    if latest_session:
        completion = latest_session.get("completionSummary") or {}
        session_next_tasks = [str(item).strip() for item in (completion.get("recommended_next_tasks") or []) if str(item).strip()]
        session_blockers = [str(item).strip() for item in (completion.get("blockers") or []) if str(item).strip()]
    if pending_approvals:
        next_bits.append(f"First, clear {_count_phrase(len(pending_approvals), 'pending approval')} so the planner can resume dispatch.")
    elif session_next_tasks:
        next_bits.append(f"Next, {_compact_task_title(session_next_tasks[0]).lower()}.")
    elif next_action:
        next_bits.append(f"Next, {_compact_task_title(next_action).lower()}.")
    if auditors.get("ontology", {}).get("state") in {"stale_on_this_device", "not_hydrated"}:
        next_bits.append("Hydrate ontology data on this device before relying on graph and dashboard views.")
    if recommended_repair_task:
        next_bits.append(f"Repair priority remains {_compact_task_title(str(recommended_repair_task.get('title') or 'the repair queue')).lower()}.")
    elif session_blockers:
        next_bits.append(f"Watch the active blocker: {_compact_task_title(session_blockers[0]).lower()}.")
    elif ready_count:
        next_bits.append(f"After that, move {_count_phrase(ready_count, 'ready task')} into execution.")
    if not next_bits:
        next_bits.append("Open Planner to review the next ready task and dispatch the next work package.")

    return {
        "current": " ".join(current_bits),
        "next": " ".join(next_bits),
        "sourceSessionId": latest_session.get("sessionId") if latest_session else None,
        "sourceRole": latest_session.get("role") if latest_session else None,
        "sourceStatus": latest_session.get("status") if latest_session else None,
        "sourceUpdatedAt": latest_session.get("updatedAt") if latest_session else None,
    }


def _ontology_follow_up_summary(project: dict, tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    root = project_root(project)
    path = root / "research_plan" / "ontology_answerable_follow_up_questions.md"
    if not path.exists():
        return {
            "path": None,
            "questions": [],
            "classificationCounts": {},
        }

    content = _read(path, 40_000)
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            if current:
                questions.append(current)
            current = {"title": line[4:].strip(), "classification": None, "notes": []}
            continue
        if current is None:
            continue
        if line.startswith("- Classification:"):
            marker = line.split("`")
            if len(marker) >= 2:
                current["classification"] = marker[1].strip()
            else:
                current["classification"] = line.removeprefix("- Classification:").strip()
            continue
        if line.startswith("- Why") or line.startswith("- What would improve it:") or line.startswith("- Why expansion is needed:"):
            current["notes"].append(line.removeprefix("- ").strip())
    if current:
        questions.append(current)

    task_by_title = {str(task.get("title") or ""): task for task in (tasks or [])}
    for question in questions:
        classification = str(question.get("classification") or "").strip().lower()
        title = str(question.get("title") or "").strip()
        expected_task_title: str | None = None
        if classification == "requires_expansion":
            expected_task_title = f"Expand ontology coverage for: {title}"
        elif classification == "blocked_by_data":
            expected_task_title = f"Resolve data blocker for: {title}"
        question["expectedTaskTitle"] = expected_task_title
        linked_task = task_by_title.get(expected_task_title or "")
        question["taskPresent"] = linked_task is not None
        question["taskStatus"] = str(linked_task.get("status") or "") if linked_task else None

    classification_counts: dict[str, int] = {}
    for question in questions:
        key = str(question.get("classification") or "unknown")
        classification_counts[key] = classification_counts.get(key, 0) + 1

    return {
        "path": _rel(path, root),
        "questions": questions,
        "classificationCounts": classification_counts,
    }


LIFECYCLE_PHASES_DEFAULT: tuple[str, ...] = (
    "brief",
    "scoped",
    "source_discovery",
    "config_ready",
    "hydration_ready",
    "hydrated",
    "ontology_healthy",
    "research_active",
    "synthesis_ready",
    "closed",
)


def infer_lifecycle_phase(
    root: Path | None,
    manifest: Any,
    auditors: dict[str, Any],
    tasks: list[dict[str, Any]],
    active_sessions: list[dict[str, Any]],
) -> str:
    """Single authoritative lifecycle phase derivation.

    Encodes docs/future-spec-autonomous-platform-roadmap.md#2-lifecycle-contract
    so the closeout certificate UI, the /phase endpoint, and the command-center
    payload all read from the same source.
    """
    if not root or not root.exists():
        return "brief"

    phases = list(getattr(getattr(manifest, "lifecycle", None), "phases", None) or LIFECYCLE_PHASES_DEFAULT)

    closeout = auditors.get("closeout") or {}
    if str(closeout.get("status") or "") == "ready":
        return "closed"

    ontology = auditors.get("ontology") or {}
    ont_state = str(ontology.get("state") or ontology.get("stateClassification") or "")
    if "hydrated" in ont_state or ont_state == "hydrated_on_this_device":
        if str(ontology.get("status") or "") == "ready":
            open_tasks = [task for task in (tasks or []) if task.get("status") not in {"done", "cancelled"}]
            if not open_tasks and not active_sessions:
                return "synthesis_ready"
            return "research_active"
        return "ontology_healthy" if "ontology_healthy" in phases else "hydrated"

    integrity = auditors.get("integrity") or {}
    if str(integrity.get("status") or "") == "ready":
        return "hydration_ready"

    sources_path = root / "research_plan" / "state" / "sources.json"
    if sources_path.exists():
        try:
            raw = json.loads(sources_path.read_text(encoding="utf-8"))
            if isinstance(raw, list) and raw:
                return "source_discovery"
        except Exception:
            pass

    topics_dir = root / "topics"
    if topics_dir.is_dir() and any(topics_dir.iterdir()):
        return "scoped"

    return "brief"


def build_closeout_certificate(
    *,
    auditors: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    """Surface a top-level certificate state for the UI.

    `status` is one of: `issued`, `pending`, `would_issue_if`.
    `issued` only fires when phase==closed AND closeout auditor is ready.
    `pending` is the live blocked state with first blocker as headline.
    `would_issue_if` is the partial-ready state shown while upstream gates
    (ontology/integrity) still gate closeout — useful for the operator's
    end-of-project confidence check.
    """
    closeout = auditors.get("closeout") or {}
    closeout_status = str(closeout.get("status") or "unknown")
    blockers = [str(item) for item in (closeout.get("blockers") or []) if item]

    if closeout_status == "ready" and phase == "closed":
        return {
            "status": "issued",
            "phase": phase,
            "headline": "Closeout certificate issued.",
            "blockers": [],
        }

    if closeout_status == "blocked" and blockers:
        return {
            "status": "pending",
            "phase": phase,
            "headline": f"Closeout pending — {blockers[0]}",
            "blockers": blockers[:6],
        }

    upstream_blocked = any(
        str((auditors.get(key) or {}).get("status") or "") == "blocked"
        for key in ("session", "planner", "ontology", "integrity")
    )
    if upstream_blocked:
        unmet = [
            key
            for key in ("session", "planner", "ontology", "integrity")
            if str((auditors.get(key) or {}).get("status") or "") == "blocked"
        ]
        return {
            "status": "would_issue_if",
            "phase": phase,
            "headline": f"Would issue once {', '.join(unmet)} auditor(s) clear.",
            "blockers": [],
        }

    return {
        "status": "pending",
        "phase": phase,
        "headline": "Closeout pending — research not yet complete.",
        "blockers": [],
    }


BLOCKER_CATEGORY_FIX_SECTIONS: dict[str, str] = {
    "approval_required": "review",
    "stale_session": "runs",
    "planner_drift": "planner",
    "hydration_failure": "ontology",
    "ontology_health": "ontology",
    "integrity_gap": "integrity",
    "source_gap": "sources",
    "closeout_pending": "review",
    "clear": "",
}

BLOCKER_CATEGORY_LABELS: dict[str, str] = {
    "approval_required": "Approval required",
    "stale_session": "Stale session",
    "planner_drift": "Planner drift",
    "hydration_failure": "Hydration failure",
    "ontology_health": "Ontology health",
    "integrity_gap": "Integrity gap",
    "source_gap": "Source gap",
    "closeout_pending": "Closeout pending",
    "clear": "Clear",
}

BLOCKER_CATEGORY_SEVERITY: dict[str, str] = {
    "approval_required": "action",
    "stale_session": "critical",
    "planner_drift": "critical",
    "hydration_failure": "critical",
    "ontology_health": "warning",
    "integrity_gap": "warning",
    "source_gap": "warning",
    "closeout_pending": "info",
    "clear": "ok",
}


def _classify_blocker_category(
    *,
    pending_approvals: list[dict[str, Any]],
    reality: dict[str, Any],
    auditors: dict[str, Any],
    integrity_summary: dict[str, Any] | None,
    source_summary: dict[str, Any] | None,
) -> str:
    """Derive a canonical blocker category from auditor + reality state.

    Categories follow docs/future-spec-ui-and-control-plane.md:86. Order matters:
    operator-actionable items (approvals, stale sessions, planner drift) win over
    derived/downstream gates (ontology, integrity, closeout) so the UI never
    surfaces a downstream failure as the headline when an upstream repair is the
    real fix.
    """
    session = auditors.get("session") or {}
    planner = auditors.get("planner") or {}
    ontology = auditors.get("ontology") or {}
    integrity = auditors.get("integrity") or {}
    closeout = auditors.get("closeout") or {}

    if pending_approvals:
        return "approval_required"

    has_stale_session = bool(
        reality.get("staleRuntimeSessionCount")
        or reality.get("zombieSessionCount")
        or reality.get("runningAgentStatusDriftCount")
        or reality.get("runningAgentRoleDriftCount")
        or reality.get("runningAgentRunnerDriftCount")
    )
    if session.get("status") == "blocked" or has_stale_session:
        return "stale_session"

    has_planner_drift = bool(
        reality.get("duplicateTaskFileCount")
        or reality.get("taskSessionMismatchCount")
        or reality.get("staleAuditSessionCount")
        or reality.get("secretPolicyRoleDriftCount")
        or reality.get("roleConfigAliasDriftCount")
    )
    if planner.get("status") == "blocked" or has_planner_drift:
        return "planner_drift"

    if ontology.get("status") == "blocked":
        state_class = str(ontology.get("stateClassification") or "")
        if state_class in {"stale", "not_started", "in_progress", "unavailable"}:
            return "hydration_failure"
        return "ontology_health"

    if integrity.get("status") == "blocked":
        # Source admissibility failures route to source_gap so the UI sends
        # the operator to the sources plane where the real fix lives.
        admissibility = (integrity_summary or {}).get("sourceAdmissibilityCounts") or {}
        rejected = int(admissibility.get("rejected") or 0)
        candidate = int(admissibility.get("candidate") or 0)
        if (rejected + candidate) > 0 and int(admissibility.get("admitted") or 0) == 0:
            return "source_gap"
        return "integrity_gap"

    source_count = int((source_summary or {}).get("count") or 0)
    if source_count == 0:
        return "source_gap"

    if closeout.get("status") == "blocked":
        return "closeout_pending"

    return "clear"


def _build_blocker_summary(
    *,
    latest_audit: dict[str, Any] | None,
    reality: dict[str, Any],
    auditors: dict[str, Any],
    pending_approvals: list[dict[str, Any]] | None = None,
    integrity_summary: dict[str, Any] | None = None,
    source_summary: dict[str, Any] | None = None,
    project_slug: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    repairs: list[str] = []

    session = auditors.get("session") or {}
    planner = auditors.get("planner") or {}
    ontology = auditors.get("ontology") or {}
    integrity = auditors.get("integrity") or {}
    closeout = auditors.get("closeout") or {}

    reasons.extend(str(item) for item in (session.get("blockers") or []) if str(item) not in reasons)
    reasons.extend(str(item) for item in (planner.get("blockers") or []) if str(item) not in reasons)
    reasons.extend(str(item) for item in (ontology.get("blockers") or []) if str(item) not in reasons)
    reasons.extend(str(item) for item in (integrity.get("blockers") or []) if str(item) not in reasons)
    reasons.extend(str(item) for item in (closeout.get("blockers") or []) if str(item) not in reasons)

    if reality.get("staleRuntimeSessionCount"):
        reasons.append(f"{reality['staleRuntimeSessionCount']} stale runtime session(s) are still marked active.")
        repairs.append("Finalize or cancel stale runtime sessions before launching more work.")
    if reality.get("runningAgentStatusDriftCount"):
        reasons.append(f"{reality['runningAgentStatusDriftCount']} running-agent session status alias row(s) are still non-canonical.")
        repairs.append("Reconcile running-agent session statuses so live runtime state uses canonical lifecycle values.")
    if reality.get("runningAgentRoleDriftCount"):
        reasons.append(f"{reality['runningAgentRoleDriftCount']} running-agent session role alias row(s) are still non-canonical.")
        repairs.append("Reconcile running-agent session roles so live runtime state uses canonical agent roles.")
    if reality.get("runningAgentRunnerDriftCount"):
        reasons.append(f"{reality['runningAgentRunnerDriftCount']} running-agent session runner alias row(s) are still non-canonical.")
        repairs.append("Reconcile running-agent session runners so live runtime state uses canonical runner values.")
    if reality.get("duplicateTaskFileCount"):
        reasons.append(f"{reality['duplicateTaskFileCount']} duplicate planner task file(s) are present.")
        repairs.append("Run planner task-file reconciliation so the board has one canonical task record per task.")
    if reality.get("taskSessionMismatchCount"):
        reasons.append(f"{reality['taskSessionMismatchCount']} task(s) disagree with terminal session truth.")
        repairs.append("Reconcile task states from terminal session review and publish results.")
    if reality.get("staleAuditSessionCount"):
        reasons.append(f"{reality['staleAuditSessionCount']} terminal session audit(s) are stale or missing.")
        repairs.append("Regenerate post-run audits before autopilot advances.")
    if reality.get("secretPolicyRoleDriftCount"):
        reasons.append(f"{reality['secretPolicyRoleDriftCount']} agent secret policy role alias row(s) are still non-canonical.")
        repairs.append("Reconcile agent secret policies so secret access is keyed by canonical agent roles.")
    if reality.get("roleConfigAliasDriftCount"):
        reasons.append(f"{reality['roleConfigAliasDriftCount']} role config alias declaration(s) are still non-canonical.")
        repairs.append("Reconcile agent role config files so runner policy is keyed by canonical agent roles.")

    if ontology.get("status") == "blocked":
        repairs.append("Repair hydration or promote the correct ontology artifact before research or closeout.")
    if integrity.get("status") == "blocked":
        repairs.append("Resolve unsupported claims, inadmissible sources, or missing provenance before promotion.")
    if closeout.get("status") == "blocked":
        repairs.append("Clear active blockers and rerun closeout once ontology and integrity gates are green.")

    deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    deduped_repairs = list(dict.fromkeys(repair for repair in repairs if repair))
    blocked = bool(deduped_reasons)

    headline = "No active blocker detected."
    if blocked:
        headline = deduped_reasons[0]

    category = _classify_blocker_category(
        pending_approvals=pending_approvals or [],
        reality=reality,
        auditors=auditors,
        integrity_summary=integrity_summary,
        source_summary=source_summary,
    )
    # If nothing is reported but the classifier still picked something other
    # than `clear` (e.g. no sources yet on a fresh repo), surface it so the UI
    # never shows "Clear" while a real upstream gate is open.
    if not blocked and category != "clear":
        blocked = True
        if category == "source_gap":
            headline = "No sources have been admitted yet."
            deduped_repairs.insert(0, "Run source discovery to admit at least one source.")
        else:
            headline = BLOCKER_CATEGORY_LABELS.get(category, "Pending")

    fix_section = BLOCKER_CATEGORY_FIX_SECTIONS.get(category, "")
    fix_href = (
        f"/projects/{project_slug}/{fix_section}" if project_slug and fix_section else None
    )

    return {
        "blocked": blocked,
        "headline": headline,
        "category": category,
        "categoryLabel": BLOCKER_CATEGORY_LABELS.get(category, category),
        "severity": BLOCKER_CATEGORY_SEVERITY.get(category, "info"),
        "fixSection": fix_section or None,
        "fixHref": fix_href,
        "reasons": deduped_reasons[:6],
        "repairs": deduped_repairs[:6],
    }


def _build_repair_queue(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = ("repair", "reconcile", "resolve", "refresh", "expand")
    repair_tasks = [
        task
        for task in tasks
        if any(token in str(task.get("title") or "").lower() for token in keywords)
    ]
    status_counts: dict[str, int] = {}
    for task in repair_tasks:
        status = str(task.get("status") or "backlog")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "count": len(repair_tasks),
        "readyCount": sum(1 for task in repair_tasks if str(task.get("status") or "") == "ready"),
        "runningCount": sum(1 for task in repair_tasks if str(task.get("status") or "") == "running"),
        "tasks": [
            {
                "id": str(task.get("_id") or ""),
                "title": str(task.get("title") or ""),
                "status": str(task.get("status") or "backlog"),
                "agentRole": str(task.get("agentRole") or task.get("agent_role") or ""),
            }
            for task in repair_tasks[:10]
        ],
        "byStatus": status_counts,
    }


def _select_recommended_repair_task(
    *,
    repair_queue: dict[str, Any],
    auditors: dict[str, Any],
) -> dict[str, Any] | None:
    tasks = [task for task in (repair_queue.get("tasks") or []) if isinstance(task, dict)]
    if not tasks:
        return None

    def _first_match(*titles: str) -> dict[str, Any] | None:
        preferred = []
        fallback = []
        for task in tasks:
            title = str(task.get("title") or "")
            if title not in titles:
                continue
            if str(task.get("status") or "") == "ready":
                preferred.append(task)
            else:
                fallback.append(task)
        if preferred:
            return preferred[0]
        if fallback:
            return fallback[0]
        return None

    matches: list[tuple[str, str, tuple[str, ...]]] = [
        ("session", "Resolve control-plane drift first", ("Reconcile control-plane drift and stale sessions",)),
        ("planner", "Resolve control-plane drift first", ("Reconcile control-plane drift and stale sessions",)),
        ("ontology", "Repair ontology readiness before downstream work", ("Repair ontology readiness blockers",)),
        (
            "integrity",
            "Repair trusted-output integrity before promotion",
            (
                "Repair dataset provenance and freshness metadata",
                "Repair analysis lineage and verification metadata",
                "Repair unsupported claims and verification evidence",
                "Refresh stale sources or rerun dependent analyses",
                "Resolve failed verification runs before trusted promotion",
                "Repair reproducibility metadata for trusted artifacts",
                "Resolve inadmissible sources for trusted outputs",
            ),
        ),
        ("closeout", "Clear closeout blockers before completion", ("Resolve closeout blockers",)),
    ]

    for auditor_key, reason, titles in matches:
        auditor = auditors.get(auditor_key) or {}
        if str(auditor.get("status") or "") != "blocked":
            continue
        task = _first_match(*titles)
        if task is None:
            continue
        return {
            "auditor": auditor_key,
            "reason": reason,
            **task,
        }

    ready_tasks = [task for task in tasks if str(task.get("status") or "") == "ready"]
    fallback = ready_tasks[0] if ready_tasks else tasks[0]
    return {
        "auditor": None,
        "reason": "Next repair task currently ready on the board",
        **fallback,
    }


async def _build_live_command_center(project: dict) -> dict[str, Any]:
    planner_service, running_agent_service = _runtime_services()
    project_id = project.get("_id")
    if planner_service is None or running_agent_service is None:
        tasks = []
        approvals = []
        sessions = []
    else:
        board = await planner_service.ensure_main_board(project)
        tasks = await planner_service.list_tasks(board["_id"], project=project)
        approvals = await planner_service.list_approvals(project) if project_id else []
        sessions = (
            await running_agent_service.list_project_running_agents(str(project_id), active_only=False, limit=20)
            if project_id
            else []
        )
    active_sessions = [s for s in sessions if s.get("status") in {"running", "awaiting_approval", "awaiting_input"}]
    pending_approvals = [a for a in approvals if a.get("status") == "pending"]
    root = project_root(project)
    integrity_indexes = _project_integrity_indexes(project)
    sources = list_project_sources(project, root=root, indexes=integrity_indexes)
    skills = list_project_skills(project)
    artifacts = list_project_artifacts(project, root=root, indexes=integrity_indexes, include_previews=False)
    integrity = list_project_integrity(project, root=root, indexes=integrity_indexes)
    ranking = integrity.get("hypothesisRanking") or []
    _write_hypothesis_ranking_decisions(project, ranking)
    ontology_follow_ups = _ontology_follow_up_summary(project, tasks=tasks)
    latest_audit = read_latest_audit(root)
    recent_audits = list_recent_audits(root)
    reality = await project_reality_status(project, tasks=tasks, active_sessions=active_sessions)
    auditors = await build_auditor_statuses(
        {
            **project,
            "__controlPlaneReality": reality,
        },
        tasks=tasks,
        active_sessions=active_sessions,
    )
    try:
        from rail.manifest import load_manifest as _load_manifest

        manifest = _load_manifest(root) if (root / "rail.yaml").is_file() else None
    except Exception:
        manifest = None
    lifecycle_phase = infer_lifecycle_phase(root, manifest, auditors, tasks, active_sessions)
    closeout_certificate = build_closeout_certificate(auditors=auditors, phase=lifecycle_phase)
    blocker_summary = _build_blocker_summary(
        latest_audit=latest_audit,
        reality=reality,
        auditors=auditors,
        pending_approvals=pending_approvals,
        integrity_summary=integrity.get("summary"),
        source_summary=sources.get("summary"),
        project_slug=project.get("slug"),
    )
    repair_queue = _build_repair_queue(tasks)
    recommended_repair_task = _select_recommended_repair_task(repair_queue=repair_queue, auditors=auditors)

    task_hypothesis_overview: list[dict[str, Any]] = []
    if tasks:
        boosted_tasks = _boost_ready_tasks_with_hypotheses(project, tasks)
        for task in boosted_tasks:
            if not task.get("hypothesisLinks"):
                continue
            task_hypothesis_overview.append(
                {
                    "taskId": str(task.get("_id") or ""),
                    "title": str(task.get("title") or ""),
                    "hypothesisLinks": list(task.get("hypothesisLinks") or []),
                    "hypothesisScore": float(task.get("hypothesisScore") or 0),
                    "priorityBoost": int(task.get("_hypothesisPriorityBoost") or 0),
                }
            )

    status_counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "backlog")
        status_counts[status] = status_counts.get(status, 0) + 1

    next_action = _derive_next_action(
        pending_approvals=pending_approvals,
        active_sessions=active_sessions,
        task_counts={"total": len(tasks), "byStatus": status_counts},
    )

    goal_bundle = goal_service.load_goal_bundle(project)
    goal_summary = None
    if goal_bundle:
        goal_state = goal_bundle.get("state") or {}
        goal_summary = {
            "objective": (goal_bundle.get("contract") or {}).get("objective"),
            "phase": goal_state.get("phase"),
            "currentBlocker": goal_state.get("currentBlocker"),
            "retryBudget": goal_state.get("retryBudget"),
            "success": goal_state.get("success"),
            "dashboard": goal_state.get("dashboard"),
            "tracks": goal_state.get("tracks"),
        }
    current_plan = _summarize_current_plan(project)
    mission_brief = _build_mission_brief(
        root=root,
        current_plan=current_plan,
        next_action=next_action,
        lifecycle_phase=lifecycle_phase,
        status_counts=status_counts,
        active_sessions=active_sessions,
        pending_approvals=pending_approvals,
        recent_artifacts=artifacts["artifacts"][:6],
        source_summary=sources["summary"],
        blocker_summary=blocker_summary,
        recommended_repair_task=recommended_repair_task,
        auditors=auditors,
    )

    return {
        "project": {
            "id": project.get("_id") or project.get("slug") or "",
            "name": project.get("name"),
            "slug": project.get("slug"),
            "status": project.get("status"),
            "localRepoPath": project.get("localRepoPath"),
            "defaultBranch": project.get("defaultBranch") or "main",
        },
        "currentPlan": current_plan,
        "missionBrief": mission_brief,
        "nextAction": next_action,
        "goal": goal_summary,
        "taskCounts": {"total": len(tasks), "byStatus": status_counts},
        "plannerSnapshot": _planner_snapshot(tasks),
        "latestTruth": _latest_truth_snapshot(integrity_indexes),
        "activeSessions": active_sessions,
        "pendingApprovals": pending_approvals,
        "recentArtifacts": artifacts["artifacts"][:6],
        "sourceSummary": sources["summary"],
        "skillSummary": skills["summary"],
        "integritySummary": {
            "staleArtifactCount": integrity["summary"]["staleArtifactCount"],
            "sourceFreshnessCounts": integrity["summary"]["sourceFreshnessCounts"],
            "sourceAdmissibilityCounts": integrity["summary"]["sourceAdmissibilityCounts"],
            "agentWorkflow": integrity["agentWorkflow"],
            "hypothesisRanking": ranking,
        },
        "hypothesisTaskLinks": task_hypothesis_overview,
        "ontologyFollowUps": ontology_follow_ups,
        "auditedTruth": latest_audit,
        "recentAudits": recent_audits,
        "lifecyclePhase": lifecycle_phase,
        "closeoutCertificate": closeout_certificate,
        "currentBlocker": blocker_summary["headline"] if blocker_summary.get("blocked") else None,
        "blockerSummary": blocker_summary,
        "repairQueue": repair_queue,
        "recommendedRepairTask": recommended_repair_task,
        "projectReality": reality,
        "auditors": auditors,
        "repoHealth": {
            "hasLocalRepo": bool(project.get("localRepoPath")),
            "hasRailYaml": bool(project.get("localRepoPath") and (Path(project["localRepoPath"]) / "rail.yaml").exists()),
            "hasResearchPlan": bool(project.get("localRepoPath") and (Path(project["localRepoPath"]) / "research_plan").exists()),
        },
        "snapshot": {
            "loaded": False,
            "path": CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH,
            "generatedAt": None,
            "version": CONTROL_PLANE_SNAPSHOT_VERSION,
        },
    }


async def build_command_center(project: dict, *, prefer_snapshot: bool = True) -> dict[str, Any]:
    planner_service, running_agent_service = _runtime_services()
    project_id = project.get("_id")
    if planner_service is None or running_agent_service is None:
        pending_approvals: list[dict[str, Any]] = []
        active_sessions: list[dict[str, Any]] = []
    else:
        pending_approvals = (
            [a for a in await planner_service.list_approvals(project) if a.get("status") == "pending"]
            if project_id
            else []
        )
        sessions = (
            await running_agent_service.list_project_running_agents(str(project_id), active_only=False, limit=20)
            if project_id
            else []
        )
        active_sessions = [s for s in sessions if s.get("status") in {"running", "awaiting_approval", "awaiting_input"}]

    if prefer_snapshot:
        snapshot = read_control_plane_snapshot(project)
        if snapshot is not None:
            return _command_center_from_snapshot(
                project,
                snapshot,
                active_sessions=active_sessions,
                pending_approvals=pending_approvals,
            )

    return await _build_live_command_center(project)


def build_launch_preview(project: dict, payload: dict[str, Any]) -> dict[str, Any]:
    selected = payload.get("workflowPresets") or []
    if not selected:
        selected = ["feasibility_memo", "source_inventory"]
    presets = [WORKFLOW_PRESETS[key] | {"key": key} for key in selected if key in WORKFLOW_PRESETS]
    if not presets:
        presets = [WORKFLOW_PRESETS["feasibility_memo"] | {"key": "feasibility_memo"}]

    question = str(payload.get("researchQuestion") or "").strip()
    audience = str(payload.get("audience") or "project stakeholders").strip()
    constraints = str(payload.get("dataConstraints") or "").strip()
    deliverables = payload.get("deliverables") or [p["label"] for p in presets]
    notes = str(payload.get("notes") or "").strip()
    public_only = bool(payload.get("publicOnly", True))
    approval_before_writes = bool(payload.get("approvalBeforeWrites", True))
    use_sub_agents = bool(payload.get("useSubAgents", True))
    citation_strictness = str(payload.get("citationStrictness") or "strict")

    skill_names = sorted({skill for preset in presets for skill in preset["skills"]})
    outputs = sorted({output for preset in presets for output in preset["outputs"]})
    tasks = []
    for idx, preset in enumerate(presets, start=1):
        acceptance_criteria = [
            "Findings are saved to the expected repo paths",
            "Sources are cited for factual claims",
            "Open questions and caveats are recorded",
        ]
        if preset["role"] == "research":
            acceptance_criteria.append("Facts, interpretations, and open questions are separated explicitly.")
        elif preset["role"] == "data":
            acceptance_criteria.append("Datasets preserve provenance and freshness metadata before handoff.")
        elif preset["role"] == "coding":
            acceptance_criteria.append("Analysis outputs declare inputs, scripts, and verification commands.")
        elif preset["role"] == "artifact":
            acceptance_criteria.append("Artifacts preserve evidence links and avoid unsupported trusted narratives.")
            acceptance_criteria.append("Closeout includes ranked hypotheses, falsifiers, and next data pulls.")
        elif preset["role"] == "health":
            acceptance_criteria.append("Missing evidence, stale sources, and reproducibility gaps are reported explicitly.")
        tasks.append(
            {
                "title": f"{preset['label']}: {question[:80] or project.get('name', 'Research Project')}",
                "description": "\n".join(
                    part
                    for part in [
                        f"Research question: {question or 'TBD'}",
                        f"Audience: {audience}",
                        f"Data constraints: {constraints}" if constraints else "",
                        f"Public data only: {public_only}",
                        f"Citation strictness: {citation_strictness}",
                        f"Use sub-agents: {use_sub_agents}",
                        f"Notes: {notes}" if notes else "",
                    ]
                    if part
                ),
                "agentRole": preset["role"],
                "status": "awaiting_approval" if approval_before_writes else "ready",
                "repoPaths": preset["outputs"],
                "acceptanceCriteria": acceptance_criteria,
            }
        )

    if not any(task["agentRole"] == "artifact" and "Meta-synthesis" in task["title"] for task in tasks):
        tasks.append(
            {
                "title": f"Meta-synthesis closeout: {question[:80] or project.get('name', 'Research Project')}",
                "description": "\n".join(
                    part
                    for part in [
                        f"Research question: {question or 'TBD'}",
                        "Build a closeout synthesis grounded in ranked hypotheses and critic blockers.",
                        "Use artifacts/meta_synthesis.md as the output structure.",
                    ]
                    if part
                ),
                "agentRole": "artifact",
                "status": "awaiting_approval" if approval_before_writes else "ready",
                "repoPaths": ["artifacts/meta_synthesis.md", "research_plan/state/hypotheses.json", "research_plan/state/conflicts.json"],
                "acceptanceCriteria": [
                    "Meta-synthesis includes ranked hypotheses and computed score context.",
                    "Evidence table links hypotheses to claims and sources.",
                    "Falsifiers and unresolved conflicts are clearly surfaced.",
                    "Next data pulls are documented with linked hypotheses.",
                ],
            }
        )

    risks = [
        "Source availability may limit automation",
        "Causal claims require identification review before policy conclusions",
    ]
    if public_only:
        risks.append("Non-public or subscription-only data will be excluded unless manually supplied")

    return {
        "objective": question or f"Advance {project.get('name', 'this research project')}",
        "audience": audience,
        "deliverables": deliverables,
        "workflowPresets": [p["key"] for p in presets],
        "agentWorkBreakdown": tasks,
        "skillsToUse": skill_names,
        "expectedRepoOutputs": outputs,
        "requiredApprovals": ["Create planner tasks", "Start write-capable agent runs"] if approval_before_writes else ["Start write-capable agent runs"],
        "knownRisks": risks,
        "missingInputs": [] if question else ["Research question"],
    }


async def approve_launch_preview(project: dict, payload: dict[str, Any]) -> dict[str, Any]:
    preview = build_launch_preview(project, payload)
    planner_service, _ = _runtime_services()
    root = project_root(project)
    if planner_service is None:
        tasks_dir = root / "research_plan" / "tasks"
        approvals_dir = root / "research_plan" / "approvals"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        approvals_dir.mkdir(parents=True, exist_ok=True)
        created = []
        for idx, task in enumerate(preview["agentWorkBreakdown"], start=1):
            task_id = f"task-{idx}"
            created_task = {
                "_id": task_id,
                "title": task["title"],
                "description": task["description"],
                "status": task["status"],
                "agentRole": task["agentRole"],
                "repoPaths": task["repoPaths"],
                "acceptanceCriteria": task["acceptanceCriteria"],
                "approvalState": "pending" if task["status"] == "awaiting_approval" else None,
            }
            created.append(created_task)
            _write(
                tasks_dir / f"{task_id}.md",
                "\n".join(
                    [
                        f"# {task['title']}",
                        "",
                        task["description"],
                        "",
                        f"- status: {task['status']}",
                        f"- role: {task['agentRole']}",
                    ]
                ) + "\n",
            )
        approval_id = "approval-local-launch"
        _write(
            approvals_dir / f"{approval_id}.md",
            json.dumps({"objective": preview["objective"], "tasks": [t["_id"] for t in created]}, indent=2) + "\n",
        )
        return {"preview": preview, "tasks": created, "approvalId": approval_id}

    board = await planner_service.ensure_main_board(project)
    created = []
    for task in preview["agentWorkBreakdown"]:
        created.append(
            await planner_service.create_task(
                project=project,
                board_id=board["_id"],
                title=task["title"],
                description=task["description"],
                status=task["status"],
                agent_role=task["agentRole"],
                repo_paths=task["repoPaths"],
                acceptance_criteria=task["acceptanceCriteria"],
                approval_state="pending" if task["status"] == "awaiting_approval" else None,
            )
        )
    approval_id = await planner_service.create_approval(
        project=project,
        task_id=None,
        agent_session_id=None,
        approval_type="research_launch",
        requested_by_role="planner",
        resolution_note=json.dumps({"objective": preview["objective"], "tasks": [t["_id"] for t in created]}, indent=2),
    )
    await planner_service.sync_planner_files(project, board)
    return {"preview": preview, "tasks": created, "approvalId": approval_id}


def extract_decisions_from_session_detail(detail: dict[str, Any]) -> dict[str, Any]:
    text_parts = []
    for key in ("summary", "todos", "verification"):
        node = (detail.get("reviewFiles") or {}).get(key) or {}
        if node.get("content"):
            text_parts.append(str(node["content"]))
    combined = "\n".join(text_parts)
    assumptions = re.findall(r"(?im)^[-*]\s*(?:assumption|assume)[s:]?\s*(.+)$", combined)
    blockers = re.findall(r"(?im)^[-*]\s*(?:blocker|blocked|risk)[s:]?\s*(.+)$", combined)
    questions = re.findall(r"(?im)^[-*]\s*(?:question|open question)[s:]?\s*(.+)$", combined)
    return {
        "assumptions": assumptions[:12],
        "blockers": blockers[:12],
        "openQuestions": questions[:12],
    }
