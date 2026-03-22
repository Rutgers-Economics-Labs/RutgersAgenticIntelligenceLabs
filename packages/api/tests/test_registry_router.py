import httpx
import pytest

pytestmark = pytest.mark.asyncio


async def test_registry_search_returns_seeded_entries(client):
    response = await client.get("/api/v1/registry/search", params={
        "q": "new jersey unemployment",
        "provider": "fred",
        "geography": "state",
        "limit": 10,
    })

    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all(item["provider"] == "fred" for item in data)
    assert all(item["geography"] == "state" for item in data)
    assert data[0]["id"] == "NJUR"


async def test_registry_get_returns_seeded_entry(client):
    response = await client.get("/api/v1/registry/fred/UNRATE")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Unemployment Rate"
    assert "series_id: UNRATE" in body["exampleYaml"]


async def test_registry_create_and_get_custom_entry(client, convex_mock):
    mutation_route = convex_mock.post("/api/mutation")
    mutation_route.mock(return_value=httpx.Response(200, json={"value": "registry-id"}))

    create_response = await client.post("/api/v1/registry", json={
        "provider": "custom",
        "id": "my-source",
        "name": "My Source",
        "description": "Custom internal registry item.",
        "unit": "index",
        "frequency": "monthly",
        "geography": "national",
        "tags": ["custom"],
        "exampleYaml": "name: my-source",
    })
    assert create_response.status_code == 200

    convex_mock.post("/api/query").mock(return_value=httpx.Response(200, json={"value": {
        "provider": "custom",
        "sourceId": "my-source",
        "name": "My Source",
        "description": "Custom internal registry item.",
        "unit": "index",
        "frequency": "monthly",
        "geography": "national",
        "tags": ["custom"],
        "exampleYaml": "name: my-source",
        "updatedAt": 123,
    }}))

    get_response = await client.get("/api/v1/registry/custom/my-source")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == "my-source"
