from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.services import planner_service, running_agent_service


TEXT_PREVIEW_LIMIT = 80_000
TABLE_PREVIEW_ROWS = 25


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
}


def project_root(project: dict) -> Path:
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise ValueError("Project does not have a localRepoPath configured")
    return root


def _read(path: Path, limit: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit] if limit else text


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


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


def list_project_sources(project: dict) -> dict[str, Any]:
    root = project_root(project)
    rows: dict[str, dict[str, Any]] = {}

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

    notes_path = root / "topics" / "source_notes.md"
    source_notes = _read(notes_path, 40_000) if notes_path.exists() else ""
    status_counts: dict[str, int] = {}
    for row in rows.values():
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    return {
        "sources": list(rows.values()),
        "summary": {
            "count": len(rows),
            "statusCounts": status_counts,
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


def list_project_artifacts(project: dict) -> dict[str, Any]:
    root = project_root(project)
    artifact_root = root / "artifacts"
    artifacts: list[dict[str, Any]] = []
    if artifact_root.is_dir():
        for path in sorted(p for p in artifact_root.rglob("*") if p.is_file()):
            stat = path.stat()
            artifacts.append(
                {
                    "name": path.name,
                    "path": _rel(path, root),
                    "type": _artifact_type(path),
                    "sizeBytes": stat.st_size,
                    "modifiedAt": int(stat.st_mtime * 1000),
                    "previewable": _artifact_type(path) in {"markdown", "table", "structured", "image", "html"},
                    "preview": _preview_artifact(path),
                }
            )
    type_counts: dict[str, int] = {}
    for artifact in artifacts:
        type_counts[artifact["type"]] = type_counts.get(artifact["type"], 0) + 1
    return {"artifacts": artifacts, "summary": {"count": len(artifacts), "typeCounts": type_counts}}


def _summarize_current_plan(project: dict) -> dict[str, Any]:
    root = planner_service.project_root_from_record(project)
    if root is None:
        return {"path": None, "summary": ""}
    path = root / "research_plan" / "current_plan.md"
    if not path.exists():
        return {"path": None, "summary": ""}
    content = _read(path, 20_000)
    return {"path": _rel(path, root), "summary": _summary_from_markdown(content), "content": content}


async def build_command_center(project: dict) -> dict[str, Any]:
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    approvals = await planner_service.list_approvals(project)
    sessions = await running_agent_service.list_project_running_agents(project["_id"], active_only=False, limit=20)
    active_sessions = [s for s in sessions if s.get("status") in {"running", "awaiting_approval", "awaiting_input"}]
    pending_approvals = [a for a in approvals if a.get("status") == "pending"]
    sources = list_project_sources(project)
    skills = list_project_skills(project)
    artifacts = list_project_artifacts(project)

    status_counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "backlog")
        status_counts[status] = status_counts.get(status, 0) + 1

    if pending_approvals:
        next_action = "Review pending approvals"
    elif active_sessions:
        next_action = "Monitor active agent sessions"
    elif tasks:
        next_action = "Select the next ready task or launch a research workflow"
    else:
        next_action = "Start a research workflow"

    return {
        "project": {
            "id": project["_id"],
            "name": project.get("name"),
            "slug": project.get("slug"),
            "status": project.get("status"),
            "localRepoPath": project.get("localRepoPath"),
            "defaultBranch": project.get("defaultBranch") or "main",
        },
        "currentPlan": _summarize_current_plan(project),
        "nextAction": next_action,
        "taskCounts": {"total": len(tasks), "byStatus": status_counts},
        "activeSessions": active_sessions,
        "pendingApprovals": pending_approvals,
        "recentArtifacts": artifacts["artifacts"][:6],
        "sourceSummary": sources["summary"],
        "skillSummary": skills["summary"],
        "repoHealth": {
            "hasLocalRepo": bool(project.get("localRepoPath")),
            "hasRailYaml": bool(project.get("localRepoPath") and (Path(project["localRepoPath"]) / "rail.yaml").exists()),
            "hasResearchPlan": bool(project.get("localRepoPath") and (Path(project["localRepoPath"]) / "research_plan").exists()),
        },
    }


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
                "acceptanceCriteria": [
                    "Findings are saved to the expected repo paths",
                    "Sources are cited for factual claims",
                    "Open questions and caveats are recorded",
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
