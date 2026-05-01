from __future__ import annotations

import json

import httpx
import pytest

from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo

pytestmark = pytest.mark.asyncio


async def test_patch_assumption_returns_rerun_plan(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "study-period",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/assumptions/study-period",
        json={"value": "2012-2024", "notes": "Updated analysis window"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["assumption"]["value"] == "2012-2024"
    assert payload["rerunPlan"]["affectedPaths"] == ["artifacts/report.md"]


async def test_apply_rerun_plan_creates_tasks(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "study-period",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/rerun-plan/apply",
        json={"assumptionKey": "study-period"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["tasks"]) >= 2
