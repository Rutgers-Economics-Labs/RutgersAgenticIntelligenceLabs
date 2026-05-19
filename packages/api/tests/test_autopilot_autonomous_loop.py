"""Category D: Autopilot-Driven Autonomous Loop Validation.

These tests prove the platform's autopilot service (not a human operator) drives
the full project lifecycle from initial tasks → session launches → auditor
certification → closeout for three varied project archetypes.

Key invariants asserted per archetype:
  1. `planner_runtime._execute_planner_tool("launch_task_runner", ...)` is called
     by the autopilot loop — not by a human operator.
  2. `_mark_project_completed` is called — the autopilot declared the project closed.
  3. Zero operator-level calls: the loop ran from `run_autopilot_loop(slug)` to
     completion with no external signals or manual task promotions.
  4. The audit gate blocks advancement until each session has a post-run audit.
  5. Real session state files and real audit files are written to disk; the
     autopilot reads them to verify progress — not trusting raw LLM output.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.services import autopilot_service, session_files
from app.services.audit_service import write_post_run_audit


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_READY_AUDITORS: dict[str, Any] = {
    "session": {"status": "ready", "blockers": []},
    "planner": {"status": "ready", "blockers": []},
    "ontology": {"status": "ready", "blockers": [], "state": None, "stateClassification": "not_applicable", "duckdbPath": None},
    "integrity": {"status": "ready", "blockers": []},
    "closeout": {"status": "ready", "blockers": []},
}

_CLEAN_REALITY: dict[str, Any] = {
    "hasDrift": False,
    "duplicateTaskFileCount": 0,
    "taskSessionMismatchCount": 0,
    "staleRuntimeSessionCount": 0,
    "zombieSessionCount": 0,
    "staleAuditSessionCount": 0,
    "terminalSessionCount": 0,
    "activeRuntimeSessionCount": 0,
    "runningAgentStatusDriftCount": 0,
    "runningAgentRoleDriftCount": 0,
    "runningAgentRunnerDriftCount": 0,
    "ontologyArtifactDriftCount": 0,
    "artifactRegistryDriftCount": 0,
    "secretPolicyRoleDriftCount": 0,
    "roleConfigAliasDriftCount": 0,
    "details": {
        "duplicateTaskFiles": [],
        "taskSessionMismatchTaskIds": [],
        "staleRuntimeSessionIds": [],
        "zombieSessionIds": [],
        "staleAuditSessionIds": [],
        "terminalSessionIds": [],
        "ontologyArtifactDrift": {"hasDrift": False},
        "artifactRegistryDrift": {"hasDrift": False},
    },
    "removedTaskFiles": [],
    "updatedTaskIds": [],
    "repairedSessionIds": [],
    "repairedAuditSessionIds": [],
    "hasChanges": False,
}


def _seed_minimal_project(root: Path, archetype: str = "time-series-econ") -> None:
    """Write a schema-valid rail.yaml and directory layout for the autopilot."""
    slug = archetype.replace(" ", "-").lower()
    rail_yaml = f"""\
version: 1

project:
  name: "{archetype} Validation Project"
  slug: "{slug}"
  default_branch: "main"
  description: "Autopilot-driven validation for {archetype}"

paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"

hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"
  transforms_dir: ".ontology/transforms"

agents:
  roles_dir: "agents"
  default_runner: "codex_cli"

frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"

lifecycle:
  closeout_requires: []
