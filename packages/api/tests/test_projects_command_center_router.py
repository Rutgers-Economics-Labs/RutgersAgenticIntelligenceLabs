from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_register_artifacts_rejects_missing_hydration_metadata(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_db.write_bytes(b"db")
    onto_duckdb = ontology_root / "onto.duckdb"
    onto_duckdb.write_bytes(b"duck")

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": str(tmp_path)}

    async def _mutation(path: str, payload: dict):
        raise AssertionError(f"unexpected mutation {path}")

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)

    response = client.post(
        "/api/v1/projects/demo-project/register-artifacts",
        json={"output_db_path": str(onto_db)},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Hydration metadata must exist before promoting active ontology artifacts."


def test_project_repo_routes_use_repo_first_lookup(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    project_root = tmp_path / "demo-project"
    (project_root / "research_plan").mkdir(parents=True, exist_ok=True)
    (project_root / "research_plan" / "current_plan.md").write_text("# Plan\n", encoding="utf-8")
    (project_root / "topics").mkdir(parents=True, exist_ok=True)
    (project_root / "topics" / "brief.md").write_text("# Brief\n", encoding="utf-8")

    async def _refresh_project_record(slug: str):
        return {
            "_id": "local:demo-project",
            "slug": slug,
            "localRepoPath": str(project_root),
        }

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    root_response = client.get("/api/v1/projects/demo-project/repo")
    tree_response = client.get("/api/v1/projects/demo-project/repo/tree", params={"rootDir": "research_plan"})
    file_response = client.get("/api/v1/projects/demo-project/repo/file", params={"path": "topics/brief.md"})
    generic_response = client.get("/api/v1/projects/demo-project/repo/research_plan/current_plan.md")

    assert root_response.status_code == 200
    assert tree_response.status_code == 200
    assert file_response.status_code == 200
    assert generic_response.status_code == 200

    root_payload = root_response.json()
    tree_payload = tree_response.json()
    file_payload = file_response.json()
    generic_payload = generic_response.json()

    assert root_payload["kind"] == "directory"
    assert {entry["path"] for entry in root_payload["entries"]} == {"research_plan", "topics"}
    assert tree_payload["kind"] == "directory"
    assert tree_payload["path"] == "research_plan"
    assert tree_payload["maxDepth"] == 3
    assert {entry["path"] for entry in tree_payload["entries"]} == {"research_plan/current_plan.md"}
    assert file_payload["kind"] == "file"
    assert file_payload["path"] == "topics/brief.md"
    assert file_payload["content"] == "# Brief\n"
    assert generic_payload["kind"] == "file"
    assert generic_payload["path"] == "research_plan/current_plan.md"
    assert generic_payload["content"] == "# Plan\n"


def test_create_project_returns_repo_first_refreshed_project(monkeypatch):
    import app.routers.projects as projects_router

    created_payloads: list[dict] = []

    async def _mutation(path: str, payload: dict):
        assert path == "projects:create"
        created_payloads.append(payload)
        return "project-123"

    async def _query(path: str, payload: dict):
        if path == "projects:getBySlug":
            raise AssertionError("create_project should prefer planner_service refresh")
        raise AssertionError(path)

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "name": "Demo Project",
            "slug": "demo-project",
            "status": "draft",
            "localRepoPath": "/tmp/demo-project",
        }

    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router.planner_service, "resolve_project_reference", _resolve_project_reference)

    response = client.post(
        "/api/v1/projects/",
        json={
            "name": "Demo Project",
            "slug": "demo-project",
            "description": "Repo-first create",
            "approach": "ontology-first",
            "localRepoPath": "/tmp/demo-project-missing-for-test",
            "ontologyConfigSlug": "demo-ontology",
            "apiConfigSlugs": ["demo-source"],
            "pipelineConfigSlug": "demo-pipeline",
        },
    )

    assert response.status_code == 200
    assert response.json()["_id"] == "local:demo-project"
    assert created_payloads[0]["slug"] == "demo-project"


