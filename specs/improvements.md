# Midterm Improvements

This document captures planned architectural improvements that are not needed for the initial release but should be designed with these in mind to avoid painting into a corner. Each improvement has a motivation, proposed approach, dependencies, and notes on what current design decisions preserve the upgrade path.

---

## 1. Pluggable Triple Store Backend

### Problem
owlready2 uses SQLite as its quadstore. It degrades significantly beyond ~5 million individuals. For a comprehensive public data ontology (full FRED at 800k+ series × decades of monthly observations = hundreds of millions of individuals), it will not scale.

### Approach
Abstract the triple store behind an interface so the backend can be swapped without changing the engine or API:

```python
# packages/engine/engine/triplestore.py  (new)
class TripleStoreBackend(Protocol):
    def load(self, db_path: str) -> None: ...
    def get_world(self) -> Any: ...          # returns owlready2 World OR jena Model, etc.
    def save(self, output_path: str) -> None: ...
    def list_classes(self) -> list[str]: ...
    def list_instances(self, class_name: str) -> list[Any]: ...
    def search_one(self, **kwargs) -> Any: ...
    def export_to_duckdb(self, duckdb_path: str) -> None: ...
```

Concrete implementations:
- `OwlreadyBackend` — current behavior, wraps owlready2/SQLite (default)
- `JenaTDB2Backend` — Apache Jena TDB2 via JPype or a sidecar JVM process
- `OxigraphBackend` — Oxigraph (Rust, via Python bindings `pyoxigraph`), best balance of performance and simplicity
- `BlazeGraphBackend` — Blazegraph for very large graphs with SPARQL endpoint

Backend is selected per-project via the `rail.yaml` manifest:

```yaml
# rail.yaml
triplestore:
  backend: owlready2          # owlready2 | oxigraph | jena-tdb2 | blazegraph
  options:
    memory_limit: 4gb         # backend-specific options
```

If absent, defaults to `owlready2`. The hydration worker, ontology service, and analysis runner all go through the `TripleStoreBackend` interface — no backend-specific code outside the concrete implementations.

### Dependencies
- This is an engine-level change. `ontology_service.py` is the primary consumer.
- owlready2-specific property access (`individual.hasName`, `onto.State.instances()`) must be wrapped or replaced with generic accessor methods in the interface.
- Analysis plugins that import owlready2 directly will need updating when a non-owlready2 backend is active.

### Preserving the Upgrade Path Now
- Keep all owlready2 calls inside `ontology_service.py` — never import owlready2 from routers or agent tools directly.
- Design `OntologyModule` (platform-objects template) to store `hasTriplestoreBackend` as a data property so the platform knows which backend a project uses.

---

## 2. Object Properties as Join Tables in DuckDB

### Problem
The current DuckDB export skips all object properties (`isPartOf`, `measuredFor`, `locatedIn`, etc.). This makes relational graph queries impossible in SQL — the agent's `run_sql` tool and the SQL editor cannot traverse relationships.

```sql
-- Currently broken — measuredFor is not in DuckDB:
SELECT c.hasName, AVG(l.hasValue)
FROM County c
JOIN LaborIndicator l ON l.measuredFor = c._iri
GROUP BY c.hasName
```

### Approach
For each object property in the ontology, export a join table during `export_to_duckdb`:

```python
# In _export_to_duckdb_sync():
# For each object property `prop`:
#   CREATE TABLE {prop.name}_edges (subject_iri VARCHAR, object_iri VARCHAR)
#   INSERT rows for all (subject, object) pairs
```

Result in DuckDB:
```
isPartOf_edges        (subject_iri, object_iri)
measuredFor_edges     (subject_iri, object_iri)
locatedIn_edges       (subject_iri, object_iri)
hasPart_edges         (subject_iri, object_iri)   -- inverse properties too
```

This enables full relational graph traversal in SQL:

```sql
-- Find all counties in NJ with unemployment > 5%
SELECT c.hasName, l.hasValue
FROM County c
JOIN isPartOf_edges e ON e.subject_iri = c._iri
JOIN State s ON s._iri = e.object_iri AND s.hasFIPS = '34'
JOIN measuredFor_edges mf ON mf.object_iri = c._iri
JOIN LaborIndicator l ON l._iri = mf.subject_iri
WHERE l.hasValue > 5.0 AND l.hasDate = '2024-01-01'
```

