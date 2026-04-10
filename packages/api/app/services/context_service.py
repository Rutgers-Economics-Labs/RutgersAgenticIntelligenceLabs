import json
import uuid
import sys
from typing import Dict, Any, Optional

from app.services import llm_service, sql_service, coverage_service
from app.models.context import ContextManifest, StructuredContextBundle
from app.services.agent_service import _resolve_duckdb_path

# Simple in-memory cache for bundles
_BUNDLE_CACHE: Dict[str, StructuredContextBundle] = {}

def get_bundle(bundle_id: str) -> Optional[StructuredContextBundle]:
    return _BUNDLE_CACHE.get(bundle_id)

async def assemble_context(question: str, project_id: str | None = None) -> StructuredContextBundle:
    """
    Acts as a high-level orchestrator that translates natural language queries
    into deterministic "operational slices" of data.
    """
    # 1. Call the Planner role to get a ContextManifest
    prompt = f"""You are the Context Planner for RAIL.
Given the user question: '{question}'

Determine the required data slice to answer this question.
Respond ONLY with a JSON object in the following format:
{{
  "classes": ["List of relevant ontology classes like 'County', 'Unemployment', 'Measure'"],
  "iris": ["List of specific IRIs if mentioned explicitly, otherwise empty"],
  "filters": ["Any specific filter requirements"]
}}
"""

    messages = [
        {"role": "system", "content": "You are a precise data planner. Output valid JSON only."},
        {"role": "user", "content": prompt}
    ]

    response = await llm_service.complete(messages=messages, temperature=0.0)
    raw_response = response.choices[0].message.content.strip()

    # Attempt to parse the response as JSON
    try:
        # Some LLMs wrap JSON in markdown blocks
        if raw_response.startswith("```json"):
            raw_response = raw_response[7:-3].strip()
        elif raw_response.startswith("```"):
            raw_response = raw_response[3:-3].strip()

        manifest_data = json.loads(raw_response)
        manifest = ContextManifest(**manifest_data)
    except Exception as e:
        print(f"Error parsing Planner response: {e}. Raw response: {raw_response}", file=sys.stderr)
        manifest = ContextManifest()

    # 2. Call coverage_service to verify data presence
    duck_path = await _resolve_duckdb_path(project_id=project_id)
    if manifest.classes:
        # Note check_data_availability takes a time_range, passing None
        availability = await coverage_service.check_data_availability(
            ontology_classes=manifest.classes,
            time_range=None,
            project_id=project_id
        )

    # 3. Generate a StructuredContextBundle
    # Extract DDL for the specific requested classes to keep the context size small
    # For now, we fetch the whole schema DDL and filter it to only include relevant tables if possible,
    # or just use the full schema DDL if small enough, but the requirement implies a "sub-schema"
    full_ddl = sql_service.get_schema_ddl(duckdb_path=duck_path)

    sub_schema_lines = []
    if full_ddl:
        # Simple extraction of relevant CREATE TABLE blocks
        current_table = None
        current_block = []
        for line in full_ddl.split("\n"):
            if line.startswith("CREATE TABLE"):
                # "CREATE TABLE "TableName" ..."
                parts = line.split('"')
                if len(parts) >= 3:
                    current_table = parts[1]
                else:
                    current_table = line.split(" ")[2]

            if current_table:
                # If no classes specified or table is in requested classes, keep it
                if not manifest.classes or current_table in manifest.classes:
                    sub_schema_lines.append(line)

    ontology_ddl = "\n".join(sub_schema_lines)
    if not ontology_ddl:
        # Fallback to full DDL if no classes matched or sub-schema is empty
        ontology_ddl = full_ddl

    bundle = StructuredContextBundle(
        manifest_id=uuid.uuid4(),
        ontology_ddl=ontology_ddl,
        entities=manifest.iris,
        document_ids=[] # We can add documents if needed in the future
    )

    bundle_id_str = str(bundle.manifest_id)
    _BUNDLE_CACHE[bundle_id_str] = bundle
    return bundle
