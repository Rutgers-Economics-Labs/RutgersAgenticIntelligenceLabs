from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_zen_route_prefers_repo_backed_control_plane_summary(client, monkeypatch, tmp_path):
    import app.routers.zen as zen_router

    project_root = tmp_path / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "research_plan").mkdir(parents=True, exist_ok=True)

    async def _get_project_by_slug(slug: str):
        return {
            "_id": "project-1",
            "name": "Demo Project",
            "slug": slug,
            "status": "hydrated",
            "localRepoPath": str(project_root),
        }

    async def _find_active_worker(project_id: str):
        return None

    async def _ensure_main_board(project: dict):
        return {"_id": "main"}

    async def _list_tasks(board_id: str, *, project=None):
        return [
            {"_id": "task-1", "title": "Hydrate source graph", "status": "ready"},
            {"_id": "task-2", "title": "Publish report", "status": "awaiting_approval"},
            {"_id": "task-3", "title": "Archive notes", "status": "done"},
        ]

    async def _list_approvals(project: dict):
        return [{"_id": "approval-1", "status": "pending", "approvalType": "task execution"}]

    async def _list_decision_events(project: dict, status: str = "open"):
        return []

    monkeypatch.setattr(zen_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(zen_router.running_agent_service, "find_active_worker", _find_active_worker)
    monkeypatch.setattr(zen_router.planner_service, "ensure_main_board", _ensure_main_board)
    monkeypatch.setattr(zen_router.planner_service, "list_tasks", _list_tasks)
    monkeypatch.setattr(zen_router.planner_service, "list_approvals", _list_approvals)
    monkeypatch.setattr(zen_router, "list_decision_events", _list_decision_events)
    monkeypatch.setattr(
        zen_router.command_center_service,
        "load_control_plane_summary",
        lambda project: {
            "summary": {
                "currentPlan": {"summary": "Finish the repo-first closeout path."},
                "lifecyclePhase": "research_active",
                "currentBlocker": "Need artifact verification",
                "blockerSummary": {"blocked": True},
                "recentArtifacts": [
                    {
                        "name": "paper.pdf",
                        "path": "artifacts/paper.pdf",
                        "promotionState": "verified",
                        "verificationStatus": "passed",
                    }
                ],
            },
            "snapshot": {"loaded": True},
        },
    )
    monkeypatch.setattr(
        zen_router,
        "load_integrity_indexes",
        lambda project_root: (_ for _ in ()).throw(ValueError("integrity unavailable")),
    )
    monkeypatch.setattr(
        zen_router,
        "list_project_artifacts",
        lambda project: (_ for _ in ()).throw(AssertionError("artifact fallback should come from control-plane summary")),
    )

    response = await client.get("/api/v1/projects/demo-project/zen")

    assert response.status_code == 200
    payload = response.json()
    assert payload["objective"] == "Finish the repo-first closeout path."
    assert payload["project"]["phase"] == "research_active"
    assert payload["project"]["health"] == "Blocked"
    assert payload["artifacts"][0]["name"] == "paper.pdf"
    assert payload["nextDecision"]["prompt"] == "Approval needed for task execution"
    assert payload["plan"]["now"] == ["Hydrate source graph"]
    assert payload["plan"]["next"] == ["Publish report"]
    assert payload["plan"]["done"] == ["Archive notes"]
