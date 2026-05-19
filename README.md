# RAIL: The Agentic Data OS

RAIL (Rutgers Agentic Intelligence Labs) is a repo-centric **Data Operating System** designed for economic research. It treats a Git repository as the primary source of truth for ontology schemas, data hydration pipelines, and research logic.

### The Vision
- **Repo-Centric**: Everything from data lineage to research plans lives in the repository.
- **Agent-First**: Designed for autonomous agents (Research Agent & Jules) to operate natively via bash and the `rail` CLI.
- **Semantic Navigation**: Move beyond keyword search with `lgrep` for semantic discovery across documents and data.
- **Declarative Hydration**: Unify disparate APIs (Census, FRED, etc.) into a cohesive knowledge graph via YAML.

---

## First-time setup

Use this checklist the first time you install RAIL on a machine.

### Requirements

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| git | any recent |
| Convex | deployment URL + deploy key (cloud mode) |

Optional: [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) and other provider keys for hydration pipelines.

### Option A — Install from GitHub Release (recommended)

After [releases](https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases) exist for your version:

```bash
curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
```

The installer downloads a source bundle, creates a virtualenv, installs Python packages and the web app, and prints the install path (default `~/rail-platform`).

### Option B — Install from a git clone (developers)

```bash
git clone https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git
cd RutgersAgenticIntelligenceLabs
./scripts/install-rail.sh
# equivalent: make setup
```

### Configure environment

```bash
cd RutgersAgenticIntelligenceLabs   # or your install path
cp .env.example .env
```

Edit `.env` and set at minimum:

```bash
CONVEX_URL=https://your-deployment.convex.cloud
CONVEX_DEPLOY_KEY=your_deploy_key
FRED_API_KEY=your_fred_key          # for FRED hydration pipelines
```

### Start the platform

```bash
make run
```

| Service | URL |
|---------|-----|
| Command Center (UI) | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Open a project in the UI → **Overview**. Use **Fetch data & hydrate** to reconcile state, run pipelines, and refresh the ontology DuckDB in one step.

### Create or open a research project

**Cloud (Convex):** use the web UI to create a project, or connect an existing slug via the project picker.

**Local (no Convex):** work inside a directory that contains `rail.yaml`:

```bash
export RAIL_LOCAL=1
export RAIL_PATH=/path/to/your/project
rail query classes
```

### Optional: agent CLIs

RAIL does not bundle Cursor, Copilot, or other proprietary tools. To install or check Codex, Claude Code, Gemini CLI, and similar:

```bash
./scripts/install-agent-clis.sh
```

### Optional: MCP for Cursor / Claude Desktop

```bash
pip install -e packages/mcp-server
```

See [AGENTS.md](AGENTS.md) for MCP tool reference and example config.

### Verify the install

```bash
make install-rail
rail --help
curl -s http://localhost:8000/health
```

More detail: [docs/INSTALL.md](docs/INSTALL.md) · Release process: [RELEASE.md](RELEASE.md) · [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)

---

## Quick reference

### Secrets

```bash
make secrets-set KEY=FRED_API_KEY VAL=your_key_here
```

### CLI

```bash
rail search "unemployment"
rail query sql "SELECT * FROM county LIMIT 5"
rail hydrate
rail integrity status
```

### Hydrate from the terminal

```bash
make hydrate
```

---

## Repository Layout