Multi-hop traversal via DuckDB recursive CTEs:
```sql
-- All geographic entities within a state hierarchy (recursive)
WITH RECURSIVE region_tree AS (
  SELECT _iri FROM State WHERE hasFIPS = '34'
  UNION ALL
  SELECT e.subject_iri FROM isPartOf_edges e
  INNER JOIN region_tree r ON e.object_iri = r._iri
)
SELECT * FROM region_tree
```

### Impact on `get_schema_ddl()`
The schema DDL returned to the agent and the SQL schema browser must include the edge tables with column types and a comment explaining their semantics.

### Dependencies
- Change to `_export_to_duckdb_sync()` in `ontology_service.py`.
- Update `get_schema_ddl()` to include edge tables.
- Update agent system prompt to explain the `{property}_edges` pattern.
- Update `specs/api.md` SQL section when implemented.

---

## 3. Cross-Project Queries

### Problem
Each project has an isolated DuckDB file. Correlating data across projects (e.g., NJ unemployment vs. NJ air quality) requires loading both files manually. There is no platform-level cross-project query surface.

### SQL Layer — DuckDB ATTACH

The SQL service can maintain an attached multi-project DuckDB session:

```python
# sql_service.py — multi-project mode
conn = duckdb.connect()
for project in active_projects:
    conn.execute(f"ATTACH '{project.duckdb_path}' AS \"{project.slug}\" (READ_ONLY)")
```

Cross-project SQL becomes natural:
```sql
SELECT 
    econ.hasName,
    econ.hasValue AS unemployment_rate,
    clim.hasPM25 AS air_quality
FROM "nj-economics".LaborIndicator econ
JOIN "nj-economics".measuredFor_edges mf ON mf.subject_iri = econ._iri
JOIN "nj-climate".AirQualityReading clim ON clim.measuredFor = mf.object_iri
WHERE econ.hasDate = '2024-01-01'
```

The SQL editor and agent `run_sql` tool both get access to this multi-project session. A project can opt into the shared session or stay isolated.

### Ontology Layer — Cross-Project Graph