def test_pipeline_run_uses_local_repo_hydration_for_repo_only_project(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    local_project = tmp_path / "demo-project"
    (local_project / ".ontology" / "pipelines").mkdir(parents=True, exist_ok=True)
    (local_project / ".ontology" / "ontology.yaml").write_text("classes: []\n", encoding="utf-8")
    (local_project / ".ontology" / "pipelines" / "demo-pipeline.yaml").write_text(
        "name: demo-pipeline\nontology: .ontology/ontology.yaml\nsteps: []\n",
        encoding="utf-8",
    )

    async def _refresh_project_record(slug: str):
        return {
            "_id": "local:demo-project",
            "slug": slug,
            "localRepoPath": str(local_project),
            "manifestPath": "rail.yaml",
        }

    async def _reconcile_project_reality(project: dict):
        return {"hasChanges": False}

    class _Engine:
        def __init__(self, project_path: str):
            assert project_path == str(local_project)
            self.manifest = type(
                "_Manifest",
                (),
                {"hydration": type("_Hydration", (), {"hydration_mode": "full"})()},
            )()

        def hydrate(self, pipeline_slug: str | None = None):
            assert pipeline_slug == "demo-pipeline"
            return {
                "status": "hydrated",
                "artifact_db_path": str(local_project / ".ontology" / "onto.db"),
                "artifact_duckdb_path": str(local_project / ".ontology" / "onto.duckdb"),
            }

    async def _register_hydration_artifact(**kwargs):
        assert kwargs["pipeline_slug"] == "demo-pipeline"
        return "local-hydration:demo-project:demo-pipeline:full"

    async def _promote_project_hydration_artifact(**kwargs):
        assert kwargs["ontology_artifact_path"].endswith(".ontology/onto.db")
        assert kwargs["duckdb_artifact_path"].endswith(".ontology/onto.duckdb")
        return None

    async def _query(path: str, payload: dict):
        if path == "configs:getPipeline":
            assert payload == {"slug": "demo-pipeline"}
            return None
        raise AssertionError(path)

    async def _mutation(path: str, payload: dict):
        raise AssertionError(f"unexpected mutation {path}")

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(projects_router, "LocalEngine", _Engine)
    monkeypatch.setattr(projects_router, "register_hydration_artifact", _register_hydration_artifact)
    monkeypatch.setattr(projects_router, "promote_project_hydration_artifact", _promote_project_hydration_artifact)
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)

    response = client.post(
        "/api/v1/projects/demo-project/pipeline/run",
        json={"pipelineSlug": "demo-pipeline"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reconciled"] is True
    assert payload["hydration"] == {
        "jobId": None,
        "status": "hydrated",
        "source": "project_repo_local",
        "artifactId": "local-hydration:demo-project:demo-pipeline:full",
        "artifactDbPath": str(local_project / ".ontology" / "onto.db"),
        "artifactDuckdbPath": str(local_project / ".ontology" / "onto.duckdb"),
        "pipelineSlug": "demo-pipeline",
        "projectSlug": "demo-project",
        "device": payload["hydration"]["device"],
    }


def test_command_center_reconcile_endpoint_returns_repair_summary(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _reconcile_project_reality(project: dict):
        return {
            "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
            "updatedTaskIds": ["task-1"],
            "updatedApprovalIds": ["approval-1"],
            "repairedSecretPolicyRoles": ["coding"],
            "repairedSessionIds": ["sess-1"],
            "repairedAuditSessionIds": ["sess-2"],
            "hasChanges": True,
        }

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)

    response = client.post("/api/v1/projects/demo-project/command-center/reconcile")

    assert response.status_code == 200
    assert response.json() == {
        "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
        "updatedTaskIds": ["task-1"],
        "updatedApprovalIds": ["approval-1"],
        "repairedSecretPolicyRoles": ["coding"],
        "repairedSessionIds": ["sess-1"],
        "repairedAuditSessionIds": ["sess-2"],
        "hasChanges": True,
    }


def test_project_context_includes_snapshot_backed_control_plane(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    local_project = tmp_path / "demo-project"
    local_project.mkdir(parents=True, exist_ok=True)
    (local_project / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  description: Demo
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def _refresh_project_record(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo Project",
            "slug": slug,
            "status": "draft",
            "localRepoPath": str(local_project),
            "apiConfigSlugs": [],
        }

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review pending approvals",
                "currentBlocker": "Waiting on approval",
                "blockerSummary": {"blocked": True, "headline": "Waiting on approval"},
                "closeoutCertificate": {"status": "pending"},
                "missionBrief": {"current": "Current brief", "next": "Next brief"},
                "repoHealth": {
                    "hasLocalRepo": True,
                    "hasRailYaml": True,
                    "hasResearchPlan": False,
                },
            },
            "snapshot": {
                "loaded": True,
                "path": "research_plan/state/control_plane_snapshot.json",
                "generatedAt": 1234567890,
                "version": 1,
            },
        },
    )

    response = client.get("/api/v1/projects/demo-project/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["phase"] == "research_active"
    assert payload["controlPlane"] == {
        "phase": "research_active",
        "nextAction": "Review pending approvals",
        "currentBlocker": "Waiting on approval",
        "blockerSummary": {"blocked": True, "headline": "Waiting on approval"},
        "closeoutCertificate": {"status": "pending"},
        "missionBrief": {"current": "Current brief", "next": "Next brief"},
        "repoHealth": {
            "hasLocalRepo": True,
            "hasRailYaml": True,
            "hasResearchPlan": False,
        },
        "snapshot": {
            "loaded": True,
            "path": "research_plan/state/control_plane_snapshot.json",
            "generatedAt": 1234567890,
            "version": 1,
        },
    }


def test_project_phase_prefers_snapshot_without_loading_board(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _list_project_running_agents(project_id: str, active_only: bool = True, limit: int = 50):
        return [{"_id": "sess-1", "status": "running"}]

    async def _ensure_main_board(project):
        raise AssertionError("ensure_main_board should not run when snapshot is loaded")

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "research_active",
                "currentBlocker": "Waiting on approval",
                "nextAction": "Review pending approvals",
                "taskCounts": {
                    "total": 5,
                    "byStatus": {"ready": 2, "done": 1, "cancelled": 1, "running": 1},
                },
                "auditors": {"planner": {"status": "ready"}},
            },
            "snapshot": {
                "loaded": True,
                "path": "research_plan/state/control_plane_snapshot.json",
                "generatedAt": 1234567890,
                "version": 1,
            },
        },
    )
    monkeypatch.setattr(
        "app.services.running_agent_service.list_project_running_agents",
        _list_project_running_agents,
    )

    response = client.get("/api/v1/projects/demo-project/phase")

    assert response.status_code == 200
    assert response.json() == {
        "slug": "demo-project",
        "phase": "research_active",
        "topBlocker": "Waiting on approval",
        "nextAction": "Review pending approvals",
        "auditors": {"planner": {"status": "ready"}},
        "activeSessions": 1,
        "openTasks": 3,
        "snapshot": {
            "loaded": True,
            "path": "research_plan/state/control_plane_snapshot.json",
            "generatedAt": 1234567890,
            "version": 1,
        },
    }


def test_list_projects_catalog_includes_snapshot_progress(monkeypatch):
    import app.routers.projects as projects_router

    async def _query(path: str, payload: dict):
        assert path == "projects:list"
        return [
            {
                "_id": "project-1",
                "name": "Demo Project",
                "slug": "demo-project",
                "description": "Demo",
                "localRepoPath": "/tmp/demo-project",
                "gitRepoUrl": "https://example.com/demo.git",
                "status": "hydrated",
            }
        ]

    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router, "_manifest_metadata", lambda root, project: {})
    monkeypatch.setattr(projects_router, "_local_catalog_projects", lambda: [])
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review pending approvals",
                "taskCounts": {
                    "total": 5,
                    "byStatus": {"ready": 2, "running": 1, "done": 1, "cancelled": 1},
                },
            },
            "snapshot": {
                "loaded": True,
                "generatedAt": 1234567890,
                "path": "research_plan/state/control_plane_snapshot.json",
                "version": 1,
            },
        },
    )

    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["projects"]) == 1
    item = payload["projects"][0]
    assert item["progress"] == {"closed": 2, "total": 5}
    assert item["controlPlane"] == {
        "phase": "research_active",
        "nextAction": "Review pending approvals",
        "snapshotLoaded": True,
    }


def test_list_projects_catalog_includes_local_repo_only_projects(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    local_project = tmp_path / "generated_projects" / "demo-project"
    local_project.mkdir(parents=True, exist_ok=True)
    (local_project / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  description: Repo-only local project
  default_branch: main
hydration:
  default_pipeline: baseline-pipeline
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def _query(path: str, payload: dict):
        assert path == "projects:list"
        return []

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "read_control_plane_snapshot",
        lambda project: None,
    )

    response = client.get("/api/v1/projects")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["projects"]) == 1
    item = payload["projects"][0]
    assert item["slug"] == "demo-project"
    assert item["localExists"] is True
    assert item["manifestExists"] is True
    assert item["backendProject"]["_id"] == "local:demo-project"
    assert item["progress"] == {"closed": 0, "total": 0}
    assert item["controlPlane"]["snapshotLoaded"] is False


