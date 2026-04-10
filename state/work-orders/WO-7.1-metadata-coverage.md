# Work Order 7.1: Metadata & Coverage (The Gap-Map)

## Objective
Implement a logic layer that enables agents to determine if a research question can be answered with the current project graph or if new data sources need to be onboarded.

## Requirements
1.  **`coverage_service.py`**:
    *   Implement `get_project_coverage(project_id)`: Scans the DuckDB schema and returns a map of classes and their "density" (row counts, non-null property percentage).
    *   Implement `check_data_availability(ontology_classes, time_range)`: Cross-references requested data with both the current DuckDB and the global `dataSourceRegistry` (Convex).
2.  **`coverage.yaml`**:
    *   Define a schema for project-level coverage overrides. Researchers can manually flag certain classes as "sparse" or "verified."
3.  **Ontology Integration**:
    *   Add `hasCoverageStatus` property to the Ontology Kernel so coverage metadata can be stored directly in `onto.db`.

## Verification
- `pytest packages/api/tests/test_coverage_service.py`
- Verify that the Coverage Agent can answer: "Do we have enough data to analyze NJ unemployment in 2022?"
