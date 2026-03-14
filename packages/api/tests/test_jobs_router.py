"""
Tests for /api/v1/jobs routes.
Convex calls and hydration_worker.run are mocked.
"""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio

PIPELINE_DOC = {
    "_id": "pipeline-id-123",
    "slug": "nj-hydration",
    "content": "ontology: core.yaml\nsteps: []\n",
    "referencedApiSlugs": ["census_states"],
}


async def test_trigger_job_queued(client, convex_mock):
    call_count = 0

    def query_side_effect(request):
        nonlocal call_count
        body = request.content
        call_count += 1
        # First call: getPipeline → return pipeline doc
        # Subsequent calls (getApi per slug): return api config
        if call_count == 1:
            return httpx.Response(200, json={"value": PIPELINE_DOC})
        return httpx.Response(200, json={"value": {"slug": "census_states", "content": "name: census_states\n"}})

    convex_mock.post("/api/query").mock(side_effect=query_side_effect)
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": {"jobId": "job-abc"}})
    )

    with patch("app.services.hydration_worker.run", new=AsyncMock()):
        resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "nj-hydration"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["jobId"] == "job-abc"
    assert body["status"] == "queued"


async def test_trigger_job_pipeline_not_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": None})
    )
    resp = await client.post("/api/v1/jobs", json={"pipeline_slug": "does-not-exist"})
    assert resp.status_code == 404


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
