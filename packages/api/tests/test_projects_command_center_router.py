from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_command_center_reconcile_endpoint_returns_repair_summary(monkeypatch):
    import app.routers.projects as projects_router

    async def _get_project_by_slug(slug: str):
        return {"_id": "project-1", "slug": slug, "localRepoPath": "/tmp/demo-project"}

    async def _reconcile_project_reality(project: dict):
        return {
            "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
            "updatedTaskIds": ["task-1"],
            "repairedSessionIds": ["sess-1"],
            "repairedAuditSessionIds": ["sess-2"],
            "hasChanges": True,
        }

    monkeypatch.setattr(projects_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(projects_router.reconciliation_service, "reconcile_project_reality", _reconcile_project_reality)

    response = client.post("/api/v1/projects/demo-project/command-center/reconcile")

    assert response.status_code == 200
    assert response.json() == {
        "removedTaskFiles": ["research_plan/tasks/duplicate.md"],
        "updatedTaskIds": ["task-1"],
        "repairedSessionIds": ["sess-1"],
        "repairedAuditSessionIds": ["sess-2"],
        "hasChanges": True,
    }