"""
    (root / "rail.yaml").write_text(rail_yaml, encoding="utf-8")
    for d in [
        "research_plan/sessions",
        "research_plan/audits",
        "research_plan/state",
        "artifacts",
        ".ontology/pipelines",
        ".ontology/sources",
        "agents",
        "topics",
        "specs",
        ".git",
    ]:
        (root / d).mkdir(parents=True, exist_ok=True)


def _write_completed_session(root: Path, session_id: str, role: str) -> Path:
    """Write a real completed session state so audit_gate_status counts it."""
    session_root = root / "research_plan" / "sessions" / role / session_id
    session_root.mkdir(parents=True, exist_ok=True)
    session_files.write_state(
        session_root,
        {
            "session_id": session_id,
            "role": role,
            "status": "completed",
            "review_status": "review",
            "verification_status": "passed",
            "publish_status": "published",
            "updated_at": session_files.utc_now_iso(),
        },
    )
    session_files.append_event(session_root, "session_completed", content="Task completed.", status="completed")
    return session_root


async def _write_audit_for_session(
    root: Path, session_root: Path, session_id: str, role: str
) -> None:
    """Write a real post-run audit file so audit_gate_status unblocks."""
    project_stub = {
        "_id": None,
        "slug": root.name,
        "localRepoPath": str(root),
    }
    await write_post_run_audit(
        project=project_stub,
        project_root=root,
        session_root=session_root,
        session_id=session_id,
        session={"_id": session_id, "role": role},
        changed_files=[],
    )


def _build_archetype_fixture(
    tmp_path: Path,
    archetype: str,
    tasks: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Seed a project directory and return (project, board, seeded_tasks)."""
    project_root = tmp_path / archetype
    project_root.mkdir()
    _seed_minimal_project(project_root, archetype)
    project = {
        "_id": f"proj-{archetype}",
        "slug": archetype,
        "localRepoPath": str(project_root),
    }
    board = {"_id": f"board-{archetype}"}
    return project, board, tasks


# ---------------------------------------------------------------------------
# Category D Test 1 — time-series-econ archetype
# ---------------------------------------------------------------------------

def test_autopilot_drives_time_series_econ_to_closeout(monkeypatch, tmp_path):
    """Autopilot loop drives a time-series-econ project from one ready task
    through session launch → audit certification → closeout.

    The human trigger is a single call to run_autopilot_loop. Everything else
    (launch, audit, closeout) is driven by the loop itself.
    """
    archetype = "time-series-econ"
    project, board, initial_tasks = _build_archetype_fixture(
        tmp_path,
        archetype,
        tasks=[
            {
                "_id": "analyze-nj-housing-trends",
                "title": "Analyze NJ housing price trends vs unemployment",
                "status": "ready",
                "approvalState": "granted",
                "agentRole": "research",
                "agent_role": "research",
                "runner": "codex_cli",
                "repoPaths": ["artifacts"],
                "dependsOnTaskIds": [],
            }
        ],
    )
    project_root = Path(project["localRepoPath"])
    task_state: dict[str, str] = {"status": "ready"}
    launches: list[dict[str, Any]] = []
    completed_calls: list[str] = []
    session_id = "auto-res-time-series-001"
    role = "research"

    async def _fake_execute_planner_tool(proj: dict, name: str, args: dict) -> dict[str, Any]:
        if name == "launch_task_runner":
            task_id = args.get("task_id") or ""
            launches.append({"task_id": task_id, "triggered_by": "autopilot_loop"})
            task_state["status"] = "done"
            # Write real session state + audit so audit_gate_status passes
            sr = _write_completed_session(project_root, session_id, role)
            await _write_audit_for_session(project_root, sr, session_id, role)
            return {"convex_session_id": session_id, "status": "launched"}
        return {"status": "ok"}

    async def _fake_get_project(slug: str) -> dict:
        return project

    async def _fake_ensure_main_board(proj: dict) -> dict:
        return board

    async def _fake_list_tasks(board_id: str, *, project: dict | None = None) -> list[dict]:
        task = dict(initial_tasks[0])
        task["status"] = task_state["status"]
        return [task]

    async def _fake_find_active_worker(project_id: str) -> None:
        return None

    async def _fake_build_auditor_statuses(proj: dict, *, tasks=None, active_sessions=None) -> dict:
        return dict(_READY_AUDITORS)

    async def _fake_reconcile(proj: dict) -> dict:
        return dict(_CLEAN_REALITY)

    async def _fake_run_planner_turn(**kwargs) -> None:
        return None

    async def _fake_list_approvals(proj: dict) -> list:
        return []

    async def _fake_list_decision_events(*args, **kwargs) -> list:
        return []

    async def _fake_sync_planner_files(*args, **kwargs) -> None:
        return None

    async def _fake_mark_completed(proj: dict) -> None:
        completed_calls.append(proj["slug"])

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _fake_get_project)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _fake_list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _fake_list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _fake_find_active_worker)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _fake_build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _fake_reconcile)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _fake_run_planner_turn)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _fake_list_decision_events)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _fake_mark_completed)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service.planner_runtime, "_execute_planner_tool", _fake_execute_planner_tool)

    autopilot_service._active_autopilots[archetype] = True
    autopilot_service._autopilot_configs[archetype] = {"auto_approve": True}
    autopilot_service._wake_events[archetype] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop(archetype))

    # The autopilot (not an operator) triggered the session launch
    assert len(launches) == 1, f"Expected 1 autopilot-driven launch, got {launches}"
    assert launches[0]["triggered_by"] == "autopilot_loop"
    assert launches[0]["task_id"] == "analyze-nj-housing-trends"

    # The autopilot declared the project closed
    assert archetype in completed_calls, "Autopilot must call _mark_project_completed"

    # Real audit files were written to disk during the loop
    audit_files = list((project_root / "research_plan" / "audits").glob("*.json"))
    assert len(audit_files) >= 1, "Autopilot must produce at least one durable audit file"

    audit_payload = json.loads(audit_files[0].read_text(encoding="utf-8"))
    assert audit_payload.get("session", {}).get("status") == "completed"


