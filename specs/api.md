# FastAPI Service

The FastAPI service (`packages/api/`) is the HTTP bridge between the Next.js frontend and the Python engine. It runs on port 8000.

## Entry Point

`packages/api/app/main.py` — started with `uvicorn app.main:app --port 8000 --reload`.

On startup (`lifespan`):
1. Inserts `settings.engine_root` into `sys.path` so `from engine.*` imports work.
2. If `{engine_root}/ontology/onto.db` exists, loads it via `ontology_service.load()`.

## Configuration — `app/core/config.py`

`Settings` is a `pydantic_settings.BaseSettings` that reads from `.env` and env vars.

| Field | Type | Default | Source env var |
|-------|------|---------|---------------|
| `convex_url` | `str` | `""` | `CONVEX_URL` |
| `convex_deploy_key` | `str` | `""` | `CONVEX_DEPLOY_KEY` |
| `engine_root` | `Path` | `packages/engine` (relative to `config.py`) | `ENGINE_ROOT` |
| `rail_cache_dir` | `Path` | `/tmp/rail_cache` | `RAIL_CACHE_DIR` |
| `storage_backend` | `str` | `"local"` | `STORAGE_BACKEND` |
| `s3_bucket` | `str` | `""` | `S3_BUCKET` |
| `s3_region` | `str` | `"us-east-1"` | `S3_REGION` |
| `aws_access_key_id` | `str` | `""` | `AWS_ACCESS_KEY_ID` |
| `aws_secret_access_key` | `str` | `""` | `AWS_SECRET_ACCESS_KEY` |
| `fred_api_key` | `str` | `""` | `FRED_API_KEY` |
| `api_cors_origins` | `list[str]` | `["http://localhost:3000"]` | `API_CORS_ORIGINS` |

## Routers

All routers are mounted at `/api/v1`.

### `/api/v1/ontology` — `app/routers/ontology.py`

All handlers delegate to `ontology_service._run(fn, *args)` (thread-safe async wrapper).

| Method | Path | Parameters | Returns |
|--------|------|-----------|---------|
| GET | `/classes` | — | `[{name, instanceCount}]` |
| GET | `/classes/{class_name}/instances` | `page`, `limit` (1–200), `search` | `{total, page, limit, items: [EntitySummary]}` |
| GET | `/entities/{uri}` | — | `EntityDetail` with `relationships` |
| GET | `/entities/{uri}/graph` | — | `{nodes, links}` 1-hop subgraph |
| GET | `/graph` | `types` (CSV), `state_fips`, `limit` (1–2000) | `{nodes, links}` filtered full graph |
| GET | `/search` | `q` (required), `types` (CSV, optional) | `[EntitySummary]` capped at 100 |
| GET | `/series` | — | `[series_id_string]` sorted |
| GET | `/series/{series_id}/data` | — | `[{date, value}]` sorted by date |

### `/api/v1/analysis` — `app/routers/analysis.py`

Imports `engine.analysis_runner.{discover, run}` at request time (not at startup) to handle cold-start cases.

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/plugins` | — | `[{slug, name, description}]` |
| POST | `/plugins/{slug}/run` | `{config: dict}` | `{title, sections: [Section]}` |

Section types match `lib/api.ts` AnalysisSection union: `metrics`, `table`, `chart`, `text`, `divider`, `group`. DataFrames are serialized to `list[dict]` + `columns` list before return.

### `/api/v1/configs` — `app/routers/configs.py`

All reads proxy to Convex queries; all writes validate YAML first, then call Convex mutations.

**Validation endpoint:**

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/validate` | `{config_type: "api"\|"ontology"\|"pipeline", content: str}` | `{valid: bool, errors: [str]}` |

**API configs** (`/apis`, `/apis/{slug}`): GET list, POST create, GET one, PUT update, DELETE delete.

**Ontology configs** (`/ontologies`, `/ontologies/{slug}`): same CRUD shape.

**Pipeline configs** (`/pipelines`, `/pipelines/{slug}`): same CRUD shape. On create/update, `referencedApiSlugs` is extracted from `steps[*].api` fields.

### `/api/v1/jobs` — `app/routers/jobs.py`

| Method | Path | Body / Params | Returns |
|--------|------|--------------|---------|
| POST | `` | `{pipeline_slug, env_overrides?: dict}` | `{jobId, status: "queued"}` |
| GET | `` | `status?`, `limit` (default 50) | list of job objects |
| GET | `/{job_id}` | — | job object |
| GET | `/{job_id}/logs` | `after_seq` (default 0), `limit` (default 200) | list of log entries |
| DELETE | `/{job_id}` | — | sets status to `"cancelled"` in Convex |

POST triggers `hydration_worker.run()` as a FastAPI `BackgroundTask`.

## Services

### `app/services/convex_client.py`

Thin async `httpx` wrapper for the Convex HTTP API.

