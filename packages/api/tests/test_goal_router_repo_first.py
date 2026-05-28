from __future__ import annotations

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
                "",
                "agents:",
                '  roles_dir: "agents"',
                '  default_runner: "codex_cli"',
                "  sequential_execution: true",
                '  planner_thread_mode: "project"',
                '  default_planner_role: "planner"',
            ]
        ),
        encoding="utf-8",
    )


def test_goal_contract_endpoint_prefers_repo_first_refresh(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    for name in ("topics", "specs", "agents", "skills", "artifacts"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    _write_manifest(tmp_path)

    async def _refresh_project_record(slug: str):
        assert slug == "demo-project"
        return {
            "_id": "local:demo-project",
            "name": "Demo",
            "slug": slug,
            "description": "Demo goal mode project",
            "localRepoPath": str(tmp_path),
        }

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.post(
        "/api/v1/projects/demo-project/goal",
        json={
            "objective": "Explain how weather shocks affect prices.",
            "successCriteria": [
                "hydrated ontology exists",
                "closeout audit passes",
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["phase"] == "scoped"
    assert (tmp_path / ".rail" / "goal" / "goal.md").exists()


def test_get_project_goal_prefers_repo_first_refresh(monkeypatch, tmp_path):
    import app.routers.projects as projects_router

    (tmp_path / "research_plan" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".ontology" / "sources").mkdir(parents=True, exist_ok=True)
    for name in ("topics", "specs", "agents", "skills", "artifacts"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    _write_manifest(tmp_path)

    project = {
        "_id": "local:demo-project",
        "name": "Demo",
        "slug": "demo-project",
        "description": "Demo goal mode project",
        "localRepoPath": str(tmp_path),
    }
    goal_service.create_goal_contract(
        project,
        {
            "objective": "Test goal",
            "successCriteria": ["closeout audit passes"],
        },
    )

    async def _refresh_project_record(slug: str):
        assert slug == "demo-project"
        return dict(project)

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)

    response = client.get("/api/v1/projects/demo-project/goal")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"]["objective"] == "Test goal"
