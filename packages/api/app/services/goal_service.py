from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from rail.manifest import load_manifest


GOAL_DIR = Path(".rail") / "goal"
GOAL_MD = "goal.md"
GOAL_STATE_JSON = "goal_state.json"
GOAL_LESSONS_JSON = "goal_lessons.json"
GOAL_BLOCKERS_JSON = "goal_blockers.json"
GOAL_DECISIONS_JSON = "goal_decisions.json"

GOAL_PHASES: tuple[str, ...] = (
    "declared",
    "scoped",
    "bootstrapped",
    "acquiring_sources",
    "building_pipelines",
    "hydrating",
    "researching",
    "artifacting",
    "verifying",
    "closeout",
    "completed",
    "blocked",
    "needs_human",
)

FAILURE_CLASSES: tuple[str, ...] = (
    "setup_failure",
    "source_access_failure",
    "verification_failure",
    "publish_failure",
    "planner_drift",
    "audit_drift",
    "ontology_invalid",
    "integrity_invalid",
    "platform_bug",
)

HUMAN_DECISION_KINDS = {
    "scope_decision",
    "access_credential_decision",
    "trust_acceptance_decision",
}

STATE_MACHINE: dict[str, dict[str, Any]] = {
    "declared": {
        "entryCriteria": ["goal contract persisted in repo state"],
        "exitCriteria": ["objective, success criteria, spend, and escalation policy are present"],
        "allowedRepairTasks": ["complete missing contract fields"],
        "disallowedTasks": ["launch worker execution"],
    },
    "scoped": {
        "entryCriteria": ["goal contract is complete enough to scope work"],
        "exitCriteria": ["scope, source path, and success criteria are interpretable"],
        "allowedRepairTasks": ["clarify scope", "downgrade scope", "record assumptions"],
        "disallowedTasks": ["mark goal complete"],
    },
    "bootstrapped": {
        "entryCriteria": ["preflight checks started"],
        "exitCriteria": ["repo, manifest, planner truth, integrity ledger, runners, and source readiness checked"],
        "allowedRepairTasks": ["fix manifest", "fix repo linkage", "repair planner drift"],
        "disallowedTasks": ["launch domain research while preflight is failing"],
    },
    "acquiring_sources": {
        "entryCriteria": ["goal passed preflight but lacks admissible source coverage"],
        "exitCriteria": ["at least one admissible source path exists"],
        "allowedRepairTasks": ["find replacement sources", "classify source readiness", "narrow scope"],
        "disallowedTasks": ["trusted hydration from placeholder sources"],
    },
    "building_pipelines": {
        "entryCriteria": ["sources exist but hydration path is not executable"],
        "exitCriteria": ["default pipeline and source configs are runnable"],
        "allowedRepairTasks": ["repair pipeline configs", "attach sources", "register transforms"],
        "disallowedTasks": ["research claims without data path"],
    },
    "hydrating": {
        "entryCriteria": ["pipeline exists and hydration is required"],
        "exitCriteria": ["hydrated ontology or dataset artifacts are populated and registered"],
        "allowedRepairTasks": ["rerun hydration", "repair ontology pointers", "repair publish metadata"],
        "disallowedTasks": ["final synthesis before populated artifacts exist"],
    },
    "researching": {
        "entryCriteria": ["hydrated or otherwise admissible evidence path exists"],
        "exitCriteria": ["claims, notes, or datasets materially advance the goal"],
        "allowedRepairTasks": ["collect evidence", "refine claims", "branch into sub-questions"],
        "disallowedTasks": ["ignore blocking platform repair"],
    },
    "artifacting": {
        "entryCriteria": ["research evidence exists and artifacts are being produced"],
        "exitCriteria": ["final artifacts are present with lineage stubs"],
        "allowedRepairTasks": ["write reports", "publish analyses", "repair artifact registry"],
        "disallowedTasks": ["mark complete without provenance"],
    },
    "verifying": {
        "entryCriteria": ["artifacts or claims exist and need verification"],
        "exitCriteria": ["verification, provenance, and integrity gates pass"],
        "allowedRepairTasks": ["rerun verification", "repair evidence", "downgrade unsupported claims"],
        "disallowedTasks": ["trusted promotion while verification is blocked"],
    },
    "closeout": {
        "entryCriteria": ["success criteria are nearly satisfied and closeout is in progress"],
        "exitCriteria": ["closeout auditor is green and no blocking repairs remain"],
        "allowedRepairTasks": ["close remaining blockers", "record follow-ups", "issue certificate"],
        "disallowedTasks": ["new speculative research"],
    },
    "completed": {
        "entryCriteria": ["all success, provenance, and closeout requirements are satisfied"],
        "exitCriteria": ["none"],
        "allowedRepairTasks": [],
        "disallowedTasks": ["resume autonomous execution without a new goal"],
    },
    "blocked": {
        "entryCriteria": ["autonomy cannot continue but no precise human decision is required yet"],
        "exitCriteria": ["repair path is available or blocker is cleared"],
        "allowedRepairTasks": ["platform repair", "scope downgrade", "source substitution"],
        "disallowedTasks": ["pretend the goal is progressing"],
    },
    "needs_human": {
        "entryCriteria": ["autonomy requires a concrete human decision"],
        "exitCriteria": ["user provides one clear scope, access, or trust decision"],
        "allowedRepairTasks": ["surface one precise question"],
        "disallowedTasks": ["ask vague open-ended questions"],
    },
}


