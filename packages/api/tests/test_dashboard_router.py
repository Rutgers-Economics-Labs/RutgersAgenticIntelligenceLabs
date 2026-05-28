from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_get_dashboard_uses_repo_first_project_resolution(monkeypatch, tmp_path):
    import app.routers.dashboard as dashboard_router

    project_root = tmp_path / "demo-project"
    research_root = project_root / "research"
    research_root.mkdir(parents=True, exist_ok=True)
    (research_root / "dashboard_panels.json").write_text(
        json.dumps([{"id": "overview", "title": "Overview", "html": "<div>ok</div>"}]),
        encoding="utf-8",
    )

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "local:demo-project",
            "name": "Demo Project",
            "slug": slug,
            "localRepoPath": str(project_root),
        }

    monkeypatch.setattr(dashboard_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(
        dashboard_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "research_active",
                "nextAction": "Review dashboard figures",
                "currentBlocker": None,
                "repoHealth": {
                    "hasLocalRepo": True,
                    "hasRailYaml": True,
                    "hasResearchPlan": True,
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

    response = client.get("/api/v1/projects/demo-project/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectName"] == "Demo Project"
    assert payload["controlPlane"] == {
        "phase": "research_active",
        "nextAction": "Review dashboard figures",
        "currentBlocker": None,
        "snapshot": {
            "loaded": True,
            "path": "research_plan/state/control_plane_snapshot.json",
            "generatedAt": 1234567890,
            "version": 1,
        },
    }
    assert payload["repoHealth"] == {
        "hasLocalRepo": True,
        "hasRailYaml": True,
        "hasResearchPlan": True,
    }


def test_generate_dashboard_returns_curated_panels_for_repo_only_project(monkeypatch, tmp_path):
    import app.routers.dashboard as dashboard_router

    project_root = tmp_path / "demo-project"
    research_root = project_root / "research"
    research_root.mkdir(parents=True, exist_ok=True)
    (research_root / "dashboard_panels.json").write_text(
        json.dumps([{"id": "overview", "title": "Overview", "html": "<div>ok</div>"}]),
        encoding="utf-8",
    )

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "local:demo-project",
            "name": "Demo Project",
            "slug": slug,
            "localRepoPath": str(project_root),
        }

    monkeypatch.setattr(dashboard_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(
        dashboard_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "lifecyclePhase": "ontology_healthy",
                "nextAction": "Generate dashboard panels",
                "currentBlocker": None,
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

    response = client.post("/api/v1/projects/demo-project/dashboard/generate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["projectName"] == "Demo Project"
    assert payload["panels"][0]["id"] == "overview"
    assert payload["controlPlane"]["phase"] == "ontology_healthy"
    assert payload["repoHealth"]["hasLocalRepo"] is True
