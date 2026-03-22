# FastAPI Service

The FastAPI service (`packages/api/`) is the HTTP bridge between the Next.js frontend and the Python engine. It runs on port 8000.

## Entry Point

`packages/api/app/main.py` — started with `uvicorn app.main:app --port 8000 --reload`.

On startup (`lifespan`):
1. Inserts `settings.engine_root` into `sys.path` so `from engine.*` imports work.
2. Pushes LLM API keys from settings into `os.environ` so LiteLLM can read them.
3. If `{engine_root}/ontology/onto.db` exists, loads it via `ontology_service.load()`.
4. If `{engine_root}/ontology/onto.duckdb` exists, loads it via `sql_service.set_path()`.

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
| `ai_model` | `str` | `"claude-sonnet-4-6"` | `AI_MODEL` |
| `ai_temperature` | `float` | `0.3` | `AI_TEMPERATURE` |
| `ai_max_tokens` | `int` | `8192` | `AI_MAX_TOKENS` |
| `embedding_model` | `str` | `"text-embedding-3-small"` | `EMBEDDING_MODEL` |
| `anthropic_api_key` | `str` | `""` | `ANTHROPIC_API_KEY` |
| `openai_api_key` | `str` | `""` | `OPENAI_API_KEY` |
| `google_api_key` | `str` | `""` | `GOOGLE_API_KEY` |
| `openrouter_api_key` | `str` | `""` | `OPENROUTER_API_KEY` |
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
| GET | `/semantic-search` | `q` (required), `types` (CSV, optional), `limit` (1–100) | ranked `[EntitySummary]` |
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
| POST | `/scrape-preview` | `{url: str, table_selector?: str, javascript?: bool, encoding?: str}` | `{columns, rows, rowCount}` |
| POST | `/doc-preview` | `{storage_key: str, extraction_mode: str, pages?: str}` | `{columns, rows, rowCount, source_text?}` |

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

POST triggers `hydration_worker.run()` via `asyncio.create_task()`. An internal helper `_trigger_job(pipeline_slug)` exposes the same logic without FastAPI's `BackgroundTasks` dependency (used by the agent service).

### `/api/v1/sql` — `app/routers/sql.py`

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `` | `{query: str}` | `{columns, rows, rowCount}` |
| POST | `/translate` | `{question: str, model?: str}` | `{sql, explanation, columns, rows, rowCount}` |
| GET | `/schema` | — | `{table_name: [{name, type}]}` |
| GET | `/tables` | — | `[table_name, ...]` |

Queries run against the DuckDB export of the ontology. `/translate` calls the LLM to convert natural language to SQL, then executes the result.

### `/api/v1/execute` — `app/routers/execute.py`

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `` | `{code: str, timeout?: int}` | `{stdout, stderr, dataframes, figures, error}` |

`timeout` max is 300s. Executes Python in a sandboxed namespace via `code_runner.run_code()`.

### `/api/v1/agent` — `app/routers/agent.py`

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/chat` | `{message, history?, model?, session_id?}` | SSE stream of event objects |
| POST | `/infer-schema` | `{sample?, description?, domain?, model?}` | `{api_yaml, ontology_yaml, explanation, raw}` |
| GET | `/models` | — | `{models: [{id, label}], default: str}` |

`/chat` returns `text/event-stream`. Each `data:` line is a JSON object with a `type` field:
- `{"type": "text_delta", "content": str}` — streaming text chunk
- `{"type": "tool_call", "id": str, "name": str, "args": dict}` — agent calling a tool
- `{"type": "tool_result", "id": str, "name": str, "result": any}` — tool execution result
- `{"type": "done", "new_messages": list}` — turn complete
- `{"type": "error", "message": str}` — fatal error

`/infer-schema` returns three YAML blocks extracted from the LLM response: an API source config, an ontology config, and a plain-text explanation.

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
async def export_to_duckdb(duckdb_path: str) -> None # exports all OWL individuals to DuckDB tables

def list_classes() -> list[dict]
def list_instances(class_name, page, limit, search) -> dict
def get_entity(uri) -> dict
def get_entity_graph(uri) -> dict
def get_full_graph(types, state_fips, limit) -> dict
def search_entities(q, types) -> list[dict]
def list_search_documents() -> list[dict]
def list_series() -> list[str]
def get_series_data(series_id) -> list[dict]
def _export_to_duckdb_sync(duckdb_path: str) -> None # sync; must be called within the executor thread
```

Entity serialization (`_serialize_entity`) extracts: `hasName`, `hasPopulation`, `hasFIPS`, `hasIncome`, `hasValue`, `hasDate`, `hasSeries`, `hasUnit`.

Graph node serialization (`_graph_node`) extracts: `hasName`, `hasPopulation`, `hasFIPS`, `hasValue`, `hasDate`, `hasSeries`.

`get_full_graph` defaults to `types=["State","County","Municipality","Individual"]`. When `state_fips` is given, County rows are filtered to `isPartOf == State_{fips}`; Municipality rows are filtered to `isPartOf` ∈ matching counties. Without `state_fips`, Municipality rows are skipped entirely (too many).

`export_to_duckdb` runs `_export_to_duckdb_sync` inside the single-thread executor so it shares the same SQLite connection. Each OWL class becomes a DuckDB table; data properties become columns; object properties are skipped. Two built-in columns are added per table: `_iri` and `_id`.

### `app/services/embedding_service.py`

```python
async def build_index(db_path: str | Path | None = None) -> None
async def search(query: str, top_k: int = 20, types: list[str] | None = None) -> list[dict]
def is_ready(db_path: str | Path | None = None) -> bool
```