def _project_root(project: dict[str, Any]) -> Path:
    local_repo_path = str(project.get("localRepoPath") or "").strip()
    if not local_repo_path:
        raise ValueError("Project does not have a localRepoPath configured")
    return Path(local_repo_path).resolve()


def _goal_root(project: dict[str, Any]) -> Path:
    return _project_root(project) / GOAL_DIR


def _goal_path(project: dict[str, Any], filename: str) -> Path:
    return _goal_root(project) / filename


def _now() -> int:
    return int(time.time() * 1000)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ensure_phase(phase: str) -> str:
    return phase if phase in GOAL_PHASES else "declared"


def _ensure_failure_class(value: str) -> str:
    return value if value in FAILURE_CLASSES else "platform_bug"


def _default_goal_contract(project: dict[str, Any]) -> dict[str, Any]:
    objective = str(project.get("description") or "").strip() or f"Complete project: {project.get('name') or project.get('slug') or 'Untitled project'}"
    return {
        "goalId": f"goal-{uuid.uuid4().hex[:12]}",
        "objective": objective,
        "successCriteria": [
            "admissible sources are registered and classified",
            "required data or ontology artifacts are hydrated and available",
            "final artifacts contain provenance-backed claims",
            "verification and closeout gates pass",
        ],
        "allowedSpend": {
            "timeMinutes": None,
            "tokens": None,
            "apiCostUsd": None,
            "retries": 3,
        },
        "requiredEvidence": [
            "source registry entries",
            "hydration or dataset artifact path",
            "claims or artifact lineage proving provenance",
            "passing closeout or verification evidence",
        ],
        "forbiddenShortcuts": [
            "do not promote placeholder ontology or source configs as trusted",
            "do not mark complete from task activity alone",
            "do not bypass provenance or verification requirements",
        ],
        "escalationPolicy": [
            "pause only for scope decisions",
            "pause only for access or credential decisions",
            "pause only for trust or acceptance decisions",
        ],
        "createdAt": _now(),
        "updatedAt": _now(),
        "mode": "goal",
    }


def _render_goal_md(contract: dict[str, Any], state: dict[str, Any]) -> str:
    lines = [
        "# Goal",
        "",
        f"- goal_id: `{contract.get('goalId', '')}`",
        f"- phase: `{state.get('phase', 'declared')}`",
        f"- objective: {contract.get('objective', '')}",
        "",
        "## Success Criteria",
        "",
    ]
    for item in contract.get("successCriteria") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Allowed Spend", ""])
    allowed_spend = contract.get("allowedSpend") or {}
    for key in ("timeMinutes", "tokens", "apiCostUsd", "retries"):
        lines.append(f"- {key}: `{allowed_spend.get(key)}`")
    lines.extend(["", "## Required Evidence", ""])
    for item in contract.get("requiredEvidence") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Forbidden Shortcuts", ""])
    for item in contract.get("forbiddenShortcuts") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Escalation Policy", ""])
    for item in contract.get("escalationPolicy") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Runtime", ""])
    lines.append(f"- current_blocker: {state.get('currentBlocker') or 'none'}")
    lines.append(f"- autonomy_confidence: `{state.get('autonomyConfidence')}`")
    return "\n".join(lines) + "\n"


