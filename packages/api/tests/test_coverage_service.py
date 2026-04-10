import pytest
from unittest.mock import patch, MagicMock

from app.services import coverage_service

@pytest.mark.asyncio
@patch("app.services.coverage_service._resolve_duckdb_path")
@patch("app.services.sql_service.get_schema")
@patch("duckdb.connect")
async def test_get_project_coverage(mock_duckdb_connect, mock_get_schema, mock_resolve_path):
    mock_resolve_path.return_value = "fake_path.duckdb"

    # Mock schema
    mock_get_schema.return_value = {
        "Person": [{"name": "hasName", "type": "VARCHAR"}, {"name": "age", "type": "INTEGER"}],
        "EmptyClass": [{"name": "hasName", "type": "VARCHAR"}]
    }

    # Mock duckdb connection and execution
    mock_conn = MagicMock()
    mock_duckdb_connect.return_value = mock_conn

    def mock_execute(query):
        mock_cursor = MagicMock()
        if "COUNT(*) FROM Person WHERE hasName IS NOT NULL" in query:
            mock_cursor.fetchone.return_value = [100]
        elif "COUNT(*) FROM Person WHERE age IS NOT NULL" in query:
            mock_cursor.fetchone.return_value = [50]
        elif "COUNT(*) FROM Person" in query:
            mock_cursor.fetchone.return_value = [100]
        elif "COUNT(*) FROM EmptyClass" in query:
            mock_cursor.fetchone.return_value = [0]
        else:
            mock_cursor.fetchone.return_value = [0]
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute

    # Call the service
    result = await coverage_service.get_project_coverage(project_id="test_project")

    # Assertions
    assert "Person" in result
    assert result["Person"]["row_count"] == 100
    assert result["Person"]["property_density"]["hasName"] == 1.0
    assert result["Person"]["property_density"]["age"] == 0.5

    assert "EmptyClass" in result
    assert result["EmptyClass"]["row_count"] == 0
    assert result["EmptyClass"]["property_density"] == {}

    mock_conn.close.assert_called_once()

@pytest.mark.asyncio
@patch("app.services.coverage_service.get_project_coverage")
@patch("app.services.registry_service.search_registry_entries")
async def test_check_data_availability(mock_search_registry, mock_get_coverage):
    # Mock coverage returned from DuckDB
    mock_get_coverage.return_value = {
        "ExistingClass": {"row_count": 100, "property_density": {}}
    }

    # Mock registry search results
    mock_search_registry.side_effect = lambda query_text: [{"name": "Registry Match"}] if query_text == "RegistryClass" else []

    classes_to_check = ["ExistingClass", "RegistryClass", "UnknownClass"]

    result = await coverage_service.check_data_availability(classes_to_check, project_id="test_project")

    # Assertions
    assert "ExistingClass" in result["available_in_project"]
    assert result["available_in_project"]["ExistingClass"]["row_count"] == 100

    assert len(result["missing_but_available_in_registry"]) == 1
    assert result["missing_but_available_in_registry"][0]["class"] == "RegistryClass"
    assert result["missing_but_available_in_registry"][0]["potential_sources"][0]["name"] == "Registry Match"

    assert len(result["missing_and_unknown"]) == 1
    assert result["missing_and_unknown"][0] == "UnknownClass"
