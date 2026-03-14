"""
Tests for /api/v1/configs routes — CRUD proxied to Convex + validation endpoint.
Convex HTTP calls are intercepted by the convex_mock fixture.
"""
import json
import pytest
import httpx

pytestmark = pytest.mark.asyncio


VALID_API_YAML = "name: test_api\ntype: api\nurl: https://example.com\nresponse_format: json\n"
VALID_PIPELINE_YAML = "ontology: configs/ontology/core.yaml\nsteps:\n  - name: s\n    api: a\n    class: C\n    uri: 'X_{id}'\n"
VALID_ONTOLOGY_YAML = "uri: http://example.org/t.owl\nclasses:\n  - name: Thing\n"


# ── /configs/validate ─────────────────────────────────────────────────────────

async def test_validate_valid_api(client):
    resp = await client.post("/api/v1/configs/validate", json={
        "config_type": "api",
        "content": VALID_API_YAML,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []


async def test_validate_invalid_api(client):
    resp = await client.post("/api/v1/configs/validate", json={
        "config_type": "api",
        "content": "name: broken\n",  # missing type, url, response_format
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


async def test_validate_bad_yaml(client):
    resp = await client.post("/api/v1/configs/validate", json={
        "config_type": "api",
        "content": "key: [unclosed",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "Invalid YAML" in body["errors"][0]


# ── GET /configs/apis ─────────────────────────────────────────────────────────

async def test_list_apis_returns_list(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": [{"slug": "my-api", "name": "My API"}]})
    )
    resp = await client.get("/api/v1/configs/apis")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["slug"] == "my-api"


async def test_list_apis_empty(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    resp = await client.get("/api/v1/configs/apis")
    assert resp.status_code == 200
    assert resp.json() == []


# ── GET /configs/apis/{slug} ──────────────────────────────────────────────────

async def test_get_api_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": {"slug": "my-api", "name": "My API"}})
    )
    resp = await client.get("/api/v1/configs/apis/my-api")
    assert resp.status_code == 200
    assert resp.json()["slug"] == "my-api"


async def test_get_api_not_found(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": None})
    )
    resp = await client.get("/api/v1/configs/apis/does-not-exist")
    assert resp.status_code == 404


# ── POST /configs/apis ────────────────────────────────────────────────────────

async def test_create_api_valid(client, convex_mock):
    convex_mock.post("/api/mutation").mock(
        return_value=httpx.Response(200, json={"value": "new-id-123"})
    )
    resp = await client.post("/api/v1/configs/apis", json={
        "name": "Test API",
        "slug": "test-api",
        "content": VALID_API_YAML,
        "isPublic": True,
        "tags": [],
    })
    assert resp.status_code == 200


async def test_create_api_invalid_yaml_rejected(client):
    resp = await client.post("/api/v1/configs/apis", json={
        "name": "Bad API",
        "slug": "bad-api",
        "content": "name: broken\n",
        "isPublic": False,
        "tags": [],
    })
    assert resp.status_code == 422


# ── GET /configs/pipelines ────────────────────────────────────────────────────

async def test_list_pipelines(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": [{"slug": "nj", "name": "NJ"}]})
    )
    resp = await client.get("/api/v1/configs/pipelines")
    assert resp.status_code == 200
    assert resp.json()[0]["slug"] == "nj"


# ── GET /configs/ontologies ───────────────────────────────────────────────────

async def test_list_ontologies(client, convex_mock):
    convex_mock.post("/api/query").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    resp = await client.get("/api/v1/configs/ontologies")
    assert resp.status_code == 200
    assert resp.json() == []