def _initial_state(contract: dict[str, Any]) -> dict[str, Any]:
    retries = int((contract.get("allowedSpend") or {}).get("retries") or 0)
    phase = "scoped" if contract.get("objective") and contract.get("successCriteria") else "declared"
    return {
        "goalId": contract["goalId"],
        "contract": contract,
        "phase": phase,
        "phaseHistory": [{"phase": phase, "at": _now(), "reason": "goal contract created"}],
        "status": "active",
        "currentBlocker": None,
        "activeFailure": None,
        "lastMeaningfulProgressAt": _now(),
        "autonomyConfidence": 0.55,
        "preflight": {
            "passed": False,
            "checks": [],
            "lastRunAt": None,
        },
        "tracks": {
            "research": {"status": "pending", "blocker": None},
            "platformRepair": {"status": "clear", "blocker": None},
        },
        "runCounts": {"successful": 0, "failed": 0},
        "retryBudget": {"max": retries, "used": 0, "remaining": max(retries, 0)},
        "success": {
            "criteriaSatisfied": 0,
            "criteriaTotal": len(contract.get("successCriteria") or []),
            "percent": 0.0,
            "criteria": [],
        },
        "dashboard": {
            "currentPhase": phase,
            "currentBlocker": None,
            "retryBudgetUsed": 0,
            "successfulRuns": 0,
            "failedRuns": 0,
            "criteriaSatisfiedPercent": 0.0,
            "lastMeaningfulProgressAt": _now(),
            "autonomyConfidence": 0.55,
        },
        "updatedAt": _now(),
    }


def _default_list_payload() -> list[dict[str, Any]]:
    return []


def _phase_rank(phase: str) -> int:
    try:
        return GOAL_PHASES.index(phase)
    except ValueError:
        return 0


def _upsert_phase_history(state: dict[str, Any], phase: str, reason: str) -> None:
    history = list(state.get("phaseHistory") or [])
    if history and history[-1].get("phase") == phase:
        history[-1]["reason"] = reason
        history[-1]["at"] = _now()
    else:
        history.append({"phase": phase, "at": _now(), "reason": reason})
    state["phaseHistory"] = history


def _set_phase(state: dict[str, Any], phase: str, reason: str) -> None:
    phase = _ensure_phase(phase)
    current = _ensure_phase(str(state.get("phase") or "declared"))
    if phase not in {"blocked", "needs_human", "completed"}:
        if current in {"blocked", "needs_human"} and _phase_rank(phase) < _phase_rank("bootstrapped"):
            phase = "bootstrapped"
        elif current not in {"blocked", "needs_human", "completed"} and _phase_rank(phase) < _phase_rank(current):
            phase = current
    state["phase"] = phase
    state["dashboard"] = state.get("dashboard") or {}
    state["dashboard"]["currentPhase"] = phase
    _upsert_phase_history(state, phase, reason)


def _state_machine_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "phases": [{"name": phase, **STATE_MACHINE[phase]} for phase in GOAL_PHASES],
    }