The semantic index is stored in `embeddings.db` next to the active ontology database when possible. When an embedding provider key is configured, index/query embeddings use `litellm.aembedding()` with `settings.embedding_model`; otherwise the service falls back to a deterministic local hashing embedding so semantic search still works offline.

### `app/services/hydration_worker.py`

```python
async def run(job_id: str, pipeline_content: str, api_configs: dict[str, str], onto_configs: dict[str, str] = None)
```

Steps:
1. Set job status → `running`.
2. Create `tempfile.TemporaryDirectory`; write `configs/apis/{slug}.yaml` for each API config.
3. Parse pipeline YAML; override `ontology` to point at engine's bundled `core.yaml`, `output_owl` and `db` to tmpdir paths.
4. Copy `packages/engine/sources/` into tmpdir if it exists.
5. Spawn `python {engine_root}/engine/pipeline_runner_cli.py {pipeline_path}` with env vars: `RAIL_CACHE_DIR`, `RAIL_API_CONFIG_DIR`, `RAIL_TRANSFORM_DIR`, `RAIL_ANALYSIS_DIR`, `FRED_API_KEY`.
6. Read stdout line-by-line; parse `[step]` and `-> N X individuals processed` lines; call `jobs:updateStep` mutations; call `jobs:appendLog` for every line.
7. On exit code 0: upload `onto.db` and `populated_ontology.owl` via `storage_service`; call `jobs:updateJob` → `success`; call `ontology_service.load(db_key)`; call `ontology_service.export_to_duckdb(duckdb_path)`; call `sql_service.set_path(duckdb_path)`.
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

### `app/services/llm_service.py`

Provider-agnostic LLM wrapper backed by LiteLLM. Supports any model string LiteLLM understands (Anthropic, Google, OpenRouter, OpenAI). Model is selected via `settings.ai_model`; callers may override per-request.

```python
def ensure_env_keys() -> None
    # Pushes API keys from settings into os.environ for LiteLLM

async def complete(
    messages: list[dict],
    model: str | None = None,
    tools: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Any
    # Non-streaming completion; returns the full LiteLLM response object

async def stream_text(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]
    # Streaming text; yields text delta strings

async def stream_agent(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
) -> AsyncGenerator[dict, None]
    # One streaming turn with tool use; yields event dicts
    # (text_delta, tool_call, _turn_end)
```

`stream_agent` accumulates tool call deltas across chunks and yields complete tool calls at end-of-stream, followed by a `_turn_end` sentinel with `has_tool_calls` and `raw_tool_calls` fields.

### `app/services/sql_service.py`

Manages a DuckDB file that mirrors the OWL ontology. Each OWL class is a table; each instance is a row.

```python
def get_path() -> Optional[Path]
def set_path(path: str | Path) -> None
def is_ready() -> bool
def run_query(sql: str) -> dict          # returns {columns, rows, rowCount}
def list_tables() -> list[str]
def get_schema() -> dict                 # returns {table: [{name, type}]}
def get_schema_ddl() -> str              # returns CREATE TABLE statements as a string
async def translate_to_sql(natural_language: str, model: str | None = None) -> dict
    # returns {sql, explanation}
```

`run_query` opens a read-only connection per call, serializes datetime values via `.isoformat()`, and closes the connection before returning.

`translate_to_sql` sends the DDL schema + question to the LLM with a system prompt instructing it to output only valid DuckDB SQL, then parses the explanation comment.

### `app/services/code_runner.py`

Executes Python code in a sandboxed `exec()` namespace. Single-user; no container isolation.

```python
def run_code(code: str, timeout_seconds: int = 60) -> dict
    # returns {stdout, stderr, dataframes, figures, error}
```

Execution namespace (`_build_context()`) contains:
- `sql(query: str) -> pd.DataFrame` — runs SQL via `sql_service`
- `get_table(name: str) -> pd.DataFrame` — fetches a full DuckDB table
- `list_tables() -> list[str]`
- `pd` (pandas), `np` (numpy), `smf` (statsmodels.formula.api), `sm` (statsmodels.api), `sklearn`, `plt` (matplotlib.pyplot)

After execution, all `pd.DataFrame` variables in the namespace (excluding `_`-prefixed names) are serialized to `{columns, rows, rowCount}` and returned in `dataframes`. Matplotlib figures are saved as base64 PNG and returned in `figures`. Execution runs in a `ThreadPoolExecutor(max_workers=1)` with the specified timeout.

### `app/services/agent_service.py`

Implements a streaming agentic loop. The agent can call tools across multiple turns until no tool calls remain (max 10 turns).

```python
async def run_chat(
    user_message: str,
    history: list[dict],
    model: str | None = None,
) -> AsyncGenerator[dict, None]
    # Yields SSE event dicts: text_delta, tool_call, tool_result, done
```

**System prompt** instructs the agent to: discover data sources, write YAML configs, run pipelines, query the ontology, run SQL, and execute Python for statistical analysis.

**Tools available to the agent:**

| Tool name | What it does |
|-----------|-------------|
| `list_configs` | Fetches API, ontology, and pipeline config lists from Convex |
| `create_config` | Creates a new config in Convex (api, ontology, or pipeline) |
| `run_pipeline` | Triggers a hydration pipeline and polls until done (max 10 min) |
| `query_ontology` | Lists class instances with optional keyword search (max 100) |
| `run_sql` | Executes SQL against DuckDB |
| `get_sql_schema` | Returns DuckDB schema as `{table: [{name, type}]}` |
| `execute_python` | Runs Python code in the sandbox; returns stdout, DataFrames, figures |
| `get_series_data` | Fetches time-series data for a measure series ID |
| `search_entities` | Keyword search across all ontology entities |

Tool schemas follow the OpenAI function-calling format; LiteLLM normalizes them for each provider.