```python
class ConvexClient:
    async def mutation(self, fn_path: str, args: dict) -> Any
    async def query(self, fn_path: str, args: dict) -> Any

convex = ConvexClient()  # module-level singleton
```

Both methods call `POST /api/mutation` or `POST /api/query` with `Authorization: Convex <deploy_key>` and unwrap the `{"value": ...}` response envelope before returning.

### `app/services/ontology_service.py`

Module-level state: `_onto`, `_world`, `_db_path`, `_lock`, `_executor`.

```python
def load(db_path: str | Path)                        # opens/swaps quadstore; thread-safe via _lock
async def _run(fn, *args, **kwargs)                  # runs sync fn in ThreadPoolExecutor(max_workers=1)

def list_classes() -> list[dict]
def list_instances(class_name, page, limit, search) -> dict
def get_entity(uri) -> dict
def get_entity_graph(uri) -> dict
def get_full_graph(types, state_fips, limit) -> dict
def search_entities(q, types) -> list[dict]
def list_series() -> list[str]
def get_series_data(series_id) -> list[dict]
```

Entity serialization (`_serialize_entity`) extracts: `hasName`, `hasPopulation`, `hasFIPS`, `hasIncome`, `hasValue`, `hasDate`, `hasSeries`, `hasUnit`.

Graph node serialization (`_graph_node`) extracts: `hasName`, `hasPopulation`, `hasFIPS`, `hasValue`, `hasDate`, `hasSeries`.

`get_full_graph` defaults to `types=["State","County","Municipality","Individual"]`. When `state_fips` is given, County rows are filtered to `isPartOf == State_{fips}`; Municipality rows are filtered to `isPartOf` ∈ matching counties. Without `state_fips`, Municipality rows are skipped entirely (too many).

### `app/services/hydration_worker.py`

```python
async def run(job_id: str, pipeline_content: str, api_configs: dict[str, str])
```

Steps:
1. Set job status → `running`.
2. Create `tempfile.TemporaryDirectory`; write `configs/apis/{slug}.yaml` for each API config.
3. Parse pipeline YAML; override `ontology` to point at engine's bundled `core.yaml`, `output_owl` and `db` to tmpdir paths.
4. Copy `packages/engine/sources/` into tmpdir if it exists.
5. Spawn `python {engine_root}/engine/pipeline_runner_cli.py {pipeline_path}` with env vars: `RAIL_CACHE_DIR`, `RAIL_API_CONFIG_DIR`, `RAIL_TRANSFORM_DIR`, `RAIL_ANALYSIS_DIR`, `FRED_API_KEY`.
6. Read stdout line-by-line; parse `[step]` and `-> N X individuals processed` lines; call `jobs:updateStep` mutations; call `jobs:appendLog` for every line.
7. On exit code 0: upload `onto.db` and `populated_ontology.owl` via `storage_service`; call `jobs:updateJob` → `success`; call `ontology_service.load(db_key)`.
8. On exception: call `jobs:updateJob` → `failed` with `errorMessage`.

Log levels: `"error"` if `"error"` or `"warning"` appears in line (case-insensitive); otherwise `"info"`.

### `app/services/storage_service.py`

```python
async def upload(job_id: str, filename: str, local_path: str) -> str
```

When `storage_backend == "local"`: copies file to `/tmp/rail_artifacts/{job_id}/{filename}`; returns the local path string.

When `storage_backend == "s3"`: uploads to `s3://{s3_bucket}/jobs/{job_id}/{filename}` using `aioboto3`; returns the S3 key `jobs/{job_id}/{filename}`.

`download(storage_key, dest_path)` is the reverse: in local mode copies `storage_key` (which is a path) to `dest_path`; in S3 mode downloads from S3.

### `app/services/yaml_service.py`

```python
def validate(config_type: str, content: str) -> list[str]
def parse(content: str) -> dict
```

`validate` checks: YAML parses without error; required top-level keys are present for the given type. Returns a list of error strings (empty = valid).

Required keys and validation rules by type:

**`"api"`**: `name` (string); `type` (one of `"api"`, `"csv"`, `"excel"`).
- When `type == "api"`: `url`, `response_format` (`"json"` or `"census_array"`); if `foreach` present, requires `foreach.source` and `foreach.field`.
- When `type` is `"csv"` or `"excel"`: `path`.
- Each `fields[]` entry: must have `source` or `computed`; `computed` fields require `alias`; `cast` must be `"int"`, `"float"`, or `"str"`.

**`"ontology"`**: `uri`; `classes[]` entries must have `name`; `object_properties[]` entries must have `name`; `data_properties[]` entries must have `name` and `range` ∈ `("str","int","float","bool")`.

**`"pipeline"`**: `ontology`, `steps`; each step requires `name`, `api`, `class`, `uri`; each `relationships[]` entry requires `property`, `target_class`, `target_uri`.
