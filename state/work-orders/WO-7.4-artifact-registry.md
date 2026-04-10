# Work Order 7.4: Distributed Artifact Registry

## Objective
Enable horizontal scaling and eliminate "split-brain" state by shifting from local file paths to a versioned, immutable artifact registry.

## Requirements
1.  **`artifact_registry.py`**:
    *   Implement a service to manage project artifacts (`onto.db`, `onto.duckdb`).
    *   Generate unique `rev_hashes` for every hydration.
    *   Store manifests in Convex: `artifactRev: { rev: string, projectId: string, s3_path: string, timestamp: number }`.
2.  **Hydration Worker Update**:
    *   Update `hydration_worker.py` to upload the resulting DuckDB/SQLite files to object storage (or a shared local path addressable by hash) and register the new version in Convex.
3.  **Service Resolution**:
    *   Update `ontology_service.py` and `sql_service.py` to resolve their data sources via `artifact_rev` instead of hardcoded paths in the engine root.

## Verification
- Run a hydration job and verify a new `artifact_rev` is created in Convex.
- Verify that the Agent can query a previous version of the graph by passing an old hash.
