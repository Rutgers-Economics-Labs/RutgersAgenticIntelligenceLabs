from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.services import goal_service


client = TestClient(app)


def _write_manifest(root):
    (root / "rail.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "",
                "project:",
                '  name: "Demo"',
                '  slug: "demo-project"',
                '  default_branch: "main"',
                '  description: "Demo goal mode project"',
                "",
                "paths:",
                '  ontology_root: ".ontology"',
                '  topics_root: "topics"',
                '  specs_root: "specs"',
                '  plan_root: "research_plan"',
                '  agents_root: "agents"',
                '  skills_root: "skills"',
                '  artifacts_root: "artifacts"',
                "",
                "hydration:",
                '  ontology_file: ".ontology/ontology.yaml"',
                '  sources_dir: ".ontology/sources"',
                '  pipelines_dir: ".ontology/pipelines"',
                '  transforms_dir: ".ontology/transforms"',
                '  hydration_mode: "full"',
                "",
                "agents:",
                '  roles_dir: "agents"',
                '  default_runner: "codex_cli"',
                "  sequential_execution: true",
                "  approval_required_for_write_runs: true",
                '  planner_thread_mode: "project"',
                '  default_planner_role: "planner"',
                "",
                "frontend:",
                '  topic_index_mode: "filesystem"',
                '  artifact_index_mode: "filesystem"',
                "  show_repo_tree: true",
                "  show_task_board_snapshot: true",
                '  default_home_view: "project_home"',
            ]
        ),
        encoding="utf-8",
    )