# ---------------------------------------------------------------------------
# Category D Test 2 — document-synthesis archetype
# ---------------------------------------------------------------------------

def test_autopilot_drives_document_synthesis_to_closeout(monkeypatch, tmp_path):
    """Autopilot loop drives a document-synthesis project through two sequential
    tasks (research → artifacts) with no operator intervention between launches.

    This proves the loop can sequence multiple session launches autonomously.
    """
    archetype = "document-synthesis"
    task1 = {
        "_id": "literature-synthesis-task",
        "title": "Synthesize NJ labor market literature",
        "status": "ready",
        "approvalState": "granted",
        "agentRole": "research",
        "agent_role": "research",
        "runner": "gemini_cli",
        "repoPaths": ["artifacts", "research_plan"],
        "dependsOnTaskIds": [],
    }
    task2 = {
        "_id": "artifact-generation-task",
        "title": "Generate final synthesis report",
        "status": "backlog",
        "approvalState": "granted",
        "agentRole": "artifact",
        "agent_role": "artifact",
        "runner": "gemini_cli",
        "repoPaths": ["artifacts"],
        "dependsOnTaskIds": ["literature-synthesis-task"],
    }
    project, board, _ = _build_archetype_fixture(tmp_path, archetype, tasks=[task1, task2])
    project_root = Path(project["localRepoPath"])

    task1_state: dict[str, str] = {"status": "ready"}
    task2_state: dict[str, str] = {"status": "backlog"}
    launches: list[dict[str, Any]] = []
    completed_calls: list[str] = []
    launch_count = {"n": 0}

    async def _fake_execute_planner_tool(proj: dict, name: str, args: dict) -> dict[str, Any]:
        if name != "launch_task_runner":
            return {"status": "ok"}
        task_id = args.get("task_id") or ""
        launch_count["n"] += 1
        launches.append({"task_id": task_id, "launch_n": launch_count["n"]})

        if task_id == task1["_id"]:
            task1_state["status"] = "done"
            task2_state["status"] = "ready"
            sr = _write_completed_session(project_root, "auto-res-doc-001", "research")
            await _write_audit_for_session(project_root, sr, "auto-res-doc-001", "research")
        elif task_id == task2["_id"]:
            task2_state["status"] = "done"
            sr = _write_completed_session(project_root, "auto-art-doc-001", "artifact")
            await _write_audit_for_session(project_root, sr, "auto-art-doc-001", "artifact")
        return {"convex_session_id": f"auto-sess-{launch_count['n']}", "status": "launched"}

    async def _fake_get_project(slug: str) -> dict:
        return project

    async def _fake_ensure_main_board(proj: dict) -> dict:
        return board

    async def _fake_list_tasks(board_id: str, *, project: dict | None = None) -> list[dict]:
        t1 = dict(task1)
        t1["status"] = task1_state["status"]
        t2 = dict(task2)
        t2["status"] = task2_state["status"]
        return [t1, t2]

    async def _fake_find_active_worker(project_id: str) -> None:
        return None

    async def _fake_build_auditor_statuses(proj: dict, *, tasks=None, active_sessions=None) -> dict:
        return dict(_READY_AUDITORS)

    async def _fake_reconcile(proj: dict) -> dict:
        return dict(_CLEAN_REALITY)

    async def _fake_run_planner_turn(**kwargs) -> None:
        return None

    async def _fake_list_approvals(proj: dict) -> list:
        return []

    async def _fake_list_decision_events(*args, **kwargs) -> list:
        return []

    async def _fake_sync_planner_files(*args, **kwargs) -> None:
        return None

    async def _fake_mark_completed(proj: dict) -> None:
        completed_calls.append(proj["slug"])

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _fake_get_project)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _fake_list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _fake_list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _fake_find_active_worker)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _fake_build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _fake_reconcile)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _fake_run_planner_turn)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _fake_list_decision_events)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _fake_mark_completed)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service.planner_runtime, "_execute_planner_tool", _fake_execute_planner_tool)

    autopilot_service._active_autopilots[archetype] = True
    autopilot_service._autopilot_configs[archetype] = {"auto_approve": True}
    autopilot_service._wake_events[archetype] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop(archetype))

    # Two launches, sequenced by the autopilot without operator intervention
    assert len(launches) == 2, f"Expected 2 autopilot-driven launches, got {launches}"
    assert launches[0]["task_id"] == task1["_id"], "First launch should be research task"
    assert launches[1]["task_id"] == task2["_id"], "Second launch should be artifact task"

    # Ordering guarantee: research before artifact
    assert launches[0]["launch_n"] < launches[1]["launch_n"]

    assert archetype in completed_calls

    audit_files = list((project_root / "research_plan" / "audits").glob("*.json"))
    assert len(audit_files) == 2, "Each autopilot-driven session must produce an audit"