def create_goal_contract(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    contract = _default_goal_contract(project)
    contract.update(
        {
            "objective": str(payload.get("objective") or contract["objective"]).strip(),
            "successCriteria": list(payload.get("successCriteria") or contract["successCriteria"]),
            "requiredEvidence": list(payload.get("requiredEvidence") or contract["requiredEvidence"]),
            "forbiddenShortcuts": list(payload.get("forbiddenShortcuts") or contract["forbiddenShortcuts"]),
            "escalationPolicy": list(payload.get("escalationPolicy") or contract["escalationPolicy"]),
            "allowedSpend": {
                **contract["allowedSpend"],
                **dict(payload.get("allowedSpend") or {}),
            },
            "updatedAt": _now(),
        }
    )
    state = _initial_state(contract)
    root = _goal_root(project)
    root.mkdir(parents=True, exist_ok=True)
    _write_markdown(root / GOAL_MD, _render_goal_md(contract, state))
    _write_json(root / GOAL_STATE_JSON, state)
    _write_json(root / GOAL_LESSONS_JSON, _default_list_payload())
    _write_json(root / GOAL_BLOCKERS_JSON, _default_list_payload())
    _write_json(root / GOAL_DECISIONS_JSON, _default_list_payload())
    return load_goal_bundle(project)


def ensure_goal_contract(project: dict[str, Any]) -> dict[str, Any]:
    state_path = _goal_path(project, GOAL_STATE_JSON)
    if state_path.exists():
        return load_goal_bundle(project)
    return create_goal_contract(project, {})


def load_goal_bundle(project: dict[str, Any]) -> dict[str, Any]:
    root = _goal_root(project)
    if not root.exists():
        return {}
    default_contract = _default_goal_contract(project)
    state = _initial_state(default_contract)
    state = {**state, **_read_json(root / GOAL_STATE_JSON, state)}
    contract = {
        **default_contract,
        **dict(state.get("contract") or {}),
    }
    goal_md = (root / GOAL_MD).read_text(encoding="utf-8") if (root / GOAL_MD).exists() else _render_goal_md(contract, state)
    lessons = _read_json(root / GOAL_LESSONS_JSON, _default_list_payload())
    blockers = _read_json(root / GOAL_BLOCKERS_JSON, _default_list_payload())
    decisions = _read_json(root / GOAL_DECISIONS_JSON, _default_list_payload())
    contract_payload = dict(contract)
    contract_path = root / GOAL_MD
    if contract_path.exists():
        contract_payload["markdownPath"] = str(contract_path)
    return {
        "contract": contract_payload,
        "state": state,
        "lessons": lessons if isinstance(lessons, list) else [],
        "blockers": blockers if isinstance(blockers, list) else [],
        "decisions": decisions if isinstance(decisions, list) else [],
        "goalMarkdown": goal_md,
        "files": {
            "goalMd": str(root / GOAL_MD),
            "goalState": str(root / GOAL_STATE_JSON),
            "goalLessons": str(root / GOAL_LESSONS_JSON),
            "goalBlockers": str(root / GOAL_BLOCKERS_JSON),
            "goalDecisions": str(root / GOAL_DECISIONS_JSON),
        },
        "stateMachine": _state_machine_payload(),
    }


def _write_bundle(project: dict[str, Any], contract: dict[str, Any], state: dict[str, Any], lessons: list[dict[str, Any]], blockers: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    root = _goal_root(project)
    root.mkdir(parents=True, exist_ok=True)
    contract["updatedAt"] = _now()
    state["contract"] = contract
    state["updatedAt"] = _now()
    _write_markdown(root / GOAL_MD, _render_goal_md(contract, state))
    _write_json(root / GOAL_STATE_JSON, state)
    _write_json(root / GOAL_LESSONS_JSON, lessons)
    _write_json(root / GOAL_BLOCKERS_JSON, blockers)
    _write_json(root / GOAL_DECISIONS_JSON, decisions)
    return load_goal_bundle(project)


def _goal_context(project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    bundle = ensure_goal_contract(project)
    return (
        bundle.get("contract") or _default_goal_contract(project),
        bundle.get("state") or _initial_state(_default_goal_contract(project)),
        list(bundle.get("lessons") or []),
        list(bundle.get("blockers") or []),
        list(bundle.get("decisions") or []),
    )


def evaluate_preflight(project: dict[str, Any], *, reality: dict[str, Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    root = _project_root(project)
    checks.append(
        {
            "name": "validate_repo_and_manifest",
            "passed": root.exists() and (root / "rail.yaml").exists(),
            "detail": "Repo root and rail.yaml must exist.",
        }
    )
    manifest = None
    manifest_ok = False
    manifest_error = None
    try:
        manifest = load_manifest(root)
        manifest_ok = True
    except Exception as exc:
        manifest_error = str(exc)
    checks.append(
        {
            "name": "validate_manifest_schema",
            "passed": manifest_ok,
            "detail": manifest_error or "Manifest loaded.",
        }
    )
    checks.append(
        {
            "name": "validate_project_metadata_and_github_linkage",
            "passed": bool(str(project.get("name") or "").strip()) and bool(str(project.get("slug") or "").strip()),
            "detail": "Project name and slug must be present.",
        }
    )
    reality = reality or {}
    planner_truth_ok = not any(
        bool(reality.get(key))
        for key in (
            "duplicateTaskFileCount",
            "taskSessionMismatchCount",
            "staleAuditSessionCount",
            "staleRuntimeSessionCount",
            "runningAgentStatusDriftCount",
            "runningAgentRoleDriftCount",
            "runningAgentRunnerDriftCount",
        )
    )
    checks.append(
        {
            "name": "validate_planner_task_truth",
            "passed": planner_truth_ok,
            "detail": "Planner and runtime drift must be cleared before autonomous launch.",
        }
    )
    integrity_root = root / "research_plan" / "state"
    checks.append(
        {
            "name": "validate_integrity_ledger_schema_compatibility",
            "passed": integrity_root.exists(),
            "detail": "research_plan/state must exist for durable integrity tracking.",
        }
    )
    checks.append(
        {
            "name": "validate_runner_availability",
            "passed": True,
            "detail": "Runners are assumed available when the API process is live.",
        }
    )
    source_ready = (root / ".ontology" / "sources").exists() or (root / "research_plan" / "state" / "sources.json").exists()
    checks.append(
        {
            "name": "validate_source_readiness_classification",
            "passed": source_ready,
            "detail": "At least one source registry path should exist before full autonomy.",
        }
    )
    passed = all(bool(item["passed"]) for item in checks)
    current_blocker = None
    for item in checks:
        if not item["passed"]:
            current_blocker = item["detail"]
            break
    return {
        "passed": passed,
        "checks": checks,
        "currentBlocker": current_blocker,
        "lastRunAt": _now(),
        "manifestLoaded": manifest_ok,
    }


def _criterion_statuses(
    contract: dict[str, Any],
    *,
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any],
    reality: dict[str, Any],
    active_sessions: list[dict[str, Any]],
    artifacts_present: bool,
    sources_present: bool,
) -> list[dict[str, Any]]:
    unfinished = [task for task in tasks if task.get("status") not in {"done", "cancelled"}]
    ontology_ready = str((auditors.get("ontology") or {}).get("status") or "") == "ready"
    integrity_ready = str((auditors.get("integrity") or {}).get("status") or "") == "ready"
    closeout_ready = str((auditors.get("closeout") or {}).get("status") or "") == "ready"
    statuses: list[dict[str, Any]] = []
    for raw in contract.get("successCriteria") or []:
        criterion = str(raw).strip()
        lower = criterion.lower()
        satisfied = False
        reason = "Not yet satisfied."
        if "source" in lower or "dataset" in lower:
            satisfied = sources_present
            reason = "Sources are registered." if satisfied else "No durable source registry path exists yet."
        elif "hydrat" in lower or "ontology" in lower:
            satisfied = ontology_ready
            reason = "Ontology auditor is ready." if satisfied else "Ontology readiness has not passed yet."
        elif "artifact" in lower or "report" in lower or "final" in lower:
            satisfied = artifacts_present
            reason = "Final artifacts exist." if satisfied else "Final artifacts are missing."
        elif "provenance" in lower or "claim" in lower or "verification" in lower:
            satisfied = integrity_ready
            reason = "Integrity gate is ready." if satisfied else "Integrity gate is still blocked."
        elif "closeout" in lower or "audit" in lower:
            satisfied = closeout_ready and not unfinished and not active_sessions and not any(bool(reality.get(key)) for key in ("duplicateTaskFileCount", "taskSessionMismatchCount"))
            reason = "Closeout and control-plane truth are ready." if satisfied else "Closeout or control-plane truth is still blocked."
        else:
            satisfied = closeout_ready
            reason = "Closeout is ready." if satisfied else "Waiting for closeout readiness."
        statuses.append({"criterion": criterion, "satisfied": satisfied, "reason": reason})
    return statuses


def _derive_phase(
    *,
    state: dict[str, Any],
    preflight: dict[str, Any],
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any],
    active_sessions: list[dict[str, Any]],
    reality: dict[str, Any],
    sources_present: bool,
    artifacts_present: bool,
) -> tuple[str, str]:
    if str(state.get("status") or "") == "completed":
        return "completed", "Goal already completed."
    if not bool(preflight.get("passed")):
        return "blocked", str(preflight.get("currentBlocker") or "Goal preflight is still failing.")
    pending_approvals = any(task.get("approvalState") == "pending" for task in tasks)
    if pending_approvals:
        return "needs_human", "An approval decision is required before autonomy can continue."
    if any(
        bool(reality.get(key))
        for key in (
            "duplicateTaskFileCount",
            "taskSessionMismatchCount",
            "staleAuditSessionCount",
            "staleRuntimeSessionCount",
            "runningAgentStatusDriftCount",
            "runningAgentRoleDriftCount",
            "runningAgentRunnerDriftCount",
        )
    ):
        return "blocked", "Platform repair is blocking autonomous progress."
    closeout = auditors.get("closeout") or {}
    integrity = auditors.get("integrity") or {}
    ontology = auditors.get("ontology") or {}
    if str(closeout.get("status") or "") == "ready":
        return "completed", "Closeout auditor is ready."
    if not sources_present:
        return "acquiring_sources", "Admissible source path is still being established."
    ontology_state = str(ontology.get("stateClassification") or ontology.get("state") or "")
    ontology_status = str(ontology.get("status") or "")
    if ontology_status == "blocked" and ontology_state in {"not_started", "stale", "in_progress", "unavailable", ""}:
        return "building_pipelines", "Source and pipeline coverage still need repair before hydration."
    if ontology_status == "blocked":
        return "hydrating", "Hydration artifacts exist but ontology readiness is still blocked."
    if ontology_status == "ready" and not artifacts_present:
        if active_sessions or any(task.get("agentRole") in {"research", "data", "planner"} and task.get("status") not in {"done", "cancelled"} for task in tasks):
            return "researching", "Research work is active against an admissible data path."
        return "artifacting", "The project is ready to turn research into durable artifacts."
    if ontology_status == "ready" and artifacts_present and str(integrity.get("status") or "") == "blocked":
        return "verifying", "Artifacts exist and integrity repair is still in progress."
    if ontology_status == "ready" and artifacts_present:
        return "closeout", "Artifacts are present and the goal is approaching closeout."
    return max("bootstrapped", str(state.get("phase") or "declared"), key=_phase_rank), "Goal passed initial setup and is awaiting the next durable step."


def _confidence_for_state(phase: str, *, current_blocker: str | None, failed_runs: int, successful_runs: int, progress_percent: float) -> float:
    if phase == "completed":
        return 1.0
    if phase == "needs_human":
        return 0.2
    if phase == "blocked":
        return 0.15
    base = {
        "declared": 0.3,
        "scoped": 0.4,
        "bootstrapped": 0.5,
        "acquiring_sources": 0.45,
        "building_pipelines": 0.5,
        "hydrating": 0.58,
        "researching": 0.65,
        "artifacting": 0.72,
        "verifying": 0.78,
        "closeout": 0.88,
    }.get(phase, 0.45)
    if current_blocker:
        base -= 0.15
    if failed_runs:
        base -= min(0.2, failed_runs * 0.03)
    if successful_runs:
        base += min(0.1, successful_runs * 0.02)
    base += min(0.15, progress_percent / 100.0 * 0.15)
    return max(0.0, min(1.0, round(base, 2)))


def _first_auditor_blocker(auditor: dict[str, Any] | None) -> str:
    blockers = (auditor or {}).get("blockers")
    if not isinstance(blockers, list) or not blockers:
        return ""
    return str(blockers[0] or "")


def sync_goal_runtime(
    project: dict[str, Any],
    *,
    tasks: list[dict[str, Any]],
    auditors: dict[str, Any],
    reality: dict[str, Any],
    active_sessions: list[dict[str, Any]],
    autopilot_enabled: bool,
) -> dict[str, Any]:
    contract, state, lessons, blockers, decisions = _goal_context(project)
    preflight = evaluate_preflight(project, reality=reality)
    state["preflight"] = preflight
    root = _project_root(project)
    sources_present = (root / ".ontology" / "sources").exists() or (root / "research_plan" / "state" / "sources.json").exists()
    artifacts_present = (root / "artifacts").exists() and any(path.is_file() for path in (root / "artifacts").rglob("*"))
    criteria = _criterion_statuses(
        contract,
        tasks=tasks,
        auditors=auditors,
        reality=reality,
        active_sessions=active_sessions,
        artifacts_present=artifacts_present,
        sources_present=sources_present,
    )
    satisfied = sum(1 for item in criteria if item["satisfied"])
    total = len(criteria)
    percent = round((satisfied / total) * 100, 2) if total else 100.0
    state["success"] = {
        "criteriaSatisfied": satisfied,
        "criteriaTotal": total,
        "percent": percent,
        "criteria": criteria,
    }
    phase, reason = _derive_phase(
        state=state,
        preflight=preflight,
        tasks=tasks,
        auditors=auditors,
        active_sessions=active_sessions,
        reality=reality,
        sources_present=sources_present,
        artifacts_present=artifacts_present,
    )
    current_blocker = None
    if phase in {"blocked", "needs_human"}:
        current_blocker = preflight.get("currentBlocker")
        if not current_blocker:
            current_blocker = _first_auditor_blocker(auditors.get("session"))
        if not current_blocker:
            current_blocker = _first_auditor_blocker(auditors.get("planner"))
        if not current_blocker:
            current_blocker = _first_auditor_blocker(auditors.get("ontology"))
        if not current_blocker:
            current_blocker = _first_auditor_blocker(auditors.get("integrity"))
        if not current_blocker:
            current_blocker = _first_auditor_blocker(auditors.get("closeout"))
        current_blocker = current_blocker or "Autonomy is blocked."
    state["currentBlocker"] = current_blocker
    state["tracks"] = {
        "research": {
            "status": "blocked" if phase in {"blocked", "needs_human"} or str((auditors.get("integrity") or {}).get("status") or "") == "blocked" else ("running" if active_sessions or any(task.get("status") == "running" for task in tasks) else "ready"),
            "blocker": current_blocker if phase in {"blocked", "needs_human"} else None,
        },
        "platformRepair": {
            "status": "running" if phase == "blocked" else ("clear" if preflight.get("passed") else "blocked"),
            "blocker": current_blocker if phase == "blocked" or not preflight.get("passed") else None,
        },
    }
    prior_phase = str(state.get("phase") or "declared")
    _set_phase(state, phase, reason)
    state["status"] = "completed" if phase == "completed" else "active"
    if phase != prior_phase:
        state["lastMeaningfulProgressAt"] = _now()
        if phase == "completed":
            state["runCounts"]["successful"] = int((state.get("runCounts") or {}).get("successful") or 0) + 1
    dashboard = state.get("dashboard") or {}
    dashboard.update(
        {
            "currentPhase": state["phase"],
            "currentBlocker": current_blocker,
            "retryBudgetUsed": int((state.get("retryBudget") or {}).get("used") or 0),
            "successfulRuns": int((state.get("runCounts") or {}).get("successful") or 0),
            "failedRuns": int((state.get("runCounts") or {}).get("failed") or 0),
            "criteriaSatisfiedPercent": percent,
            "lastMeaningfulProgressAt": state.get("lastMeaningfulProgressAt"),
            "autonomyConfidence": 0.0,
            "autopilotEnabled": autopilot_enabled,
        }
    )
    confidence = _confidence_for_state(
        state["phase"],
        current_blocker=current_blocker,
        failed_runs=dashboard["failedRuns"],
        successful_runs=dashboard["successfulRuns"],
        progress_percent=percent,
    )
    state["autonomyConfidence"] = confidence
    dashboard["autonomyConfidence"] = confidence
    state["dashboard"] = dashboard
    open_blockers = []
    if current_blocker:
        open_blockers.append(
            {
                "kind": "human_decision" if phase == "needs_human" else "platform_blocker",
                "summary": current_blocker,
                "phase": state["phase"],
                "openedAt": _now(),
            }
        )
    blockers = open_blockers
    return _write_bundle(project, contract, state, lessons, blockers, decisions)


def record_failure(
    project: dict[str, Any],
    *,
    failure_class: str,
    summary: str,
    root_cause_hypothesis: str,
    reusable_lesson: str,
    next_repair_action: str,
    retry_eligible: bool,
    phase_override: str | None = None,
) -> dict[str, Any]:
    contract, state, lessons, blockers, decisions = _goal_context(project)
    failure_class = _ensure_failure_class(failure_class)
    retry_budget = state.get("retryBudget") or {"max": 0, "used": 0, "remaining": 0}
    retry_max = int(retry_budget.get("max") or 0)
    retry_used = int(retry_budget.get("used") or 0)
    consume_retry = retry_eligible and retry_used < retry_max
    if consume_retry:
        retry_used += 1
    retry_remaining = max(retry_max - retry_used, 0)
    retry_budget.update({"used": retry_used, "remaining": retry_remaining, "max": retry_max})
    state["retryBudget"] = retry_budget
    state["runCounts"] = state.get("runCounts") or {"successful": 0, "failed": 0}
    state["runCounts"]["failed"] = int(state["runCounts"].get("failed") or 0) + 1
    state["activeFailure"] = {
        "failureClass": failure_class,
        "summary": summary,
        "at": _now(),
        "retryEligible": retry_eligible,
        "retryBudgetRemaining": retry_remaining,
    }
    state["currentBlocker"] = summary
    phase = phase_override or ("needs_human" if not retry_eligible and retry_remaining == 0 else "blocked")
    _set_phase(state, phase, summary)
    state["autonomyConfidence"] = _confidence_for_state(
        phase,
        current_blocker=summary,
        failed_runs=int(state["runCounts"]["failed"]),
        successful_runs=int((state["runCounts"] or {}).get("successful") or 0),
        progress_percent=float((state.get("success") or {}).get("percent") or 0.0),
    )
    state["dashboard"] = state.get("dashboard") or {}
    state["dashboard"]["failedRuns"] = int(state["runCounts"]["failed"])
    state["dashboard"]["retryBudgetUsed"] = retry_used
    state["dashboard"]["currentBlocker"] = summary
    state["dashboard"]["autonomyConfidence"] = state["autonomyConfidence"]
    lessons.append(
        {
            "failureClass": failure_class,
            "rootCauseHypothesis": root_cause_hypothesis,
            "reusableLesson": reusable_lesson,
            "nextRepairAction": next_repair_action,
            "retryEligible": retry_eligible,
            "retryBudgetRemaining": retry_remaining,
            "recordedAt": _now(),
            "summary": summary,
        }
    )
    blockers = [
        {
            "kind": failure_class,
            "summary": summary,
            "rootCauseHypothesis": root_cause_hypothesis,
            "nextRepairAction": next_repair_action,
            "retryEligible": retry_eligible,
            "retryBudgetRemaining": retry_remaining,
            "openedAt": _now(),
        }
    ]
    return _write_bundle(project, contract, state, lessons, blockers, decisions)


def record_human_decision(
    project: dict[str, Any],
    *,
    decision_kind: str,
    blocked: str,
    autonomy_limit: str,
    decision_needed: str,
    next_step_after_decision: str,
) -> dict[str, Any]:
    contract, state, lessons, blockers, decisions = _goal_context(project)
    if decision_kind not in HUMAN_DECISION_KINDS:
        decision_kind = "scope_decision"
    summary = f"{blocked} {decision_needed}".strip()
    decisions.append(
        {
            "kind": decision_kind,
            "blocked": blocked,
            "autonomyLimit": autonomy_limit,
            "decisionNeeded": decision_needed,
            "nextStepAfterDecision": next_step_after_decision,
            "recordedAt": _now(),
        }
    )
    state["currentBlocker"] = blocked
    _set_phase(state, "needs_human", blocked)
    blockers = [
        {
            "kind": "needs_human",
            "summary": summary,
            "autonomyLimit": autonomy_limit,
            "decisionNeeded": decision_needed,
            "nextStepAfterDecision": next_step_after_decision,
            "openedAt": _now(),
        }
    ]
    return _write_bundle(project, contract, state, lessons, blockers, decisions)


def mark_completed(project: dict[str, Any], *, summary: str) -> dict[str, Any]:
    contract, state, lessons, blockers, decisions = _goal_context(project)
    _set_phase(state, "completed", summary)
    state["status"] = "completed"
    state["currentBlocker"] = None
    state["activeFailure"] = None
    state["lastMeaningfulProgressAt"] = _now()
    state["runCounts"] = state.get("runCounts") or {"successful": 0, "failed": 0}
    state["runCounts"]["successful"] = int(state["runCounts"].get("successful") or 0) + 1
    state["autonomyConfidence"] = 1.0
    state["dashboard"] = state.get("dashboard") or {}
    state["dashboard"].update(
        {
            "currentPhase": "completed",
            "currentBlocker": None,
            "successfulRuns": int(state["runCounts"]["successful"]),
            "failedRuns": int(state["runCounts"].get("failed") or 0),
            "autonomyConfidence": 1.0,
            "criteriaSatisfiedPercent": 100.0,
            "lastMeaningfulProgressAt": state["lastMeaningfulProgressAt"],
        }
    )
    state["success"] = state.get("success") or {}
    state["success"]["percent"] = 100.0
    state["success"]["criteriaSatisfied"] = int(state["success"].get("criteriaTotal") or 0)
    blockers = []
    return _write_bundle(project, contract, state, lessons, blockers, decisions)
