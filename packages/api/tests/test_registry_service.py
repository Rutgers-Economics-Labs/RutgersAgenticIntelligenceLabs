import pytest

pytestmark = pytest.mark.asyncio


async def test_default_registry_catalog_meets_seed_targets():
    from app.services.registry_service import default_registry_entries

    entries = default_registry_entries()
    fred = [entry for entry in entries if entry["provider"] == "fred"]
    census = [entry for entry in entries if entry["provider"] == "census"]
    worldbank = [entry for entry in entries if entry["provider"] == "worldbank"]
    bls = [entry for entry in entries if entry["provider"] == "bls"]

    assert len(fred) >= 50
    assert len(census) >= 20
    assert len(worldbank) >= 10
    assert len(bls) >= 10


async def test_search_registry_entries_prefers_custom_override(monkeypatch):
    from app.services import registry_service

    async def fake_list_custom_entries(limit: int = 200):
        assert limit == 500
        return [{
            "provider": "fred",
            "id": "UNRATE",
            "name": "Unemployment Rate (Custom Override)",
            "description": "Custom registry entry should override the seeded version.",
            "unit": "percent",
            "frequency": "monthly",
            "geography": "national",
            "tags": ["labor", "custom"],
            "exampleYaml": "name: custom_unrate",
            "updatedAt": 999,
        }]

    monkeypatch.setattr(registry_service, "list_custom_entries", fake_list_custom_entries)

    results = await registry_service.search_registry_entries(
        query_text="custom override",
        provider="fred",
        geography="national",
        limit=5,
    )

    assert len(results) == 1
    assert results[0]["id"] == "UNRATE"
    assert results[0]["name"] == "Unemployment Rate (Custom Override)"


async def test_get_registry_entry_prefers_custom_override(monkeypatch):
    from app.services import registry_service

    async def fake_query(path: str, args: dict):
        assert path == "registry:get"
        assert args == {"provider": "fred", "sourceId": "UNRATE"}
        return {
            "provider": "fred",
            "sourceId": "UNRATE",
            "name": "Custom UNRATE",
            "description": "Convex-backed override",
            "unit": "percent",
            "frequency": "monthly",
            "geography": "national",
            "tags": ["custom"],
            "exampleYaml": "name: custom_unrate",
            "updatedAt": 5,
        }

    monkeypatch.setattr(registry_service.convex, "query", fake_query)

    entry = await registry_service.get_registry_entry("fred", "UNRATE")

    assert entry is not None
    assert entry["name"] == "Custom UNRATE"
    assert entry["exampleYaml"] == "name: custom_unrate"