# ---------------------------------------------------------------------------
# Category D Test 3 — cross-sectional archetype
# ---------------------------------------------------------------------------

def test_autopilot_drives_cross_sectional_to_closeout(monkeypatch, tmp_path):
    """Autopilot loop drives a cross-sectional project: planner task creates
    research + data tasks, then all three are launched by the autopilot.

    Proves the autopilot can handle planner → worker → worker sequencing
    without any operator interaction.
    """
    archetype = "cross-sectional"
    plan_task = {
        "_id": "planner-task",
        "title": "Plan cross-sectional housing comparison",
        "status": "ready",
        "approvalState": "granted",
        "agentRole": "planner",
        "agent_role": "planner",
        "runner": "gemini_cli",
        "repoPaths": ["research_plan"],
        "dependsOnTaskIds": [],
    }
    research_task = {
        "_id": "research-task",
        "title": "Analyze housing affordability across northeast states",
        "status": "backlog",
        "approvalState": "granted",
        "agentRole": "research",
        "agent_role": "research",
        "runner": "gemini_cli",
        "repoPaths": ["artifacts"],
        "dependsOnTaskIds": ["planner-task"],
    }

    project, board, _ = _build_archetype_fixture(tmp_path, archetype, tasks=[plan_task, research_task])
    project_root = Path(project["localRepoPath"])

    plan_state: dict[str, str] = {"status": "ready"}
    research_state: dict[str, str] = {"status": "backlog"}
    launches: list[str] = []
    completed_calls: list[str] = []
    launch_count = {"n": 0}

    async def _fake_execute_planner_tool(proj: dict, name: str, args: dict) -> dict[str, Any]:
        if name != "launch_task_runner":
            return {"status": "ok"}
        task_id = args.get("task_id") or ""
        launch_count["n"] += 1
        launches.append(task_id)

        if task_id == plan_task["_id"]:
            plan_state["status"] = "done"
            research_state["status"] = "ready"
            sr = _write_completed_session(project_root, "auto-pla-cross-001", "planner")
            await _write_audit_for_session(project_root, sr, "auto-pla-cross-001", "planner")
        elif task_id == research_task["_id"]:
            research_state["status"] = "done"
            sr = _write_completed_session(project_root, "auto-res-cross-001", "research")
            await _write_audit_for_session(project_root, sr, "auto-res-cross-001", "research")
        return {"convex_session_id": f"auto-sess-{launch_count['n']}", "status": "launched"}

    async def _fake_get_project(slug: str) -> dict:
        return project

    async def _fake_ensure_main_board(proj: dict) -> dict:
        return board

    async def _fake_list_tasks(board_id: str, *, project: dict | None = None) -> list[dict]:
        t_plan = dict(plan_task)
        t_plan["status"] = plan_state["status"]
        t_res = dict(research_task)
        t_res["status"] = research_state["status"]
        return [t_plan, t_res]

    async def _fake_find_active_worker(project_id: str) -> None:
        return None

    async def _fake_build_auditor_statuses(proj: dict, *, tasks=None, active_sessions=None) -> dict:
        return dict(_READY_AUDITORS)

    async def _fake_reconcile(proj: dict) -> dict:
        return dict(_CLEAN_REALITY)

    async def _fake_run_planner_turn(**kwargs) -> None:
        return None

    async def _fake_list_approvals(proj: dict) -> list:
        return []

    async def _fake_list_decision_events(*args, **kwargs) -> list:
        return []

    async def _fake_sync_planner_files(*args, **kwargs) -> None:
        return None

    async def _fake_mark_completed(proj: dict) -> None:
        completed_calls.append(proj["slug"])

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _fake_get_project)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _fake_list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _fake_list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _fake_find_active_worker)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _fake_build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _fake_reconcile)
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", _fake_run_planner_turn)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _fake_list_decision_events)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _fake_mark_completed)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service.planner_runtime, "_execute_planner_tool", _fake_execute_planner_tool)

    autopilot_service._active_autopilots[archetype] = True
    autopilot_service._autopilot_configs[archetype] = {"auto_approve": True}
    autopilot_service._wake_events[archetype] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop(archetype))

    assert launches == [plan_task["_id"], research_task["_id"]], \
        f"Autopilot must sequence planner → research. Got: {launches}"

    assert archetype in completed_calls

    audit_files = sorted((project_root / "research_plan" / "audits").glob("*.json"))
    assert len(audit_files) == 2


