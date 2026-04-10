# Work Order 7.2: Context Assembly Service (The Slicer)

## Objective
Introduce a high-level orchestrator that translates natural language queries into deterministic "operational slices" of data.

## Requirements
1.  **`context_service.py`**:
    *   Implement `assemble_context(question, project_id)`:
        1. Calls the **Planner** role to get a `ContextManifest` (list of classes, IRIs, and filters).
        2. Calls `coverage_service` to verify data presence.
        3. Generates a **`StructuredContextBundle`**.
2.  **`StructuredContextBundle` Model**:
    *   Define a Pydantic model containing:
        *   `manifest_id`: UUID
        *   `ontology_ddl`: SQL needed to recreate the relevant sub-schema.
        *   `entities`: List of pinned IRIs for high-precision context.
        *   `document_ids`: Context document snippets.
3.  **Agent Integration**:
    *   Update `agent_service.py` to accept a `bundle_id` instead of raw strings for its context initialization.

## Verification
- Test that the Planner correctly identifies "County" and "Unemployment" as context requirements for a labor query.
- Verify the bundle size is < 100KB for typical queries.