```
RutgersAgenticIntelligenceLabs/
├── hydrate.py                    # CLI entry point
├── app.py                        # Streamlit explorer
│
├── engine/                       # Core engine (no domain knowledge)
│   ├── api_runner.py             # Fetches and normalizes data sources
│   ├── ontology_builder.py       # Builds owlready2 ontology from YAML/OWL
│   ├── pipeline_runner.py        # Orchestrates hydration steps
│   ├── transform_runner.py       # Loads and runs transform plugins
│   └── analysis_runner.py        # Discovers and runs analysis plugins
│
├── configs/
│   ├── ontology/
│   │   └── core.yaml             # Classes and properties declaration
│   ├── apis/                     # One YAML per data source
│   │   ├── census_states.yaml
│   │   ├── census_counties.yaml
│   │   ├── census_municipalities.yaml
│   │   ├── fred_nj_unemployment.yaml
│   │   └── ...
│   └── pipelines/
│       └── nj_hydration.yaml     # Wires APIs → ontology classes
│
├── transforms/                   # DataFrame / ontology transform plugins
│   └── census_clean.py
│
├── analysis/                     # Analysis plugins
│   ├── builtins.py
│   └── unemployment_trends.py
│
├── ontology/                     # Generated output (git-ignored)
│   ├── onto.db                   # SQLite quadstore
│   └── populated_ontology.owl    # RDF/XML export
│
└── cache/                        # HTTP response cache (git-ignored)
```

---

## How the Engine Works

The engine has four layers: **API configs** fetch raw data, **ontology configs** declare the schema, **pipeline configs** wire them together, and **plugins** extend cleaning and analysis without touching engine code.

### Layer 1 — API Configs (`configs/apis/*.yaml`)

Each YAML file describes one data source. The engine has no hardcoded API knowledge.

```yaml
# configs/apis/fred_nj_unemployment.yaml
name: fred_nj_unemployment
type: api
url: https://api.stlouisfed.org/fred/series/observations
params:
  series_id: NJURN
  api_key: ${FRED_API_KEY}       # resolved from environment at runtime
  file_type: json
  observation_start: "2010-01-01"
response_format: json
response_path: observations      # extract nested key from JSON response
cache: true
drop_na: true                    # drop rows where any field is NaN
fields:
  - source: date
    alias: date
  - source: value
    alias: value
    cast: float                  # coerces FRED's "." missing values to NaN
```

**Supported source types:** `api` (HTTP GET), `csv`, `excel`

**`foreach` — iterate over a parent dataset:**

```yaml
# configs/apis/census_municipalities.yaml
foreach:
  source: census_states          # must have been fetched earlier in the pipeline
  field: fips
  filter: "fips in ['34', '36']" # pandas .query() expression
  inject_param: "in"
  inject_template: "state:{fips}" # becomes ?in=state:34 for NJ, state:36 for NY
```

This makes one HTTP request per matching parent row, concatenates the results, and returns a single DataFrame. Two requests (NJ + NY) produce all 1,579 municipalities.

**`response_path`** extracts a nested key before parsing — FRED wraps observations under `{"observations": [...]}`.

**`computed` fields** assemble values from other aliased columns:

```yaml
fields:
  - source: state
    alias: state_fips
  - source: county
    alias: county_fips
  - computed: "{state_fips}{county_fips}"
    alias: full_county_fips
```

**Environment variables** anywhere in a YAML value use `${VAR_NAME}` syntax; the engine substitutes from `os.environ` at load time.

---

### Layer 2 — Ontology Schema (`configs/ontology/*.yaml`)

Defines OWL classes, object properties, and data properties. The engine builds a live owlready2 ontology from this spec — or you can point it at an existing `.owl` file instead.

```yaml
# configs/ontology/core.yaml
uri: http://example.org/rutgers_ontology.owl

classes:
  - name: State
  - name: County
  - name: Municipality
  - name: Individual
  - name: Measure

object_properties:
  - name: isPartOf
    domain: [County, Municipality]
    range: [State, County]
    inverse: hasPart              # creates the inverse property automatically

data_properties:
  - name: hasPopulation
    domain: [State, County, Municipality]
    range: int
    functional: true              # OWL FunctionalProperty — at most one value
```

Supported `range` types for data properties: `str`, `int`, `float`.

---

### Layer 3 — Pipeline Config (`configs/pipelines/*.yaml`)

The pipeline wires API configs to ontology classes. Each step:
1. Fetches a DataFrame (via `api_runner`)
2. Optionally transforms it (via `transform_runner`)
3. Maps each row to an OWL individual
4. Sets data properties from column templates
5. Resolves and links object property relationships

