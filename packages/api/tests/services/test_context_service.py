import pytest
import sys
import uuid
import json

from app.services import context_service
from app.models.context import StructuredContextBundle, ContextManifest

pytestmark = pytest.mark.asyncio

class MockResponse:
    class Message:
        def __init__(self, content):
            self.content = content
    class Choice:
        def __init__(self, message):
            self.message = message
    def __init__(self, content):
        self.choices = [self.Choice(self.Message(content))]

async def mock_llm_complete(*args, **kwargs):
    # Mock returning a JSON string for Planner
    return MockResponse('{"classes": ["County", "Unemployment"], "iris": [], "filters": []}')

async def mock_check_data_availability(*args, **kwargs):
    return {"available_in_project": {}, "missing_but_available_in_registry": [], "missing_and_unknown": []}

def mock_get_schema_ddl(*args, **kwargs):
    return """CREATE TABLE "County" (
    id VARCHAR,
    name VARCHAR
);
CREATE TABLE "Unemployment" (
    county_id VARCHAR,
    rate FLOAT
);
CREATE TABLE "IgnoredClass" (
    id VARCHAR
);
"""

async def test_assemble_context(monkeypatch):
    from app.services import llm_service
    from app.services import coverage_service
    from app.services import sql_service

    monkeypatch.setattr(llm_service, "complete", mock_llm_complete)
    monkeypatch.setattr(coverage_service, "check_data_availability", mock_check_data_availability)
    monkeypatch.setattr(sql_service, "get_schema_ddl", mock_get_schema_ddl)

    # Mock DuckDB path resolution
    from app.services import agent_service
    async def mock_resolve_duckdb_path(*args, **kwargs):
        return None
    monkeypatch.setattr(agent_service, "_resolve_duckdb_path", mock_resolve_duckdb_path)

    question = "What is the unemployment rate in each county?"
    bundle = await context_service.assemble_context(question, project_id=None)

    assert bundle is not None
    assert isinstance(bundle, StructuredContextBundle)
    assert bundle.ontology_ddl is not None
    assert 'CREATE TABLE "County"' in bundle.ontology_ddl
    assert 'CREATE TABLE "Unemployment"' in bundle.ontology_ddl
    # The ignored class should not be in the output sub-schema
    assert 'CREATE TABLE "IgnoredClass"' not in bundle.ontology_ddl

    bundle_size_bytes = len(bundle.model_dump_json().encode('utf-8'))
    assert bundle_size_bytes < 100 * 1024, "Bundle size must be < 100KB"

    # Verify the bundle can be retrieved from the cache
    cached_bundle = context_service.get_bundle(str(bundle.manifest_id))
    assert cached_bundle is not None
    assert cached_bundle.manifest_id == bundle.manifest_id
