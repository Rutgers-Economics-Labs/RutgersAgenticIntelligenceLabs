"""
Tests for /api/v1/jobs routes.
Convex calls and hydration_worker.run are mocked.
"""
import json

import pytest
import httpx
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio

CENSUS_STATES_API_YAML = """
name: census_states
type: csv
path: sources/states.csv
fields:
  - source: id
    alias: id
  - source: name
    alias: name
"""

PIPELINE_CONTENT = """
ontology: core
steps:
  - name: load_states
    api: census_states
    class: State
    uri: "State_{id}"
    properties:
      hasName: "{name}"
"""

PIPELINE_DOC = {
    "_id": "pipeline-id-123",
    "slug": "nj-hydration",
    "content": PIPELINE_CONTENT,
    "referencedApiSlugs": ["census_states"],
    "parsedSpec": {
        "ontology": "core",
        "steps": [
            {
                "name": "load_states",
                "api": "census_states",
                "class": "State",
                "uri": "State_{id}",
                "properties": {"hasName": "{name}"},
            }
        ],
    },
}


def _convex_query_dispatch(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    path = payload.get("path")
    if path == "configs:getPipeline":
        return httpx.Response(200, json={"value": PIPELINE_DOC})
    if path == "configs:getApi":
        return httpx.Response(
            200,
            json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
        )
    if path == "configs:getOntology":
        return httpx.Response(200, json={"value": None})
    return httpx.Response(200, json={"value": None})


async def test_trigger_job_queued(client, convex_mock):
    convex_mock.post("/api/query").mock(side_effect=_convex_query_dispatch)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": {"jobId": "job-abc"}})
    )

    with patch("app.services.hydration_worker.run", new=AsyncMock()):
        resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "nj-hydration"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["jobId"] == "job-abc"
    assert body["status"] == "queued"


async def test_trigger_job_repo_only_project_persists_slug_and_local_id(client, convex_mock, monkeypatch):
    captured_mutation_args: dict | None = None

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {"_id": "local:demo-project", "slug": "demo-project", "localRepoPath": "/tmp/demo-project"}

    def mutation_dispatch(request: httpx.Request) -> httpx.Response:
        nonlocal captured_mutation_args
        payload = json.loads(request.content.decode())
        if payload.get("path") == "jobs:create":
            captured_mutation_args = payload.get("args")
            return httpx.Response(200, json={"value": {"jobId": "job-local"}})
        return httpx.Response(200, json={"value": {}})

    monkeypatch.setattr("app.routers.jobs.planner_service.get_project_by_slug", _get_project_by_slug)
    convex_mock.post("/api/query").mock(side_effect=_convex_query_dispatch)
    convex_mock.post("/api/mutation").mock(side_effect=mutation_dispatch)

    with patch("app.services.hydration_worker.run", new=AsyncMock()):
        resp = await client.post(
            "/api/v1/jobs",
            json={"pipeline_slug": "nj-hydration", "project_id": "local:demo-project"},
        )

    assert resp.status_code == 200
    assert resp.json()["jobId"] == "job-local"
    assert captured_mutation_args is not None
    assert captured_mutation_args["projectSlug"] == "demo-project"
    assert captured_mutation_args["projectId"] == "local:demo-project"


async def test_trigger_job_missing_job_id_returns_500(client, convex_mock):
    """Regression: empty Convex mutation value must not start hydration with job_id=None."""
    convex_mock.post("/api/query").mock(side_effect=_convex_query_dispatch)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": {}})
    )

    with patch("app.services.hydration_worker.run", new=AsyncMock()) as run_mock:
        resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "nj-hydration"})

    assert resp.status_code == 500
    run_mock.assert_not_called()


async def test_trigger_job_pipeline_not_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": None})
    )
    resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "does-not-exist"})
    assert resp.status_code == 404


async def test_trigger_job_validation_failure(client, convex_mock):
    bad_pipeline = {
        **PIPELINE_DOC,
        "content": """
ontology: core
steps:
  - name: load_states
    api: census_states
    class: NotARealClass
    uri: "X_{id}"
""",
        "parsedSpec": {
            "ontology": "core",
            "steps": [
                {
                    "name": "load_states",
                    "api": "census_states",
                    "class": "NotARealClass",
                    "uri": "X_{id}",
                }
            ],
        },
    }

    def dispatch(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        path = payload.get("path")
        if path == "configs:getPipeline":
            return httpx.Response(200, json={"value": bad_pipeline})
        if path == "configs:getApi":
            return httpx.Response(
                200,
                json={"value": {"slug": "census_states", "content": CENSUS_STATES_API_YAML}},
            )
        if path == "configs:getOntology":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=dispatch)

    resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "nj-hydration"})
    assert resp.status_code == 422
    err = resp.json()
    assert "detail" in err
    assert any("NotARealClass" in str(x) for x in err["detail"])


async def test_list_jobs(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": [
            {"_id": "j1", "pipelineSlug": "nj", "status": "success", "createdAt": 1000, "stepResults": []}
        ]})
    )
    resp = await client.get("/api/v1/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "success"


async def test_list_jobs_normalizes_repo_only_project_slug(client, convex_mock, monkeypatch):
    captured_query_args: dict | None = None

    async def _get_project_by_slug(slug: str):
        assert slug == "demo-project"
        return {"_id": "local:demo-project", "slug": "demo-project"}

    def dispatch(request: httpx.Request) -> httpx.Response:
        nonlocal captured_query_args
        payload = json.loads(request.content.decode())
        if payload.get("path") == "jobs:listByProject":
            captured_query_args = payload.get("args")
            return httpx.Response(200, json={"value": []})
        return httpx.Response(200, json={"value": None})

    monkeypatch.setattr("app.routers.jobs.planner_service.get_project_by_slug", _get_project_by_slug)
    convex_mock.post("/api/query").mock(side_effect=dispatch)

    resp = await client.get("/api/v1/jobs", params={"projectId": "local:demo-project"})

    assert resp.status_code == 200
    assert captured_query_args == {"projectSlug": "demo-project", "limit": 50}


async def test_get_job_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": {"_id": "j1", "status": "running"}})
    )
    resp = await client.get("/api/v1/jobs/j1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


async def test_get_job_not_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": None})
    )
    resp = await client.get("/api/v1/jobs/missing")
    assert resp.status_code == 404


async def test_get_job_logs(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": [
            {"seq": 1, "level": "info", "message": "Starting", "timestamp": 1000}
        ]})
    )
    resp = await client.get("/api/v1/jobs/j1/logs")
    assert resp.status_code == 200
    logs = resp.json()
    assert logs[0]["message"] == "Starting"


async def test_cancel_job(client, convex_mock):
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": {}})
    )
    resp = await client.delete("/api/v1/jobs/j1")
    assert resp.status_code == 200