def test_goal_contract_endpoint_writes_durable_goal_files(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    for name in ("topics", "specs", "agents", "skills", "artifacts"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    _write_manifest(tmp_path)

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo",
            "slug": slug,
            "description": "Demo goal mode project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/goal",
        json={
            "objective": "Explain how weather shocks affect prices.",
            "successCriteria": [
                "hydrated ontology exists",
                "final report has provenance-backed claims",
                "closeout audit passes",
            ],
            "requiredEvidence": ["hydration artifact", "claims.json entries", "closeout certificate"],
            "forbiddenShortcuts": ["do not use placeholder sources"],
            "escalationPolicy": ["pause only for access decisions"],
            "allowedSpend": {"retries": 4, "timeMinutes": 180},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["phase"] == "scoped"
    assert payload["preflight"]["passed"] is True
    assert (tmp_path / ".rail" / "goal" / "goal.md").exists()
    assert (tmp_path / ".rail" / "goal" / "goal_state.json").exists()
    assert (tmp_path / ".rail" / "goal" / "goal_lessons.json").exists()
    assert (tmp_path / ".rail" / "goal" / "goal_blockers.json").exists()
    assert (tmp_path / ".rail" / "goal" / "goal_decisions.json").exists()

    bundle = goal_service.load_goal_bundle(
        {
            "_id": "project-1",
            "name": "Demo",
            "slug": "demo-project",
            "description": "Demo goal mode project",
            "localRepoPath": str(tmp_path),
        }
    )
    assert bundle["contract"]["objective"] == "Explain how weather shocks affect prices."
    assert bundle["state"]["contract"]["allowedSpend"]["retries"] == 4


def test_goal_contract_endpoint_reports_preflight_failure(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo",
            "slug": slug,
            "description": "Demo goal mode project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post(
        "/api/v1/projects/demo-project/goal",
        json={
            "objective": "Test goal",
            "successCriteria": ["closeout audit passes"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["preflight"]["passed"] is False
    assert payload["preflight"]["currentBlocker"] == "Repo root and rail.yaml must exist."


def test_autopilot_goal_mode_stops_on_invalid_manifest(monkeypatch, tmp_path):
    from app.services import autopilot_service

    _write_manifest(tmp_path)
    project = {
        "_id": "project-1",
        "name": "Demo",
        "slug": "demo-project",
        "description": "Demo goal mode project",
        "localRepoPath": str(tmp_path),
    }
    goal_service.create_goal_contract(project, {"objective": "Test goal", "successCriteria": ["closeout audit passes"]})

    failures: list[dict] = []
    disables: list[str] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _disable(project_slug: str, *, auto_approve=None):
        disables.append(project_slug)
        autopilot_service._active_autopilots[project_slug] = False

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "load_validated_manifest", lambda project_arg: (_ for _ in ()).throw(RuntimeError("bad manifest")))
    monkeypatch.setattr(autopilot_service, "_disable_autopilot_desired_state", _disable)
    monkeypatch.setattr(
        goal_service,
        "record_failure",
        lambda project_arg, **kwargs: failures.append(kwargs) or {"state": {"phase": "blocked"}},
    )

    autopilot_service._active_autopilots["demo-project"] = True
    autopilot_service._autopilot_configs["demo-project"] = {"auto_approve": False, "desired_enabled": True}
    autopilot_service._wake_events["demo-project"] = asyncio.Event()

    asyncio.run(autopilot_service.run_autopilot_loop("demo-project", max_iterations=1))

    assert disables == ["demo-project"]
    assert failures and failures[0]["failure_class"] == "setup_failure"


def test_autopilot_goal_mode_records_audit_drift_failure(monkeypatch, tmp_path):
    from app.services import autopilot_service

    _write_manifest(tmp_path)
    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    project = {
        "_id": "project-1",
        "name": "Demo",
        "slug": "demo-project",
        "description": "Demo goal mode project",
        "localRepoPath": str(tmp_path),
    }
    goal_service.create_goal_contract(project, {"objective": "Test goal", "successCriteria": ["closeout audit passes"]})

    failures: list[dict] = []

    async def _get_project_by_slug(slug: str):
        return project

    async def _reconcile_project_reality(project_arg):
        return {
            "removedTaskFiles": [],
            "updatedTaskIds": [],
            "repairedSessionIds": [],
            "repairedAuditSessionIds": [],
            "hasChanges": False,
        }

    monkeypatch.setattr(autopilot_service.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(autopilot_service.planner_service, "load_validated_manifest", lambda project_arg: None)
    monkeypatch.setattr(autopilot_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(autopilot_service, "audit_gate_status", lambda project_root: {"blocked": True, "reason": "Post-run audit missing", "staleSessionIds": []})
    monkeypatch.setattr(
        goal_service,
        "record_failure",
        lambda project_arg, **kwargs: failures.append(kwargs) or {"state": {"phase": "blocked"}},
    )

    class _ImmediateWakeEvent:
        def clear(self):
            return None

        async def wait(self):
            autopilot_service._active_autopilots["demo-project"] = False
            return True

    autopilot_service._active_autopilots["demo-project"] = True
    autopilot_service._autopilot_configs["demo-project"] = {"auto_approve": False, "desired_enabled": True}
    autopilot_service._wake_events["demo-project"] = _ImmediateWakeEvent()

    asyncio.run(autopilot_service.run_autopilot_loop("demo-project", max_iterations=1))

    assert failures and failures[0]["failure_class"] == "audit_drift"


def test_sync_goal_runtime_handles_empty_auditor_blocker_lists(tmp_path):
    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts").mkdir(parents=True, exist_ok=True)
    _write_manifest(tmp_path)

    project = {
        "_id": "project-1",
        "name": "Demo",
        "slug": "demo-project",
        "description": "Demo goal mode project",
        "localRepoPath": str(tmp_path),
    }
    goal_service.create_goal_contract(project, {"objective": "Test goal", "successCriteria": ["closeout audit passes"]})

    payload = goal_service.sync_goal_runtime(
        project,
        tasks=[],
        auditors={
            "session": {"status": "blocked", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        },
        reality={"repoRootExists": True, "hasRailYaml": True, "hasResearchPlan": True},
        active_sessions=[],
        autopilot_enabled=True,
    )

    assert payload["state"]["currentBlocker"] in {None, "", "Autonomy is blocked."}
