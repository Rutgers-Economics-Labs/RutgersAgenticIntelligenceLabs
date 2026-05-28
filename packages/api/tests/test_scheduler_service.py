from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_scheduler_tick_uses_repo_first_project_lookup(monkeypatch):
    from app.services.scheduler_service import SchedulerService
    import app.services.scheduler_service as scheduler_service

    updates: list[tuple[str, dict]] = []

    async def _query(path: str, payload: dict):
        if path == "schedules:listActive":
            return [
                {
                    "_id": "schedule-1",
                    "projectSlug": "demo-project",
                    "pipelineSlug": "demo-pipeline",
                    "nextRunAt": 0,
                    "cron": None,
                }
            ]
        raise AssertionError(path)

    async def _mutation(path: str, payload: dict):
        updates.append((path, payload))
        return {"ok": True}

    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {"_id": "local:demo-project", "slug": "demo-project"}

    async def _trigger_job(pipeline_slug: str, project_id: str | None = None):
        assert pipeline_slug == "demo-pipeline"
        assert project_id == "demo-project"
        return {"jobId": "job-123", "status": "queued"}

    monkeypatch.setattr(scheduler_service.convex, "query", _query)
    monkeypatch.setattr(scheduler_service.convex, "mutation", _mutation)
    monkeypatch.setattr(scheduler_service.planner_service, "resolve_project_reference", _resolve_project_reference)
    monkeypatch.setattr("app.routers.jobs._trigger_job", _trigger_job)

    scheduler = SchedulerService()
    await scheduler._tick()

    assert updates[-1][0] == "schedules:update"
    assert updates[-1][1]["lastJobId"] == "job-123"
