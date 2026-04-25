# Rutgers Agentic Intelligence Labs — YAML-Driven Ontology Engine

A declarative knowledge-graph engine for economic analysis. APIs, ontology schemas, and hydration pipelines are all defined in YAML — no domain Python is required to add new data sources or extend the ontology.

Inspired by Palantir Foundry's Ontology layer, built on [owlready2](https://owlready2.readthedocs.io/), [Census Bureau API](https://api.census.gov/), and [FRED API](https://fred.stlouisfed.org/docs/api/fred/).

---

## Quick Start

### 1. Initial Setup
Run the one-step setup to install all dependencies (API, Engine, and Web) and seed the initial configuration:

```bash
make setup
```

### 2. Set API Keys
Ensure your `.env` file (or environment) has the necessary keys:

```bash
export FRED_API_KEY=your_key_here
```

### 3. Start the Platform
Launch both the FastAPI backend and the Next.js Command Center:

```bash
make run
```

- **API**: [http://localhost:8000](http://localhost:8000)
- **Command Center**: [http://localhost:3000](http://localhost:3000)

### 4. Hydrate the Ontology (Optional)
If you need to fetch fresh data and rebuild the knowledge graph:

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
