import pytest

pytestmark = pytest.mark.asyncio


async def test_search_data_registry_tool_returns_results():
    from app.services.agent_service import _execute_tool

    result = await _execute_tool("search_data_registry", {
        "query": "unemployment",
        "provider": "fred",
        "geography": "state",
    })

    assert "results" in result
    assert len(result["results"]) > 0
    assert all(item["provider"] == "fred" for item in result["results"])
    assert all(item["geography"] == "state" for item in result["results"])