```yaml
# configs/pipelines/nj_hydration.yaml
ontology: configs/ontology/core.yaml
output_owl: ontology/populated_ontology.owl
db: ontology/onto.db

steps:
  - name: load_counties
    api: census_counties
    transform: "census_clean::strip_state_suffix"   # module::function
    class: County
    uri: "County_{full_fips}"          # {field} placeholders, URI-safe sanitized
    properties:
      hasName: "{name}"
      hasFIPS: "{full_fips}"
      hasPopulation: "{population}"
    relationships:
      - property: isPartOf
        target_class: State
        target_uri: "State_{state_fips}"  # must already exist in the graph
```

**URI templates** use `{column_name}` placeholders. Characters that are invalid in OWL local names (spaces, commas, etc.) are replaced with `_` automatically.

**`create_if_missing`** on a relationship creates a stub individual if the target doesn't exist yet:

```yaml
relationships:
  - property: locatedIn
    target_class: Municipality
    target_uri: "Municipality_{municipality}"
    create_if_missing: true
    create_with_properties:
      hasName: "{municipality}"
```

**Step ordering matters.** Steps run sequentially. `foreach` sources and relationship targets must appear in earlier steps. The `resolved` dict carries each step's DataFrame forward for later `foreach` references.

---

### Layer 4 — Plugins

#### Transform Plugins (`transforms/`)

Transforms clean data *before* it is mapped to the ontology.

**DataFrame transforms** receive a `pd.DataFrame` and return one:

```python
# transforms/census_clean.py
def strip_state_suffix(df, **kwargs):
    """'Essex County, New Jersey' → 'Essex County'"""
    if "name" in df.columns:
        df = df.copy()
        df["name"] = df["name"].str.split(",").str[0].str.strip()
    return df
```

Reference in a pipeline step:

```yaml
transform: "census_clean::strip_state_suffix"
transform_config:                # optional kwargs passed to the function
  pad_width: 3
```

**Ontology transforms** operate on the live owlready2 `onto` object after hydration:

```python
def my_post_transform(onto, **kwargs):
    with onto:
        for ind in onto.individuals():
            # modify, infer, add triples ...
```

Reference in the pipeline's `post_hydration_transforms` list:

```yaml
post_hydration_transforms:
  - spec: "my_module::my_post_transform"
    config: {}
```

#### Analysis Plugins (`analysis/`)

Analysis plugins query the populated ontology and return structured results for display in the Streamlit app.

```python
# analysis/unemployment_trends.py
NAME = "NJ Unemployment Trends"   # display name in the UI

def analyze(onto, **kwargs) -> list:
    """Return a list of section dicts."""
    measures = [m for m in onto.search(type=onto.Measure)
                if m.hasSeries == "NJURN"]
    # ... compute metrics ...
    return [
        {"type": "metrics", "items": [{"label": "Latest", "value": "4.2%"}]},
        {"type": "chart",   "data": df, "x": "date", "y": "value"},
        {"type": "text",    "content": "Unemployment peaked in April 2020."},
    ]
```

The engine auto-discovers any `analysis/*.py` file that exports `analyze()` — drop a file in the folder and it appears in the UI immediately.

**Supported section types:** `table`, `metrics`, `chart`, `text`, `divider`, `group`

---

## Streamlit Explorer Tabs

### Tab 1 — Ontology Explorer
Browse all individuals by class. Select one to see its data properties and a 1-hop interactive graph showing all related individuals.

### Tab 2 — Data Analysis
FRED time-series overview with metric cards, trend charts, normalized cross-series comparison, and descriptive statistics.

### Tab 3 — Graph Explorer
Full Neo4j-style interactive graph using pyvis/vis.js. Filter by node type, toggle edge labels, scale node size by population. Uses Barnes-Hut physics for layout.

### Tab 4 — Analysis
Run built-in or custom analysis plugins. Results render as tables, metric cards, charts, and text. Includes the plugin interface spec so contributors know exactly what to implement.