For OWL-level cross-project queries (useful for the agent's `query_ontology` tool and analysis plugins), the ontology service can load multiple onto.db files into a single owlready2 World:

```python
# ontology_service.py
def load_multi(self, project_db_paths: dict[str, str]) -> None:
    world = World()
    for slug, path in project_db_paths.items():
        world.get_ontology(f"file://{path}").load()
    # All individuals from all projects are now in one World
```

Cross-project object property links work automatically if the IRIs are consistent — a `State_34` individual in nj-economics and a `State_34` in nj-climate refer to the same URI and owlready2 merges them.

### Agent Layer

A future "cross-project workspace" would let the agent receive context from multiple projects simultaneously. This builds on the domain agent model — rather than replacing it, the router selects multiple project contexts and merges their schemas for the agent's context snapshot.

### Dependencies
- SQL: small change to `sql_service.py`, new `GET /api/v1/sql/projects` endpoint.
- OWL: new `load_multi()` method on `ontology_service`.
- Frontend: cross-project SQL editor toggle; multi-project graph view.
- IRI consistency: requires that projects using shared ontology templates (e.g., `us-geography`) produce the same URIs for shared entities (e.g., `State_34`). This is a convention that must be documented and enforced in connector templates.

---

## 4. Document Store for Nested / Semi-Structured Data

### Problem
Deeply nested JSON (APIs returning arrays of objects with sub-arrays), XML with mixed content, and other semi-structured formats don't fit cleanly into the DataFrame → OWL individual pipeline. The current escape hatch (write a custom Python transform) works but requires code for every such source.

### Proposed Approach (to be fully designed later)
A **document store** layer parallel to the OWL ontology, for data that resists flattening:

- Raw documents (JSON objects, XML nodes) stored as-is alongside their metadata individual in the ontology
- A `Document` OWL class with `hasStorageKey`, `hasFormat` (`json`, `xml`, `html`), `hasSchema` (optional JSON Schema pointer)
- Extraction pipelines that project selected fields from stored documents into ontology individuals on demand
- JSONPath / XPath field mapping in YAML configs as an alternative to full flattening

This is a significant addition. The core question to resolve: is the document store a separate service (Mongo-style) or does DuckDB's native JSON support handle it? DuckDB can store and query JSON columns natively, which may be sufficient:

```sql
SELECT json_extract(raw_document, '$.observations[*].value') 
FROM Document 
WHERE hasSource = 'fred_vintage_data'
```

**Decision deferred** — to be designed when a concrete use case requiring it is identified. The current transform escape hatch is sufficient for initial release.

---

## 5. Unstructured Data Pipelines

### Problem
Research-relevant unstructured data — academic papers, Fed speeches, congressional testimony, earnings call transcripts, news articles — cannot be ingested via the current structured pipeline. The agent has no way to reason over document content.

### Approach
A dedicated **unstructured ingestion pipeline type** alongside the existing structured YAML pipeline:

```yaml
# configs/pipelines/fed_speeches.yaml
type: unstructured                    # new pipeline type
name: Federal Reserve Speeches
sources:
  - type: web_scrape
    url: "https://www.federalreserve.gov/newsevents/speeches.htm"
    extract: links
  - type: pdf_download
    foreach: links
processor:
  chunking:
    strategy: paragraph               # paragraph | fixed_tokens | sentence
    chunk_size: 512
    overlap: 64
  embedding:
    model: text-embedding-3-small     # via EMBEDDING_MODEL env var
  entities:
    extract: true                     # NER: extract named entities into ontology
    link_to_classes: [State, Individual, DataSeries]  # link found entities to existing individuals
output:
  document_class: FedSpeech           # OWL class for document metadata individuals
  vector_index: true                  # add chunks to embedding index
```

For **economics specifically**, the reference implementation is [OpenAI GABRIEL](https://github.com/openai/GABRIEL) — an agentic pipeline for ingesting and structuring economic research data from unstructured sources. GABRIEL's approach (agent-driven extraction into structured schemas) aligns with RAIL's ontology model: the agent reads documents and creates ontology individuals rather than hard-coding extraction rules.

**Integration pattern:**
- GABRIEL-style pipelines run as a new pipeline type in the hydration worker
- Output: `Document` individuals (metadata) + vector index chunks + extracted named entity links
- The agent's context assembly gains a new tool: `search_documents(query)` → semantic search over the vector index, returns relevant chunks + source document metadata
- Extracted entities are linked into the existing OWL graph via standard object properties

### Dependencies
- New `type: unstructured` in `yaml-config.md` spec
- Vector store integration (extend existing `embedding_service.py`)
- Document storage (S3 or local) for raw content
- New agent tool: `search_documents`
- GABRIEL integration: evaluate as a library dependency vs. inspiration for implementation pattern

---

## 6. Ontology Migration System

### Problem
Renaming a class (`Measure` → `LaborIndicator`), removing a property, or restructuring the hierarchy orphans all existing individuals. There is no migration path — the only recovery is a full re-hydration, which loses all manual additions.

### Approach
A **migration file** format, committed to the project repo alongside the ontology:

```yaml
# ontology/migrations/002_rename_measure_to_labor_indicator.yaml
version: "002"
description: "Rename Measure class to LaborIndicator for clarity"
up:
  - type: rename_class
    from: Measure
    to: LaborIndicator
  - type: rename_property
    from: hasMeasureValue
    to: hasValue
    domain: LaborIndicator
  - type: add_class
    name: HousingIndicator
    parent: Observation
  - type: move_individuals
    from_class: Measure
    to_class: LaborIndicator
    filter: "hasSeries LIKE '%HPI%'"   # move only housing-related individuals
down:
  - type: rename_class
    from: LaborIndicator
    to: Measure
```

A migration runner (`engine/migration_runner.py`) applies migrations sequentially against a live onto.db in-place, without requiring full re-hydration. Migrations are versioned and tracked in a `_migrations` table in the DuckDB file.

The platform UI surfaces pending migrations on the project settings page with a one-click "Apply" action.

### OWL Versioning
The ontology's `owl:versionInfo` annotation is updated on each migration. The project's `ontology_configs` Convex record stores the current schema version. Hydration jobs record which schema version they ran against (`hasPipelineID` already captures the run; `hasSchemaVersion` is added as a kernel property).

### Dependencies
- New `engine/migration_runner.py`
- New `migrations/` directory convention in project repos
- New `POST /api/v1/projects/{slug}/migrate` API route
- Schema version tracking in Convex `projects` table (`currentSchemaVersion` field)
- `hasSchemaVersion` added to kernel properties

---

## 7. Historical Ontology Snapshots

### Problem
The platform only maintains the current state of the ontology. There is no way to query what the data looked like at a past point in time (bi-temporal queries), or to roll back to a known-good state after a bad hydration.

### Approach
**Snapshot storage:** After each successful hydration, the worker already uploads `onto.db` to storage (`storage_service.upload()`). The upload currently overwrites the previous file. Instead, store snapshots with a timestamp key:

```
jobs/{job_id}/onto.db            # already done
snapshots/{project_slug}/
  {timestamp}_{job_id}.db        # new: append-only snapshot history
  latest.db                      # symlink/pointer to most recent
```

**Snapshot policy** — configurable per project in `rail.yaml`:
```yaml
snapshots:
  retain: 10                     # keep last N snapshots
  schedule: weekly               # or: on_every_hydration | daily | weekly
```

**Snapshot browsing in the UI:** The project settings page shows a snapshot history table (timestamp, job ID, entity count, size). A "Browse" button loads the snapshot into a read-only explorer view without affecting the live ontology.

**Point-in-time queries via the API:**
```
GET /api/v1/ontology/classes?snapshot={timestamp}
GET /api/v1/sql?snapshot={timestamp}
```
The API loads the snapshot onto.db into a temporary in-memory World / DuckDB connection for the duration of the request.

### Dependencies
- Change to `storage_service.py` upload logic (append vs. overwrite)
- New `snapshots` field in Convex `projects` table
- New `GET /api/v1/projects/{slug}/snapshots` API route
- Optional: `hasSnapshotPolicy` on `Project` platform-objects individual

---

## 8. Streaming CSV / Large File Support

### Problem
`pd.read_csv()` and `pd.read_excel()` load entire files into memory. Files larger than ~500MB risk OOM-ing the API server. Some public datasets (Census microdata, IRS SOI files) are multi-GB.

### Approach
Add a `streaming: true` option to CSV/Excel API configs:

```yaml
name: census_microdata
type: csv
path: /data/census_pums_2023.csv
streaming: true
chunk_size: 50000               # rows per chunk
```

When `streaming: true`:
1. `api_runner.py` uses `pd.read_csv(chunksize=chunk_size)` to iterate chunks
2. Each chunk is processed through field mapping and ontology hydration independently
3. Individuals from each chunk are committed to the quadstore before the next chunk loads
4. The pipeline step logs progress as `chunk N/M processed`

For very large files (>2GB), a `duckdb_direct: true` mode bypasses pandas entirely:
```python
# api_runner.py
conn = duckdb.connect()
conn.execute(f"SELECT * FROM read_csv_auto('{path}')")  # DuckDB streams natively
```

DuckDB's `read_csv_auto` is significantly more memory-efficient than pandas for large files and supports schema inference, quoted fields, and multi-file globs.

### Dependencies
- Changes to `api_runner.py` fetch dispatch
- New YAML fields: `streaming`, `chunk_size`, `duckdb_direct`
- Update `specs/yaml-config.md` when implemented

---

## Priority and Sequencing

| Improvement | Priority | Effort | Blocks anything? |
|-------------|----------|--------|-----------------|
| Object properties in DuckDB (#2) | **High** | Low | Cross-project queries, agent SQL quality |
| Cross-project SQL via ATTACH (#3) | **High** | Low | Multi-domain research |
| Pluggable triple store (#1) | Medium | High | Full-scale public data ontology |
| Ontology migration system (#6) | Medium | Medium | Schema evolution in production |
| Unstructured data pipelines (#5) | Medium | High | Document reasoning for agent |
| Historical snapshots (#7) | Low | Low | Reproducibility |
| Streaming CSV (#8) | Low | Low | Large file ingestion |
| Document store (#4) | Low | High | Deferred — needs use case first |
| Cross-project OWL merge (#3b) | Low | Medium | Depends on triple store abstraction |

**Recommended order:** #2 → #3 (SQL) → #6 → #1 → #5 → #7 → #8 → #4.

Object property join tables (#2) and cross-project ATTACH (#3) are the highest-leverage, lowest-effort improvements and should be built as soon as the initial release is stable.
