"""Tests for GET /projects/{slug}/reality control-plane endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from rail.bootstrap import bootstrap_future_project


@pytest.mark.asyncio
async def test_get_project_reality_returns_lane_and_auditors(tmp_path, monkeypatch):
    from app.routers import projects as projects_router

    root = bootstrap_future_project(tmp_path, name="Reality API", slug="reality-api")
    project = {"_id": "proj-1", "slug": "reality-api", "localRepoPath": str(root)}

    async def _refresh_project_record(slug: str):
        assert slug == "reality-api"
        return project

    monkeypatch.setattr(projects_router, "_refresh_project_record", _refresh_project_record)
    monkeypatch.setattr(
        "app.services.reconciliation_service.running_agent_service.list_project_running_agents",
        AsyncMock(return_value=[]),
    )

    payload = await projects_router.get_project_reality("reality-api")

    assert payload["lane"]["available"] is True
    assert payload["lane"]["policy"] == "single_active_worker"
    assert payload["reality"]["hasDrift"] is False
    assert "session" in payload["auditors"]
    assert "closeout" in payload["auditors"]
