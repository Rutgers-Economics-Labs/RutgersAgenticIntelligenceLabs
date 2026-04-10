1. **Ontology Integration**:
   - Modify `packages/engine/ontology/kernel.yaml` to include `hasCoverageStatus` in `data_properties`.
   - Ensure the new property allows storing coverage metadata natively in the ontology.

2. **`coverage_service.py`**:
   - Create `packages/api/app/services/coverage_service.py`.
   - Import necessary services (`sql_service`, `registry_service`, `project_artifacts_service`, etc.).
   - Implement `get_project_coverage(project_id)`:
     - Load duckdb schema for the project.
     - For each table (representing a class), query row count.
     - Also query non-null property percentage (count non-nulls / total rows for each column, then aggregate).
     - Return map of class name to density metrics.
   - Implement `check_data_availability(ontology_classes, time_range)`:
     - Cross-reference with `get_project_coverage` (current DuckDB).
     - Cross-reference with `dataSourceRegistry` (using `registry_service.search_registry_entries` or direct convex client).
     - Combine results to show available vs missing data.

3. **`coverage.yaml` schema definition**:
   - Add schema validation for `coverage` configs in `packages/api/app/services/yaml_service.py`.
   - Update `ALLOWED_TOP_LEVEL_COVERAGE_FIELDS` or similar.
   - Add `coverage` type parsing. A coverage yaml defines overrides (e.g., flagging classes as "sparse" or "verified").

4. **Agent Integration**:
   - Add tool definitions in `packages/api/app/services/agent_service.py`: `get_project_coverage`, `check_data_availability`.
   - Implement `_execute_tool` cases for them so the Research Agent and Project Setup Agent can utilize them.

5. **Test implementation**:
   - Create `packages/api/tests/test_coverage_service.py`.
   - Test `get_project_coverage` logic with a mock duckdb schema/data.
   - Test `check_data_availability` logic.

6. **Pre-commit**:
   - Follow standard pre-commit steps and checks before submitting.