---

## Adding a New Data Source

1. Create `configs/apis/my_source.yaml` — declare the URL, params, fields.
2. Add a step to `configs/pipelines/nj_hydration.yaml` (or create a new pipeline YAML).
3. If the new source needs cleaning, add a function to `transforms/` and reference it with `transform: "module::function"`.
4. Run `python hydrate.py` — no engine code changes needed.

## Adding a New Ontology Class

1. Add the class name under `classes:` in `configs/ontology/core.yaml`.
2. Add any new properties under `object_properties:` or `data_properties:`.
3. Add a pipeline step that maps an API to the new class.

## Adding Custom Analysis

Drop a Python file in `analysis/` that exports `NAME` (str) and `analyze(onto, **kwargs) -> list`. It will appear in the Analysis tab automatically.

---

## Architecture Notes

**Why `World()` instead of `default_world`?**
owlready2 eagerly loads OWL/RDFS base ontologies into `default_world` at import time. Opening an existing SQLite quadstore into a pre-populated world raises `"Cannot save existent quadstore"`. Using `World()` creates a fully empty world so the existing DB opens cleanly.

**Why `@st.cache_resource` on the ontology load?**
Streamlit re-runs the entire script on every widget interaction. Without caching, each interaction would open a new `World()` connection to the same SQLite file while the previous one was still open — causing `sqlite3.OperationalError: database is locked`. `@st.cache_resource` keeps one `World` + `onto` open per server session.

**Individual lookup cache (`_cache` dict)**
Each `onto.search_one()` is a SQLite query. The NJ municipalities step processes 1,579 rows, and each row must look up its parent county. Without a cache that's ~1,579 repeated queries for ~21 counties. The in-memory `_cache = {uri: individual}` dict reduces those to 21 queries + dictionary lookups, dropping hydration time to ~2 seconds.

**FRED missing values**
FRED returns the string `"."` for data points not yet available. Standard `int()` / `float()` casts raise `ValueError`. The engine uses `pd.to_numeric(errors='coerce')` which converts `"."` to `NaN`, then `drop_na: true` in the API config removes those rows cleanly.

---

## The Data OS Architecture

RAIL operates as a **Agentic Data Operating System** where the repository is the kernel.

### 📁 Repository as State
Unlike traditional platforms that store research state in a hidden database, RAIL flattens state into the filesystem:
- **`configs/`**: The system's "drivers" (APIs, pipelines, ontology).
- **`research_plan/`**: The system's "process table" (active tasks, decisions, logs).
- **`ontology/`**: The system's "disk" (hydrated DuckDB and OWL storage).

### 🤖 Agent-Native Interface
Agents don't call APIs; they execute bash. The `rail` CLI provides a standardized interface for:
- **Discovery**: `rail search "census"`
- **Analysis**: `rail query sql "..."`
- **Hydration**: `rail hydrate`
- **Secrets**: `rail secrets list`

### 🔑 Secret Management
RAIL uses server-side Fernet encryption for API keys. You can manage them via the CLI or Makefile:

```bash
# List secrets (masked)
make secrets-list

# Set a new secret
make secrets-set KEY=FRED_API_KEY VAL=abc123...
```

The `rail-py` library automatically resolves these secrets for agents based on their assigned role policy (e.g., the `data` agent can access `FRED_API_KEY`, but the `coding` agent cannot).

---

## Environment Variables

| Variable | Used by | Description |
|---|---|---|
| `FRED_API_KEY` | `configs/apis/fred_*.yaml` | FRED API key for economic data |

Set any `${VAR_NAME}` reference in an API config YAML and it will be resolved from the environment at runtime.

---

## Development

```bash
# Re-hydrate from scratch (deletes onto.db and cache)
python hydrate.py

# Run a different pipeline
python hydrate.py --pipeline configs/pipelines/my_pipeline.yaml

# Start the explorer
streamlit run app.py
```

Cache files in `cache/` persist across runs. Delete them to force fresh API fetches.