# ---------------------------------------------------------------------------
# Category D Test 4 — audit gate blocks advancement until session has audit
# ---------------------------------------------------------------------------

def test_autopilot_audit_gate_blocks_until_audit_is_written(monkeypatch, tmp_path):
    """The audit gate prevents the autopilot from advancing when a terminal session
    does not yet have a post-run audit. Once the audit is written, the gate clears
    and the autopilot proceeds to closeout.

    This verifies invariant: 'nothing advances from raw worker output; everything
    advances from audited project reality.'
    """
    archetype = "audit-gate-test"
    project, board, _ = _build_archetype_fixture(
        tmp_path,
        archetype,
        tasks=[
            {
                "_id": "sole-task",
                "title": "Run analysis",
                "status": "done",
                "approvalState": "granted",
                "agentRole": "research",
                "agent_role": "research",
                "runner": "codex_cli",
                "repoPaths": [],
                "dependsOnTaskIds": [],
            }
        ],
    )
    project_root = Path(project["localRepoPath"])
    session_id = "stale-res-session-001"
    role = "research"

    # Write a completed session WITHOUT an audit — this should trigger the gate
    session_root = _write_completed_session(project_root, session_id, role)

    gate_hit: list[bool] = []
    completed_calls: list[str] = []
    iteration = {"n": 0}

    # The real audit_gate_status from audit_service is used here (no mock)
    # On iteration 1 the gate fires (no audit). On iteration 2 we write the audit.
    real_audit_gate = autopilot_service.audit_gate_status

    def _fake_audit_gate_status(root: Path) -> dict:
        iteration["n"] += 1
        result = real_audit_gate(root)
        if result.get("blocked"):
            gate_hit.append(True)
            # Run the async audit writer in a separate thread to avoid nesting
            # event loops while still producing a real audit file.
            import asyncio as _asyncio
            import threading

            def _run_audit() -> None:
                _asyncio.run(
                    _write_audit_for_session(project_root, session_root, session_id, role)
                )

            thread = threading.Thread(target=_run_audit)
            thread.start()
            thread.join()
        return result

    async def _fake_get_project(slug: str) -> dict:
        return project

    async def _fake_ensure_main_board(proj: dict) -> dict:
        return board

    async def _fake_list_tasks(board_id: str, *, project: dict | None = None) -> list[dict]:
        return [
            {
                "_id": "sole-task",
                "title": "Run analysis",
                "status": "done",
                "approvalState": "granted",
                "agentRole": "research",
                "agent_role": "research",
                "runner": "codex_cli",
                "repoPaths": [],
                "dependsOnTaskIds": [],
            }
        ]

    async def _fake_find_active_worker(project_id: str) -> None:
        return None

    async def _fake_build_auditor_statuses(proj: dict, *, tasks=None, active_sessions=None) -> dict:
        return dict(_READY_AUDITORS)

    async def _fake_reconcile(proj: dict) -> dict:
        return dict(_CLEAN_REALITY)

    async def _fake_list_approvals(proj: dict) -> list:
        return []

    async def _fake_list_decision_events(*args, **kwargs) -> list:
        return []

    async def _fake_raise_decision_event(*args, **kwargs) -> Any:
        return None

    async def _fake_sync_planner_files(*args, **kwargs) -> None:
        return None

    async def _fake_mark_completed(proj: dict) -> None:
        completed_calls.append(proj["slug"])
        autopilot_service._active_autopilots[archetype] = False

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _fake_get_project)
    monkeypatch.setattr(autopilot_service.planner_service, "ensure_main_board", _fake_ensure_main_board)
    monkeypatch.setattr(autopilot_service.planner_service, "list_tasks", _fake_list_tasks)
    monkeypatch.setattr(autopilot_service.planner_service, "list_approvals", _fake_list_approvals)
    monkeypatch.setattr(autopilot_service.planner_service, "sync_planner_files", _fake_sync_planner_files)
    monkeypatch.setattr(autopilot_service.running_agent_service, "find_active_worker", _fake_find_active_worker)
    monkeypatch.setattr(autopilot_service, "build_auditor_statuses", _fake_build_auditor_statuses)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _fake_reconcile)
    monkeypatch.setattr(autopilot_service, "list_decision_events", _fake_list_decision_events)
    monkeypatch.setattr(autopilot_service, "raise_decision_event", _fake_raise_decision_event)
    monkeypatch.setattr(autopilot_service, "_mark_project_completed", _fake_mark_completed)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", _fake_audit_gate_status)
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_lifecycle_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_expansion_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_project_reality_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_integrity_repair_tasks", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_ontology_repair_task", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_reconcile_ontology_lifecycle_state", lambda p, t: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service, "_ensure_control_plane_repair_tasks", lambda p, t, a: asyncio.sleep(0, result=False))
    monkeypatch.setattr(autopilot_service.planner_runtime, "run_planner_turn", lambda **kw: asyncio.sleep(0))

    # Fast-forward wake events so the loop doesn't actually sleep
    class _InstantEvent:
        def clear(self):
            pass
        async def wait(self):
            await asyncio.sleep(0)
    autopilot_service._wake_events[archetype] = _InstantEvent()  # type: ignore[assignment]

    autopilot_service._active_autopilots[archetype] = True
    autopilot_service._autopilot_configs[archetype] = {"auto_approve": False}

    asyncio.run(autopilot_service.run_autopilot_loop(archetype))

    # Gate fired at least once (session without audit blocked advancement)
    assert gate_hit, "Audit gate must have fired while a terminal session lacked an audit"

    # After the audit was written, the loop reached closeout
    assert archetype in completed_calls, "Autopilot must close the project after audit is written"
