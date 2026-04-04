# rail-py — Internal Python Client Package

`rail-py` is an internal Python package that provides a unified interface for interacting with RAIL projects — either by connecting to a running platform instance (cloud mode) or by running the engine directly from a local project repo (local mode). The interface is identical in both modes.

---

## Installation

```bash
# From the monorepo (development)
pip install -e packages/rail-py

# From the internal GitHub repo (shared environments)
pip install git+ssh://git@github.com/rutgers-rail/rail.git#subdirectory=packages/rail-py

# With all optional dependencies (numpy, statsmodels, matplotlib)
pip install "git+ssh://git@github.com/rutgers-rail/rail.git#subdirectory=packages/rail-py[analysis]"
```

No PyPI publishing. Access is controlled by GitHub organization membership.

---

## Package Layout

```
packages/rail-py/
  rail/
    __init__.py            # exports connect(), local()
    client.py              # CloudClient — wraps FastAPI HTTP
    local.py               # LocalEngine — imports engine directly
    project.py             # Project — unified interface (cloud or local)
    ontology.py            # OntologyView — owlready2 wrapper
    agent.py               # AgentClient — SSE stream wrapper
    models.py              # Pydantic models for API responses
    exceptions.py          # RailError, AuthError, HydrationError, etc.
  setup.py
  pyproject.toml
  README.md
```

---

## Entry Points

```python
import rail

# Cloud mode — connects to a running RAIL platform via API
project = rail.connect(
    slug="nj-economics",
    api_url="https://rail.example.com/api/v1",   # or RAIL_API_URL env var
    api_key="rail_...",                            # or RAIL_API_KEY env var
)

# Local mode — runs the engine directly from a cloned project repo
project = rail.local(
    path="./nj-economics",       # path to the project repo root (contains rail.yaml)
    engine_path=None,            # optional: path to packages/engine/ if not in monorepo
)
```

Both return a `Project` instance with an identical interface.

### Environment Variables (cloud mode)

| Variable | Purpose |
|----------|---------|
| `RAIL_API_URL` | Base URL of the RAIL FastAPI service (default: `http://localhost:8000/api/v1`) |
| `RAIL_API_KEY` | API key for authenticated requests (not yet implemented — reserved for future auth) |

---

## `Project` Interface

```python
class Project:
    slug: str
    name: str
    mode: Literal["cloud", "local"]

    # ── Hydration ──────────────────────────────────────────────────────────────

    def hydrate(
        self,
        pipeline_slug: str | None = None,   # defaults to first pipeline in rail.yaml
        wait: bool = True,                   # block until job completes (cloud) or run finishes (local)
        timeout: int = 600,                  # seconds; ignored in local mode
    ) -> HydrationResult
        # Cloud: triggers POST /api/v1/jobs, polls until success/failed
        # Local: runs engine.pipeline_runner.run_pipeline() directly

    # ── Query ──────────────────────────────────────────────────────────────────

    def query(self, sql: str) -> pd.DataFrame
        # Executes SQL against the project's DuckDB
        # Cloud: POST /api/v1/sql
        # Local: opens onto.duckdb directly via duckdb.connect()

    def entities(
        self,
        class_name: str,
        search: str | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> list[dict]
        # Returns entity summaries for a given class
        # Cloud: GET /api/v1/ontology/classes/{class}/instances
        # Local: ontology_service.list_instances()

    def entity(self, uri: str) -> dict
        # Returns full entity detail including relationships
        # Cloud: GET /api/v1/ontology/entities/{uri}
        # Local: ontology_service.get_entity()

    def search(self, query: str, types: list[str] | None = None) -> list[dict]
        # Keyword search across all entities
        # Cloud: GET /api/v1/ontology/search
        # Local: ontology_service.search_entities()

    def series(self, series_id: str) -> pd.DataFrame
        # Returns time-series data as a DataFrame with columns [date, value]
        # Cloud: GET /api/v1/ontology/series/{id}/data
        # Local: ontology_service.get_series_data()

    def classes(self) -> list[dict]
        # Returns [{name, instanceCount}] for all OWL classes
        # Cloud: GET /api/v1/ontology/classes
        # Local: ontology_service.list_classes()

    # ── Ontology ───────────────────────────────────────────────────────────────

    def ontology(self) -> OntologyView
        # Returns an OntologyView wrapping the owlready2 World
        # Cloud: downloads onto.db to a local temp path, opens with owlready2
        # Local: opens onto.db directly

    # ── Analysis ───────────────────────────────────────────────────────────────

    def run_sql(self, sql: str) -> dict
        # Alias for query() that returns raw {columns, rows, rowCount} dict

    def execute(self, code: str, timeout: int = 60) -> ExecuteResult
        # Runs Python code in the execution sandbox
        # Cloud: POST /api/v1/execute
        # Local: runs via code_runner.run_code() with local DuckDB

    def run_analysis(self, plugin_slug: str, config: dict | None = None) -> AnalysisResult
        # Runs an analysis plugin
        # Cloud: POST /api/v1/analysis/plugins/{slug}/run
        # Local: analysis_runner.run() directly

    # ── Agent ──────────────────────────────────────────────────────────────────

    @property
    def agent(self) -> AgentClient
        # Returns the domain agent for this project
        # Cloud only — local mode raises NotImplementedError for agent methods
```

---

## `OntologyView`

