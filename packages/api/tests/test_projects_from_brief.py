from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


async def test_preview_from_brief_returns_preview(client):
    response = await client.post("/api/v1/projects/from-brief/preview", json={"brief": "Research objective: estimate housing affordability trends using ACS and FRED."})
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["slug"]
    assert "repoFiles" in body
    assert "sourceCandidates" in body


async def test_create_from_brief_writes_project_and_skips_hydration(client, tmp_path):
    preview = {
        "briefHash": "abc123",
        "project": {"name": "Grid Costs", "slug": "grid-costs", "description": "Research kickoff", "approach": "ontology-first"},
        "researchGraph": {"title": "Grid Costs", "objective": "Understand costs", "methods": ["regression"], "deliverables": ["report"]},
        "sourceCandidates": [
            {
                "slug": "grid-costs-fred-unrate",
                "name": "Unemployment Rate",
                "provider": "fred",
                "externalId": "UNRATE",
                "description": "Test source",
                "readiness": "ready",
                "reason": "Registry match",
                "configKind": "api",
                "content": "name: grid-costs-fred-unrate\ntype: api\nurl: https://api.stlouisfed.org/fred/series/observations\nresponse_format: json\nfields:\n  - source: observations[].date\n    alias: date\n  - source: observations[].value\n    alias: value\n",
            }
        ],
        "ontology": {
            "name": "Grid Costs Ontology",
            "slug": "grid-costs-ontology",
            "content": "uri: http://rail.rutgers.edu/ontology/grid-costs\nclasses:\n  - name: Observation\ndata_properties: []\nobject_properties: []\n",
            "parsedSpec": {"uri": "http://rail.rutgers.edu/ontology/grid-costs", "classes": [{"name": "Observation"}], "data_properties": [], "object_properties": []},
        },
        "pipeline": {
            "name": "Grid Costs Pipeline",
            "slug": "grid-costs-pipeline",
            "content": "name: grid-costs-pipeline\nontology: grid-costs-ontology\nsteps:\n  - name: load_grid_costs_fred_unrate\n    api: grid-costs-fred-unrate\n    class: Observation\n    uri: http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}\n",
            "parsedSpec": {"name": "grid-costs-pipeline", "ontology": "grid-costs-ontology", "steps": [{"name": "load_grid_costs_fred_unrate", "api": "grid-costs-fred-unrate", "class": "Observation", "uri": "http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}"}]},
            "referencedApiSlugs": ["grid-costs-fred-unrate"],
        },
        "repoFiles": [
            {"path": "specs/research_question.yaml", "content": "title: Grid Costs\n"},
            {"path": "research_plan/graph/summary.yaml", "content": "title: Grid Costs\n"},
        ],
        "readiness": {"ready": 1, "draft_for_review": 0, "missing_auth_or_manual": 0},
    }
    project_record = {
        "_id": "project-1",
        "name": "Grid Costs",
        "slug": "grid-costs",
        "description": "Research kickoff",
        "status": "ready_for_hydration_review",
        "localRepoPath": str(tmp_path / "grid-costs"),
        "githubSyncMode": "manual",
    }
    mutation = AsyncMock(side_effect=["project-1", "api-id", "ontology-id", "pipeline-id", None])
    query = AsyncMock(side_effect=[None, project_record, project_record])

    with patch("app.routers.projects.build_preview", new=AsyncMock(return_value=preview)), \
         patch("app.routers.projects.convex.mutation", new=mutation), \
         patch("app.routers.projects.convex.query", new=query), \
         patch("app.routers.projects._git_init", return_value=None), \
         patch("app.routers.projects.planner_service.ensure_planner_thread", new=AsyncMock(return_value="planner")), \
         patch("app.routers.projects.planner_service.ensure_main_board", new=AsyncMock(return_value={"_id": "board-1"})), \
         patch("app.routers.projects.planner_service.append_planner_message", new=AsyncMock()), \
         patch("app.routers.projects.planner_service.sync_planner_files", new=AsyncMock()), \
         patch("app.routers.projects.should_auto_publish", new=AsyncMock(return_value=False)):
        response = await client.post("/api/v1/projects/from-brief/create", json={
            "brief": "Research brief",
            "targetDir": str(tmp_path / "grid-costs"),
        })

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["slug"] == "grid-costs"
    assert body["hydrationReady"] is True
    assert body["nextAction"].lower().startswith("review")