def test_activate_catalog_project_accepts_local_repo_only_project(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    local_project = tmp_path / "generated_projects" / "demo-project"
    local_project.mkdir(parents=True, exist_ok=True)
    (local_project / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  description: Repo-only local project
  default_branch: main
""".strip()
        + "\n",
        encoding="utf-8",
    )

    created_payloads: list[dict] = []
    reconcile_projects: list[dict] = []
    catalog_projects: list[dict] = []

    async def _query(path: str, payload: dict):
        if path == "projects:getBySlug":
            if payload["slug"] == "demo-project" and created_payloads:
                return {
                    "_id": "project-1",
                    "name": "Demo Project",
                    "slug": "demo-project",
                    "description": "Repo-only local project",
                    "localRepoPath": str(local_project),
                    "manifestPath": "rail.yaml",
                    "defaultBranch": "main",
                }
            return None
        if path == "projects:getById":
            return {
                "_id": payload["projectId"],
                "name": "Demo Project",
                "slug": "demo-project",
                "description": "Repo-only local project",
                "localRepoPath": str(local_project),
                "manifestPath": "rail.yaml",
                "defaultBranch": "main",
            }
        raise AssertionError(f"unexpected query: {path}")

    async def _mutation(path: str, payload: dict):
        assert path == "projects:create"
        created_payloads.append(payload)
        return "project-1"

    async def _catalog_row(project: dict):
        catalog_projects.append(project)
        return {"slug": project["slug"], "localExists": True, "snapshotLoaded": True}

    async def _reconcile_project_reality(project: dict):
        reconcile_projects.append(project)
        return {
            "persistedControlPlaneSnapshot": {
                "path": "research_plan/state/control_plane_snapshot.json",
                "loaded": True,
            },
            "hasChanges": False,
        }

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)
    monkeypatch.setattr(projects_router, "_catalog_row", _catalog_row)
    monkeypatch.setattr(projects_router, "ensure_project_boot", lambda root: {"ok": True})
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)

    response = client.post("/api/v1/projects/catalog/demo-project/activate", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["project"]["_id"] == "project-1"
    assert payload["catalogProject"]["slug"] == "demo-project"
    assert payload["catalogProject"]["snapshotLoaded"] is True
    assert payload["reconcile"]["persistedControlPlaneSnapshot"]["loaded"] is True
    assert created_payloads[0]["localRepoPath"] == str(local_project)
    assert "gitRepoUrl" not in created_payloads[0]
    assert "defaultBranch" not in created_payloads[0]
    assert len(reconcile_projects) == 1
    reconciled = reconcile_projects[0]
    assert reconciled["_id"] == "project-1"
    assert reconciled["slug"] == "demo-project"
    assert reconciled["name"] == "Demo Project"
    assert reconciled["description"] == "Repo-only local project"
    assert reconciled["localRepoPath"] == str(local_project)
    assert reconciled["manifestPath"] == "rail.yaml"
    assert reconciled["defaultBranch"] == "main"
    assert catalog_projects[0]["_id"] == "project-1"


def test_activate_catalog_project_updates_existing_project_without_approach_field(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    local_project = tmp_path / "generated_projects" / "demo-project"
    local_project.mkdir(parents=True, exist_ok=True)
    (local_project / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  description: Repo-only local project
  default_branch: main
""".strip()
        + "\n",
        encoding="utf-8",
    )

    update_payloads: list[dict] = []

    async def _query(path: str, payload: dict):
        if path == "projects:getBySlug":
            return {
                "_id": "project-1",
                "name": "Demo Project",
                "slug": "demo-project",
                "description": "Repo-only local project",
                "localRepoPath": str(local_project),
                "manifestPath": "rail.yaml",
            }
        raise AssertionError(f"unexpected query: {path}")

    async def _mutation(path: str, payload: dict):
        assert path == "projects:updateById"
        update_payloads.append(payload)
        return None

    async def _catalog_row(project: dict):
        return {"slug": project["slug"], "localExists": True}

    async def _reconcile_project_reality(project: dict):
        return {"persistedControlPlaneSnapshot": {"loaded": True}, "hasChanges": False}

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo Project",
            "slug": slug,
            "description": "Repo-only local project",
            "localRepoPath": str(local_project),
            "manifestPath": "rail.yaml",
        }

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)
    monkeypatch.setattr(projects_router, "_catalog_row", _catalog_row)
    monkeypatch.setattr(projects_router, "ensure_project_boot", lambda root: {"ok": True})
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)
    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    response = client.post("/api/v1/projects/catalog/demo-project/activate", json={})

    assert response.status_code == 200
    assert update_payloads[0]["projectId"] == "project-1"
    assert "approach" not in update_payloads[0]


def test_create_ontology_follow_up_task_endpoint_creates_expansion_task(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    synced: list[bool] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return []

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": "expand-task", "title": kwargs["title"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(projects_router.planner_service, "create_task", _create_task)
    monkeypatch.setattr(projects_router.planner_service, "sync_planner_files", _sync_planner_files)

    response = client.post(
        "/api/v1/projects/demo-project/command-center/ontology-follow-ups/expand",
        json={"title": "2. Which question requires expansion?", "classification": "requires_expansion"},
    )

    assert response.status_code == 200
    assert response.json()["created"] is True
    assert created[0]["title"] == "Expand ontology coverage for: 2. Which question requires expansion?"
    assert synced == [True]


def test_create_ontology_follow_up_task_endpoint_returns_existing_task(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {
                "_id": "existing-task",
                "title": "Resolve data blocker for: 3. Which source is missing?",
                "status": "ready",
            }
        ]

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)

    response = client.post(
        "/api/v1/projects/demo-project/command-center/ontology-follow-ups/expand",
        json={"title": "3. Which source is missing?", "classification": "blocked_by_data"},
    )

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert response.json()["task"]["_id"] == "existing-task"