Wraps the owlready2 World for convenient access. Available in both modes (cloud mode downloads `onto.db` on first access).

```python
class OntologyView:
    world: World          # raw owlready2 World
    onto: Ontology        # loaded OWL ontology

    def classes(self) -> list[type]
        # Returns all OWL classes

    def instances(self, class_name: str) -> list[Any]
        # Returns all instances of a class as owlready2 individuals

    def individual(self, uri: str) -> Any
        # Looks up an individual by URI local name or full IRI

    def __getattr__(self, class_name: str) -> type
        # Convenience: project.ontology().State → onto.State class
```

**Usage:**
```python
onto = project.ontology()
for state in onto.State.instances():
    print(state.hasName, state.hasPopulation)

# Direct owlready2 access
nj = onto.individual("State_34")
print(nj.hasName)           # "New Jersey"
print(nj.hasPart)           # list of County individuals
```

---

## `AgentClient`

```python
class AgentClient:
    def ask(
        self,
        message: str,
        history: list[dict] | None = None,
        model: str | None = None,
        session_id: str | None = None,
        stream: bool = False,
    ) -> str | Generator[AgentEvent, None, None]
        # When stream=False (default): blocks until agent finishes, returns final text
        # When stream=True: yields AgentEvent dicts as they arrive via SSE
        # Cloud only — POST /api/v1/agent/chat?project={slug}

    def new_session(self) -> str
        # Creates a new agent session; returns session_id

    def sessions(self) -> list[dict]
        # Lists all agent sessions for this project
```

**Usage:**
```python
# Simple blocking call
answer = project.agent.ask(
    "What is the average unemployment rate in NJ counties in 2023?"
)
print(answer)

# Streaming (show tool calls as they happen)
for event in project.agent.ask("Analyze housing trends", stream=True):
    if event["type"] == "text_delta":
        print(event["content"], end="", flush=True)
    elif event["type"] == "tool_call":
        print(f"\n[tool: {event['name']}]")
    elif event["type"] == "done":
        break
```

---

## `HydrationResult`

```python
@dataclass
class HydrationResult:
    job_id: str               # cloud only; "local" in local mode
    status: str               # "success" | "failed"
    duration_seconds: float
    steps: list[dict]         # [{stepName, status, rowCount}]
    error: str | None
    onto_db_path: str         # local path to onto.db
    duckdb_path: str          # local path to onto.duckdb
```

---

## `ExecuteResult`

```python
@dataclass
class ExecuteResult:
    stdout: str
    stderr: str
    dataframes: dict[str, pd.DataFrame]   # variable name → DataFrame
    figures: list[str]                     # base64 PNG strings
    error: str | None
```

---

## Local Mode Internals

In local mode, `rail.local(path)` does the following on construction:
1. Reads `rail.yaml` from the project root to discover pipeline slugs and settings.
2. Adds `{engine_path}/engine/` to `sys.path` so engine modules can be imported.
3. Locates `onto.db` and `onto.duckdb` in `ontology/` (if they exist).
4. Does **not** start a server or connect to Convex.

`project.hydrate()` in local mode:
1. Resolves the pipeline YAML path from `configs/pipelines/{slug}.yaml`.
2. Reads connector templates from Convex if API credentials are set; otherwise raises an error if any API config uses `extends`. (Local mode can work fully offline only if no connector template resolution is needed — i.e., all API configs are fully self-contained.)
3. Calls `engine.pipeline_runner.run_pipeline(pipeline_path)` directly.
4. Returns a `HydrationResult` populated from the engine's output.

`project.query(sql)` in local mode opens a DuckDB connection to the local `onto.duckdb` file directly — no HTTP involved.

---

## Example Workflows

### Explore a project locally

```python
import rail, pandas as pd

project = rail.local("./nj-economics")

# Browse classes
for cls in project.classes():
    print(cls["name"], cls["instanceCount"])

# SQL query
df = project.query("""
    SELECT hasName, hasValue, hasDate
    FROM LaborIndicator
    WHERE hasSeries = 'NJURN'
    ORDER BY hasDate DESC
    LIMIT 24
""")
print(df.to_string())

# Time series
ts = project.series("NJURN")
ts.plot(x="date", y="value", title="NJ Unemployment")
```

### Run hydration and inspect results

```python
import rail

project = rail.local("./nj-economics")
result = project.hydrate("nj-hydration")

if result.status == "success":
    print(f"Hydrated in {result.duration_seconds:.1f}s")
    for step in result.steps:
        print(f"  {step['stepName']}: {step['rowCount']} individuals")

    # Query the fresh ontology
    df = project.query("SELECT COUNT(*) as n FROM LaborIndicator")
    print(f"LaborIndicators: {df['n'][0]}")
```

### Connect to the platform

```python
import rail

project = rail.connect("nj-economics")   # uses RAIL_API_URL env var

# Ask the domain agent a research question
answer = project.agent.ask(
    "Compare unemployment trends in Bergen and Essex counties since 2020"
)
print(answer)
```

### Direct owlready2 access

```python
import rail

project = rail.local("./nj-economics")
onto = project.ontology()

# Use owlready2 directly for graph traversal
nj = onto.individual("State_34")
counties = list(nj.hasPart)           # all NJ counties
for county in sorted(counties, key=lambda c: c.hasName or ""):
    print(county.hasName, county.hasPopulation)
```
