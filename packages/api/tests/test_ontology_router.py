"""
Tests for ontology routes, including semantic search.
"""
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_semantic_search_route(client):
    expected = [
        {
            "id": "County_Monmouth",
            "iri": "http://example.org/County_Monmouth",
            "class": "County",
            "properties": {"hasName": "Monmouth County"},
        }
    ]

    with patch("app.routers.ontology.embedding_service.search", new=AsyncMock(return_value=expected)) as search_mock:
        resp = await client.get(
            "/api/v1/ontology/semantic-search",
            params={"q": "coastal counties", "types": "County", "limit": 10},
        )

    assert resp.status_code == 200
    assert resp.json() == expected
    search_mock.assert_awaited_once_with("coastal counties", top_k=10, types=["County"])


async def test_semantic_search_unavailable(client):
    with patch(
        "app.routers.ontology.embedding_service.search",
        new=AsyncMock(side_effect=RuntimeError("Semantic index not ready")),
    ):
        resp = await client.get("/api/v1/ontology/semantic-search", params={"q": "coastal counties"})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Semantic index not ready"