def test_planner_control_plane_endpoint_returns_compact_live_snapshot(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg, session_id=None):
        return {"_id": "main", "name": "Main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "title": "Hydrate data", "status": "running"}]

    async def _list_approvals(project_arg):
        return [{"_id": "approval-1", "status": "pending"}]

    async def _list_project_running_agents(project_id: str, active_only: bool = False, limit: int = 20):
        return [{"_id": "sess-1", "status": "running", "role": "coding"}]

    async def _autopilot_status(slug: str):
        return {"enabled": True, "active": True, "autoApprove": False, "dispatchApprovalRequired": True}

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(projects_router.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(projects_router.running_agent_service, "list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr(projects_router, "get_autopilot_status", _autopilot_status)
    monkeypatch.setattr(projects_router.goal_service, "load_goal_bundle", lambda project: None)
    monkeypatch.setattr(projects_router, "_load_pending_dispatches", lambda project: [{"work_order_id": "wo-1"}])
    monkeypatch.setattr(projects_router, "_load_pending_qa", lambda project: [{"question_id": "qa-1", "question": "Need approval?"}])
    monkeypatch.setattr(projects_router, "_load_planner_decisions", lambda project, limit=50: [{"tool": "query_ontology"}])
    monkeypatch.setattr(projects_router, "_session_review_model", lambda project, session: {"reviewStatus": "pending"})
    monkeypatch.setattr(
        projects_router.command_center_service,
        "read_control_plane_snapshot",
        lambda project: {
            "snapshotVersion": 1,
            "generatedAt": 1234567890,
            "path": "research_plan/state/control_plane_snapshot.json",
            "commandCenter": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review pending approvals",
                "currentBlocker": "Snapshot blocker",
                "projectReality": {"hasDrift": True},
                "auditors": {"session": {"status": "blocked"}},
                "closeoutCertificate": {"status": "pending"},
                "missionBrief": {"current": "Now", "next": "Next"},
            },
        },
    )

    response = client.get("/api/v1/projects/demo-project/planner/control-plane")

    assert response.status_code == 200
    payload = response.json()
    assert payload["autopilot"]["enabled"] is True
    assert payload["board"]["tasks"][0]["title"] == "Hydrate data"
    assert payload["pendingDispatches"] == [{"work_order_id": "wo-1"}]
    assert payload["pendingQuestions"] == [{"question_id": "qa-1", "question": "Need approval?"}]
    assert payload["decisions"] == [{"tool": "query_ontology"}]
    assert payload["phase"] == "research_active"
    assert payload["currentBlocker"] == "Snapshot blocker"
    assert payload["projectReality"]["hasDrift"] is True
    assert payload["auditors"]["session"]["status"] == "blocked"
    assert payload["snapshot"]["loaded"] is True
    assert isinstance(payload["refreshedAt"], int)


def test_planner_home_endpoint_includes_snapshot_backed_control_plane(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo",
            "slug": slug,
            "status": "ready",
            "description": "Demo project",
            "gitRepoUrl": "https://github.com/example/demo",
            "defaultBranch": "main",
            "agentModel": "claude-opus-4-6",
            "githubSyncMode": "auto",
            "localRepoPath": "/tmp/demo-project",
        }

    async def _ensure_planner_thread(project_id: str):
        return "thread-1"

    async def _list_planner_messages(project_arg, *, thread_id: str, limit: int = 50):
        return [{"role": "user", "content": "hello"}]

    async def _ensure_main_board(project_arg):
        return {"_id": "main", "name": "Main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "title": "Hydrate data", "status": "running"}]

    async def _list_approvals(project_arg):
        return [{"_id": "approval-1", "status": "pending"}]

    async def _list_project_running_agents(project_id: str, active_only: bool = False, limit: int = 20):
        return [{"_id": "sess-1", "status": "running", "role": "coding"}]

    async def _autopilot_status(slug: str):
        return {"enabled": True, "active": True, "autoApprove": False, "dispatchApprovalRequired": True}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_planner_thread", _ensure_planner_thread)
    monkeypatch.setattr(projects_router.planner_service, "list_planner_messages", _list_planner_messages)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(projects_router.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(projects_router.planner_service, "project_root_from_record", lambda project: Path("/tmp/demo-project"))
    monkeypatch.setattr(projects_router.running_agent_service, "list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr(projects_router, "get_autopilot_status", _autopilot_status)
    monkeypatch.setattr(projects_router, "_session_review_model", lambda project, session: {"reviewStatus": "pending"})
    monkeypatch.setattr(projects_router, "_load_pending_dispatches", lambda project: [{"work_order_id": "wo-1"}])
    monkeypatch.setattr(projects_router, "_load_pending_qa", lambda project: [{"question_id": "qa-1", "question": "Need approval?"}])
    monkeypatch.setattr(projects_router, "_load_planner_decisions", lambda project, limit=50: [{"tool": "query_ontology"}])
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review pending approvals",
                "currentBlocker": "Snapshot blocker",
                "goal": {"objective": "Ship closeout", "phase": "repair"},
                "taskCounts": {"total": 4, "byStatus": {"ready": 2, "review": 1, "done": 1}},
                "recentArtifacts": [{"name": "paper.pdf", "path": "artifacts/paper.pdf"}],
                "sourceSummary": {"count": 3, "statusCounts": {"active": 3}},
                "skillSummary": {"count": 2, "agentRolesWithSkillAccess": ["research", "coding"]},
                "integritySummary": {
                    "staleArtifactCount": 1,
                    "sourceFreshnessCounts": {"fresh": 3},
                    "sourceAdmissibilityCounts": {"admissible": 3},
                    "agentWorkflow": {
                        "research": {"status": "ready", "requirements": []},
                        "data": {"status": "ready", "requirements": []},
                        "coding": {"status": "blocked", "requirements": ["verification"]},
                        "artifact": {"status": "ready", "requirements": []},
                        "health": {"status": "ready", "requirements": []},
                    },
                },
                "projectReality": {"hasDrift": True},
                "auditors": {"session": {"status": "blocked"}},
                "blockerSummary": {"blocked": True, "headline": "Snapshot blocker", "reasons": ["Need approval"], "repairs": []},
                "repairQueue": {"count": 1, "readyCount": 1, "runningCount": 0, "byStatus": {"ready": 1}, "tasks": []},
                "recommendedRepairTask": {"id": "task-2", "title": "Repair lineage", "status": "ready", "agentRole": "health"},
                "closeoutCertificate": {"status": "pending"},
                "missionBrief": {"current": "Now", "next": "Next"},
                "repoHealth": {"hasLocalRepo": True, "hasRailYaml": True, "hasResearchPlan": True},
            },
            "snapshot": {
                "loaded": True,
                "path": "research_plan/state/control_plane_snapshot.json",
                "generatedAt": 1234567890,
                "version": 1,
            },
        },
    )

    response = client.get("/api/v1/projects/demo-project/planner/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["planner"]["threadId"] == "thread-1"
    assert payload["planner"]["tasks"][0]["title"] == "Hydrate data"
    assert payload["project"]["description"] == "Demo project"
    assert payload["project"]["gitRepoUrl"] == "https://github.com/example/demo"
    assert payload["project"]["agentModel"] == "claude-opus-4-6"
    assert payload["repoHealth"] == {"hasLocalRepo": True, "hasRailYaml": True, "hasResearchPlan": True}
    assert payload["autopilot"]["enabled"] is True
    assert payload["pendingDispatches"] == [{"work_order_id": "wo-1"}]
    assert payload["pendingQuestions"] == [{"question_id": "qa-1", "question": "Need approval?"}]
    assert payload["decisions"] == [{"tool": "query_ontology"}]
    assert isinstance(payload["refreshedAt"], int)
    assert payload["controlPlane"]["phase"] == "research_active"
    assert payload["controlPlane"]["goal"]["objective"] == "Ship closeout"
    assert payload["controlPlane"]["taskCounts"]["total"] == 4
    assert payload["controlPlane"]["recentArtifacts"][0]["name"] == "paper.pdf"
    assert payload["controlPlane"]["sourceSummary"]["count"] == 3
    assert payload["controlPlane"]["skillSummary"]["count"] == 2
    assert payload["controlPlane"]["integritySummary"]["staleArtifactCount"] == 1
    assert payload["controlPlane"]["currentBlocker"] == "Snapshot blocker"
    assert payload["controlPlane"]["projectReality"]["hasDrift"] is True
    assert payload["controlPlane"]["blockerSummary"]["blocked"] is True
    assert payload["controlPlane"]["repairQueue"]["count"] == 1
    assert payload["controlPlane"]["recommendedRepairTask"]["title"] == "Repair lineage"
    assert payload["controlPlane"]["snapshot"]["loaded"] is True


def test_sync_project_metadata_updates_local_manifest_for_repo_only_project(monkeypatch, tmp_path):
    import app.routers.projects as projects_router
    import yaml

    project_root = tmp_path / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    manifest_path = project_root / "rail.yaml"
    manifest_path.write_text(
        """
version: 1
project:
  name: Demo Project
  slug: demo-project
  default_branch: main
  description: Old description
  mode: ontology_first
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
  planner_thread_mode: project
  default_planner_role: planner
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def _refresh_project_record(slug: str):
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        project_meta = raw.get("project") or {}
        return {
            "_id": f"local:{slug}",
            "name": project_meta.get("name") or "Demo Project",
            "slug": slug,
            "description": project_meta.get("description"),
            "defaultBranch": project_meta.get("default_branch") or "main",
            "gitRepoUrl": project_meta.get("git_repo_url"),
            "agentModel": project_meta.get("agent_model"),
            "localRepoPath": str(project_root),
            "manifestPath": "rail.yaml",
        }

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/sync-metadata",
        json={
            "name": "Updated Demo Project",
            "description": "New description",
            "gitRepoUrl": "https://github.com/example/demo-project",
            "defaultBranch": "develop",
            "agentModel": "claude-opus-4-6",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["name"] == "Updated Demo Project"
    assert payload["project"]["defaultBranch"] == "develop"
    assert payload["project"]["gitRepoUrl"] == "https://github.com/example/demo-project"
    assert payload["project"]["agentModel"] == "claude-opus-4-6"
    assert payload["publish"] is None

    manifest = manifest_path.read_text(encoding="utf-8")
    assert "name: Updated Demo Project" in manifest
    assert "description: New description" in manifest
    assert "default_branch: develop" in manifest
    assert "git_repo_url: https://github.com/example/demo-project" in manifest
    assert "agent_model: claude-opus-4-6" in manifest


def test_sync_project_metadata_prefers_repo_first_refresh_for_convex_project(monkeypatch):
    import app.routers.projects as projects_router

    updated_payloads: list[dict] = []

    async def _refresh_project_record(slug: str):
        assert slug == "demo-project"
        return {
            "_id": "project-1",
            "name": "Demo Project",
            "slug": slug,
            "status": "ready",
            "description": "Updated description",
            "defaultBranch": "develop",
        }

    async def _mutation(path: str, payload: dict):
        assert path == "projects:updateById"
        updated_payloads.append(payload)
        return None

    async def _query(path: str, payload: dict):
        if path == "projects:getById":
            raise AssertionError("sync_project_metadata should prefer planner_service refresh")
        raise AssertionError(path)

    async def _should_auto_publish(project: dict):
        return False

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(projects_router, "should_auto_publish", _should_auto_publish)

    response = client.post(
        "/api/v1/projects/demo-project/sync-metadata",
        json={"description": "Updated description", "defaultBranch": "develop"},
    )

    assert response.status_code == 200
    assert response.json()["project"]["description"] == "Updated description"
    assert updated_payloads[0]["projectId"] == "project-1"


def test_register_artifacts_accepts_local_repo_only_project_with_explicit_paths(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    hydration_meta = ontology_root / ".rail_hydration.json"
    onto_db.write_bytes(b"db")
    onto_duckdb.write_bytes(b"duck")
    hydration_meta.write_text('{"pipeline_slug":"default","hydration_mode":"full"}', encoding="utf-8")

    promoted: list[dict] = []

    async def _refresh_project_record(slug: str):
        return {
            "_id": f"local:{slug}",
            "slug": slug,
            "localRepoPath": str(tmp_path),
            "manifestPath": "rail.yaml",
        }

    async def _promote_project_hydration_artifact(**kwargs):
        promoted.append(kwargs)
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(
        projects_router,
        "promote_project_hydration_artifact",
        _promote_project_hydration_artifact,
    )
    monkeypatch.setattr(projects_router.ontology_service, "ensure_loaded_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(projects_router.sql_service, "set_path", lambda *args, **kwargs: None)

    response = client.post(
        "/api/v1/projects/demo-project/register-artifacts",
        json={"output_db_path": str(onto_db)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["jobId"] is None
    assert payload["activeOntologyDbPath"] == str(onto_db)
    assert payload["activeOntologyDuckdbPath"] == str(onto_duckdb)
    assert promoted[0]["project"]["_id"] == "local:demo-project"


def test_clear_hydration_for_local_repo_only_project_removes_metadata_not_artifacts(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    ontology_root = tmp_path / ".ontology"
    ontology_root.mkdir(parents=True, exist_ok=True)
    onto_db = ontology_root / "onto.db"
    onto_duckdb = ontology_root / "onto.duckdb"
    hydration_meta = ontology_root / ".rail_hydration.json"
    onto_db.write_bytes(b"db")
    onto_duckdb.write_bytes(b"duck")
    hydration_meta.write_text('{"pipeline_slug":"default","hydration_mode":"full"}', encoding="utf-8")

    async def _refresh_project_record(slug: str):
        return {
            "_id": f"local:{slug}",
            "slug": slug,
            "localRepoPath": str(tmp_path),
            "manifestPath": "rail.yaml",
        }

    async def _mutation(path: str, payload: dict):
        raise AssertionError(f"unexpected mutation {path}")

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.convex, "mutation", _mutation)

    response = client.post("/api/v1/projects/demo-project/clear-hydration")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "ok": True,
        "slug": "demo-project",
        "status": "ready",
        "mode": "local_repo",
    }
    assert onto_db.exists() is True
    assert onto_duckdb.exists() is True
    assert hydration_meta.exists() is False


def test_create_planner_task_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "almost_ready",
            "agentRole": "data",
        },
    )

    assert response.status_code == 422
    assert "Planner task status must be one of" in response.json()["detail"]


def test_project_phase_endpoint_prefers_repo_snapshot(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main", "name": "Main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {"_id": "task-1", "title": "Hydrate data", "status": "running"},
            {"_id": "task-2", "title": "Done task", "status": "done"},
        ]

    async def _list_project_running_agents(project_id: str, active_only: bool = True, limit: int = 50):
        return [{"_id": "sess-1", "status": "running", "role": "coding"}]

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "project_root_from_record", lambda project: Path("/tmp/demo-project"))
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(projects_router.running_agent_service, "list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "read_control_plane_snapshot",
        lambda project: {
            "snapshotVersion": 1,
            "generatedAt": 1234567890,
            "path": "research_plan/state/control_plane_snapshot.json",
            "commandCenter": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review pending approvals",
                "currentBlocker": "Snapshot blocker",
                "taskCounts": {"total": 5, "byStatus": {"ready": 2, "running": 1, "done": 1, "cancelled": 1}},
                "auditors": {"session": {"status": "blocked"}},
            },
        },
    )

    response = client.get("/api/v1/projects/demo-project/phase")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "research_active"
    assert payload["topBlocker"] == "Snapshot blocker"
    assert payload["nextAction"] == "Review pending approvals"
    assert payload["auditors"]["session"]["status"] == "blocked"
    assert payload["activeSessions"] == 1
    assert payload["openTasks"] == 3
    assert payload["snapshot"]["loaded"] is True


def test_sources_route_falls_back_to_control_plane_summary(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "list_project_sources",
        lambda project: (_ for _ in ()).throw(ValueError("boom")),
    )
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "sourceSummary": {
                    "count": 3,
                    "statusCounts": {"validated": 2, "candidate": 1},
                    "freshnessCounts": {"fresh": 3},
                    "admissibilityCounts": {"observed": 3},
                    "admissibilityHighlights": [],
                    "notesPath": "topics/source_notes.md",
                }
            },
            "snapshot": {"loaded": True},
        },
    )

    response = client.get("/api/v1/projects/demo-project/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == []
    assert payload["summary"]["count"] == 3
    assert payload["summary"]["statusCounts"] == {"validated": 2, "candidate": 1}


def test_integrity_route_falls_back_to_control_plane_summary(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(
        projects_router.command_center_service,
        "list_project_integrity",
        lambda project: (_ for _ in ()).throw(ValueError("boom")),
    )
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "recentArtifacts": [{"path": "artifacts/report.md"}],
                "sourceSummary": {
                    "count": 4,
                    "freshnessCounts": {"fresh": 4},
                },
                "integritySummary": {
                    "staleArtifactCount": 1,
                    "agentWorkflow": {
                        "research": {"status": "ready", "requirements": []},
                        "data": {"status": "blocked", "requirements": ["hydrate sources"]},
                        "coding": {"status": "ready", "requirements": []},
                        "artifact": {"status": "ready", "requirements": []},
                        "health": {"status": "ready", "requirements": []},
                    },
                    "hypothesisRanking": [{"id": "hyp-1", "computedScore": 0.9}],
                },
            },
            "snapshot": {"loaded": True},
        },
    )

    response = client.get("/api/v1/projects/demo-project/integrity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["indexes"]["sources"] == []
    assert payload["summary"]["sourceCount"] == 4
    assert payload["summary"]["artifactCount"] == 1
    assert payload["summary"]["staleArtifactCount"] == 1
    assert payload["agentWorkflow"]["data"]["status"] == "blocked"
    assert payload["hypothesisRanking"][0]["id"] == "hyp-1"


def test_project_context_endpoint_prefers_local_repo_sources_and_pipelines(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import app.routers.projects as projects_router
    import app.services.project_artifacts_service as project_artifacts_service

    (tmp_path / "rail.yaml").write_text("project:\n  slug: demo-project\n", encoding="utf-8")

    sources_dir = tmp_path / "assets" / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "census.yaml").write_text("name: Census API\n", encoding="utf-8")

    pipelines_dir = tmp_path / "assets" / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    (pipelines_dir / "baseline.yaml").write_text("name: Baseline pipeline\n", encoding="utf-8")

    async def _refresh_project_record(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo",
            "slug": slug,
            "status": "ready",
            "localRepoPath": str(tmp_path),
            "apiConfigSlugs": ["census"],
        }

    async def _query(path: str, payload: dict):
        raise AssertionError(f"unexpected convex query: {path}")

    async def _resolve(project_id: str):
        assert project_id == "project-1"
        return project_artifacts_service.ProjectArtifacts(
            project_id=project_id,
            db_path=str(tmp_path / "assets" / "onto.db"),
            owl_path=None,
            duckdb_path=str(tmp_path / "assets" / "onto.duckdb"),
            embeddings_path=str(tmp_path / "assets" / "embeddings.db"),
        )

    async def _run_with_ensure(slug: str, db_path: str, fn):
        return [{"id": "Observation", "label": "Observation"}]

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.convex, "query", _query)
    monkeypatch.setattr(project_artifacts_service, "resolve", _resolve)
    monkeypatch.setattr(projects_router.ontology_service, "_run_with_ensure", _run_with_ensure)
    monkeypatch.setattr(projects_router.sql_service, "set_path", lambda path: None)
    monkeypatch.setattr(projects_router.sql_service, "get_schema_ddl", lambda: "CREATE TABLE demo();")
    monkeypatch.setattr(
        projects_router,
        "load_manifest",
        lambda path: SimpleNamespace(
            hydration=SimpleNamespace(
                sources_dir="assets/sources",
                pipelines_dir="assets/pipelines",
                default_pipeline="baseline",
            )
        ),
    )
    monkeypatch.setattr(
        projects_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "hydration_ready",
                "nextAction": "Run hydration",
                "currentBlocker": None,
                "blockerSummary": {"blocked": False},
                "closeoutCertificate": {"status": "pending"},
                "missionBrief": {"current": "Current brief", "next": "Next brief"},
            },
            "snapshot": {"loaded": True, "path": "research_plan/state/control_plane_snapshot.json"},
        },
    )

    response = client.get("/api/v1/projects/demo-project/context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["slug"] == "demo-project"
    assert payload["ontology"] == {
        "classes": [{"id": "Observation", "label": "Observation"}],
        "schema_ddl": "CREATE TABLE demo();",
    }
    assert payload["data_sources"] == [{"slug": "census", "name": "Census API"}]
    assert payload["pipelines"] == [{"slug": "baseline", "name": "Baseline pipeline"}]


def test_update_planner_task_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"status": "almost_ready"},
    )

    assert response.status_code == 422
    assert "Planner task status must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_approval_state(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "backlog",
            "agentRole": "data",
            "approvalState": "approved-ish",
        },
    )

    assert response.status_code == 422
    assert "Planner task approval state must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_approval_state(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"approvalState": "approved-ish"},
    )

    assert response.status_code == 422
    assert "Planner task approval state must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_runner(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "backlog",
            "agentRole": "data",
            "runner": "magic_runner",
        },
    )

    assert response.status_code == 422
    assert "Planner task runner must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_runner(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"runner": "magic_runner"},
    )

    assert response.status_code == 422
    assert "Planner task runner must be one of" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_priority(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "backlog",
            "agentRole": "data",
            "priority": "urgent",
        },
    )

    assert response.status_code == 422
    assert "Planner task priority must be one of" in response.json()["detail"]


def test_update_planner_task_rejects_unknown_priority(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"priority": "urgent"},
    )

    assert response.status_code == 422
    assert "Planner task priority must be one of" in response.json()["detail"]


def test_update_planner_task_surfaces_planner_completion_gate_block(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _update_task(task_id: str, *, project: dict, **fields):
        raise ValueError(
            "Planner tasks cannot be marked done until planner completion checks pass: "
            "research_plan/current_plan.md missing or empty at /tmp/demo-project/research_plan/current_plan.md"
        )

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "update_task", _update_task)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"status": "done"},
    )

    assert response.status_code == 409
    assert "Planner tasks cannot be marked done until planner completion checks pass" in response.json()["detail"]


def test_update_planner_task_surfaces_worker_completion_gate_block(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _update_task(task_id: str, *, project: dict, **fields):
        raise ValueError(
            "Worker tasks cannot be marked done until a reviewed post-run audit exists for the task."
        )

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "update_task", _update_task)

    response = client.patch(
        "/api/v1/projects/demo-project/planner/tasks/task-1",
        json={"status": "done"},
    )

    assert response.status_code == 409
    assert "reviewed post-run audit exists" in response.json()["detail"]


def test_create_planner_task_rejects_unknown_agent_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Bad task",
            "description": "Should fail",
            "status": "backlog",
            "agentRole": "writer",
        },
    )

    assert response.status_code == 422
    assert "Planner task agent role must be one of" in response.json()["detail"]


def test_create_planner_task_normalizes_agent_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    synced: list[bool] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg, session_id=None):
        return {"_id": "main"}

    async def _create_task(**kwargs):
        created.append(kwargs)
        return {"_id": "task-1", "agentRole": kwargs["agent_role"], "status": kwargs["status"]}

    async def _sync_planner_files(project_arg, board):
        synced.append(True)
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "create_task", _create_task)
    monkeypatch.setattr(projects_router.planner_service, "sync_planner_files", _sync_planner_files)

    response = client.post(
        "/api/v1/projects/demo-project/planner/tasks",
        json={
            "title": "Alias task",
            "description": "Should normalize role alias",
            "status": "backlog",
            "agentRole": "developer",
        },
    )

    assert response.status_code == 200
    assert created[0]["agent_role"] == "coding"
    assert response.json()["agentRole"] == "coding"
    assert synced == [True]


def test_create_project_approval_rejects_unknown_status(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "approved-ish",
            "requestedByRole": "planner",
        },
    )

    assert response.status_code == 422
    assert "Approval status must be one of" in response.json()["detail"]


def test_create_project_approval_rejects_unknown_type(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_session",
            "status": "pending",
            "requestedByRole": "planner",
        },
    )

    assert response.status_code == 422
    assert "Approval type must be one of" in response.json()["detail"]


def test_create_project_approval_accepts_research_launch_type(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    wakes: list[str] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-launch"

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr("app.services.autopilot_service.trigger_wake", lambda slug: wakes.append(slug))

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "approvalType": "research_launch",
            "status": "pending",
            "requestedByRole": "planner",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"approvalId": "approval-launch"}
    assert created[0]["approval_type"] == "research_launch"
    assert wakes == ["demo-project"]


def test_create_project_approval_rejects_unknown_requested_by_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "pending",
            "requestedByRole": "writer",
        },
    )

    assert response.status_code == 422
    assert "Approval requestedByRole must be one of" in response.json()["detail"]


def test_create_project_approval_normalizes_requested_by_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    created: list[dict] = []
    wakes: list[str] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _create_approval(**kwargs):
        created.append(kwargs)
        return "approval-1"

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "create_approval", _create_approval)
    monkeypatch.setattr("app.services.autopilot_service.trigger_wake", lambda slug: wakes.append(slug))

    response = client.post(
        "/api/v1/projects/demo-project/approvals",
        json={
            "taskId": "task-1",
            "approvalType": "run_task",
            "status": "pending",
            "requestedByRole": "auditor",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"approvalId": "approval-1"}
    assert created[0]["requested_by_role"] == "health"
    assert wakes == ["demo-project"]


def test_create_runner_session_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "writer",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 422
    assert "Runner session role must be one of" in response.json()["detail"]


def test_create_runner_session_normalizes_role_aliases(monkeypatch):
    import app.routers.projects as projects_router
    from app.runners import session_lifecycle

    created: list[dict] = []
    polled: list[tuple[str, str]] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo", "defaultBranch": "develop"}

    async def _create_runner_session(**kwargs):
        created.append(kwargs)
        return {"convex_session_id": "sess-1", "status": "queued"}

    async def _poll_session_until_done(session_id: str, project_id: str | None = None):
        polled.append((session_id, str(project_id)))
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(session_lifecycle, "create_runner_session", _create_runner_session)
    monkeypatch.setattr(session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "developer",
            "agentRoleForSecrets": "auditor",
            "runnerName": "CODEX_CLI",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 200
    assert created[0]["role"] == "coding"
    assert created[0]["agent_role_for_secrets"] == "health"
    assert created[0]["runner_name"] == "codex_cli"
    assert polled == [("sess-1", "project-1")]


def test_create_runner_session_defaults_to_project_runner_policy(monkeypatch):
    import app.routers.projects as projects_router
    from app.runners import session_lifecycle

    created: list[dict] = []
    polled: list[tuple[str, str]] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo", "defaultBranch": "develop"}

    async def _create_runner_session(**kwargs):
        created.append(kwargs)
        return {"convex_session_id": "sess-1", "status": "queued"}

    async def _poll_session_until_done(session_id: str, project_id: str | None = None):
        polled.append((session_id, str(project_id)))
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(session_lifecycle, "create_runner_session", _create_runner_session)
    monkeypatch.setattr(session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "coding",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 200
    assert created[0]["runner_name"] == "default"
    assert created[0]["branch"] == "develop"
    assert polled == [("sess-1", "project-1")]


def test_create_runner_session_allows_local_project_without_git_repo_url(monkeypatch):
    import app.routers.projects as projects_router
    from app.runners import session_lifecycle

    created: list[dict] = []
    polled: list[tuple[str, str]] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "defaultBranch": "develop"}

    async def _create_runner_session(**kwargs):
        created.append(kwargs)
        return {"convex_session_id": "sess-1", "status": "queued"}

    async def _poll_session_until_done(session_id: str, project_id: str | None = None):
        polled.append((session_id, str(project_id)))
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(session_lifecycle, "create_runner_session", _create_runner_session)
    monkeypatch.setattr(session_lifecycle, "poll_session_until_done", _poll_session_until_done)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "coding",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 200
    assert created[0]["repo_url"] == ""
    assert created[0]["branch"] == "develop"
    assert polled == [("sess-1", "project-1")]


def test_create_runner_session_rejects_unknown_secret_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "data",
            "agentRoleForSecrets": "writer",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 422
    assert "Runner agentRoleForSecrets must be one of" in response.json()["detail"]


def test_create_runner_session_rejects_unknown_runner(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project", "gitRepoUrl": "https://github.com/example/repo"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/runner/sessions",
        json={
            "role": "data",
            "runnerName": "writerbot",
            "taskDescription": "Run analysis",
        },
    )

    assert response.status_code == 422
    assert "Runner session runnerName must be one of" in response.json()["detail"]


def test_append_planner_message_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/messages",
        json={
            "role": "narrator",
            "content": "hello",
        },
    )

    assert response.status_code == 422
    assert "Planner message role must be one of" in response.json()["detail"]


def test_append_planner_message_normalizes_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    appended: list[dict] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_planner_thread(project_id: str):
        return "planner"

    async def _append_planner_message(**kwargs):
        appended.append(kwargs)
        return None

    async def _list_planner_messages(project_arg, thread_id: str = "planner", limit: int = 200):
        return [{"role": "research", "content": "hello", "messageType": "chat"}]

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_planner_thread", _ensure_planner_thread)
    monkeypatch.setattr(projects_router.planner_service, "append_planner_message", _append_planner_message)
    monkeypatch.setattr(projects_router.planner_service, "list_planner_messages", _list_planner_messages)

    response = client.post(
        "/api/v1/projects/demo-project/planner/messages",
        json={
            "role": "researcher",
            "content": "hello",
        },
    )

    assert response.status_code == 200
    assert appended[0]["role"] == "research"


def test_worker_update_planner_rejects_unknown_role(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/planner/worker-update",
        json={
            "role": "narrator",
            "message": "done",
        },
    )

    assert response.status_code == 422
    assert "Worker update role must be one of" in response.json()["detail"]


def test_worker_update_planner_normalizes_role_alias(monkeypatch):
    import app.routers.projects as projects_router

    appended: list[dict] = []
    wakes: list[str] = []

    async def _refresh_project_record(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _append_planner_message(**kwargs):
        appended.append(kwargs)
        return None

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "append_planner_message", _append_planner_message)
    monkeypatch.setattr("app.services.autopilot_service.trigger_wake", lambda slug: wakes.append(slug))

    response = client.post(
        "/api/v1/projects/demo-project/planner/worker-update",
        json={
            "role": "auditor",
            "message": "done",
        },
    )

    assert response.status_code == 200
    assert appended[0]["role"] == "health"
    assert wakes == ["demo-project"]


def test_autopilot_status_revives_desired_loop(monkeypatch):
    called: list[str] = []

    async def _ensure_autopilot_running(slug: str):
        called.append(slug)
        return {"desired_enabled": True, "active": False, "auto_approve": True}

    monkeypatch.setattr("app.services.autopilot_service.ensure_autopilot_running", _ensure_autopilot_running)

    response = client.get("/api/v1/projects/demo-project/autopilot/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "active": False,
        "autoApprove": True,
        "dispatchApprovalRequired": False,
    }
    assert called == ["demo-project"]


def test_project_phase_uses_active_only_running_sessions(monkeypatch):
    import app.routers.projects as projects_router

    called: list[dict] = []
    root_path = "/tmp/demo-project"

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": root_path}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return []

    async def _list_project_running_agents(project_id: str, *, active_only: bool = False, limit: int = 50):
        called.append({"project_id": project_id, "active_only": active_only, "limit": limit})
        return []

    async def _build_auditor_statuses(project, *, tasks=None, active_sessions=None):
        return {
            "session": {"status": "ready", "blockers": []},
            "planner": {"status": "ready", "blockers": []},
            "ontology": {"status": "ready", "blockers": []},
            "integrity": {"status": "ready", "blockers": []},
            "closeout": {"status": "ready", "blockers": []},
        }

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr("app.services.running_agent_service.list_project_running_agents", _list_project_running_agents)
    monkeypatch.setattr(projects_router, "build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr(projects_router, "load_manifest", lambda root: None)
    monkeypatch.setattr(projects_router, "_infer_lifecycle_phase", lambda *args, **kwargs: "brief")
    monkeypatch.setattr(projects_router, "_recommend_next_action", lambda *args, **kwargs: "Proceed")

    response = client.get("/api/v1/projects/demo-project/phase")

    assert response.status_code == 200
    assert called == [{"project_id": "project-1", "active_only": True, "limit": 50}]


def test_next_best_action_endpoint_prefers_repo_first_refresh(monkeypatch):
    import app.routers.projects as projects_router

    async def _refresh_project_record(slug: str):
        assert slug == "demo-project"
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _ensure_main_board(project_arg):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [{"_id": "task-1", "title": "Hydrate data", "status": "ready"}]

    async def _evaluate_lifecycle(project_arg, tasks):
        assert project_arg["_id"] == "project-1"
        assert tasks[0]["_id"] == "task-1"
        return {"phase": "research_active", "nextAction": "Hydrate data"}

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(projects_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(projects_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr("app.services.lifecycle_service.evaluate_lifecycle", _evaluate_lifecycle)

    response = client.get("/api/v1/projects/demo-project/next-best-action")

    assert response.status_code == 200
    assert response.json() == {"phase": "research_active", "nextAction": "Hydrate data"}
