# Streamlit UI (`app.py`)

> **Legacy local tool.** The Streamlit explorer (`packages/engine/app.py`) remains in the repository as a lightweight standalone utility for local engine development and debugging. It is not the target product surface for the future planner-first platform and will not receive major new features.

---

Served with `streamlit run app.py`. Page title: "RAIL Explorer". App heading: "Rutgers Agentic Intelligence Labs".

## Startup

> **Note:** All paths in this document are relative to the `packages/engine/` directory.

On startup, if `ontology/onto.db` does not exist, the app shows `st.error("Ontology database not found. Run: python hydrate.py")` and calls `st.stop()`.

The ontology is loaded once per server session via `@st.cache_resource`:

```python
world = World()
world.set_backend(filename=path)
onto = world.get_ontology("http://example.org/rutgers_ontology.owl").load()
```

This avoids repeated SQLite opens across Streamlit reruns within the same session.

## Node Colors

Used in both graph tabs (Tab 1 and Tab 3):

| Class | Color | Name |
|-------|-------|------|
| State | `#F5A623` | amber |
| County | `#4A9EDD` | blue |
| Municipality | `#50C878` | green |
| Individual | `#B07FD4` | purple |
| Measure | `#E05C5C` | red |

## Tab 1: Ontology Explorer

Layout: sidebar + two columns (ratio 1:3).

**Sidebar:** text input labeled "Search entities", placeholder `"e.g. 'Alice', 'New Jersey'"`.

**Left column:**

- `st.selectbox` for entity type: `All`, `State`, `County`, `Municipality`, `Individual`. Note: `Measure` is not included.
  - `All` → `list(onto.individuals())`
  - Others → `list(onto.{ClassName}.instances())`
- If a search term is entered, entities are filtered to those where the search term appears (case-insensitive) in `e.name` or in `e.hasName`.
- `st.selectbox` of entity URI local names from the filtered list.
- When an entity is selected:
  - **Properties panel:** IRI displayed as inline code. Then, for each of `hasName` (label "Name", format `{}`), `hasPopulation` (label "Population", format `{:,}`), `hasIncome` (label "Income", format `${:,.2f}`), `hasFIPS` (label "FIPS", format `{}`): shown only if the value is truthy.
  - **Relationships panel:** iterates `selected.get_properties()`; for each property, iterates `prop[selected]`; displays `prop.python_name` and the value's `.name` (for object values) or the value itself.

**Right column:**

- 1-hop relationship graph using `pyvis.Network(height="600px", width="100%", bgcolor="#1a1a2e", font_color="white", directed=True)`.
- Selected node: color `#ff4b4b`, size 30.
- Neighbor nodes: color `#00acee`. Label is `hasName` if set, otherwise `ind.name`.
- Outgoing edges: from `selected.get_properties()` — adds nodes and directed edges for all object values.
- Incoming edges: from `selected.get_inverse_properties()` — adds nodes and directed edges pointing toward the selected node.
- Edge labels: `prop.python_name`.
- Graph saved to `graph.html` and rendered via `streamlit.components.v1.html`.

## Tab 2: Data Analysis

Heading: "Economic Indicators".

Loads all `Measure` instances. Builds a `state_name → [Measure]` map by reading `measuredFor` from each measure. `measuredFor` is a non-functional property; owlready2 returns a list, so the first element is used.

If no measures exist, shows `st.info`.

**State selector:** dropdown of sorted state names derived from `hasName` (or `.name` if `hasName` is absent).

**Series ID display names** are inferred from the FRED series ID:

| Pattern | Display Label | Unit | Frequency |
|---------|---------------|------|-----------|
| Ends with `URN` | `"{abbr} Unemployment Rate"` | `%` | Monthly |
| Ends with `STHPI` | `"{abbr} House Price Index"` | `Index` | Quarterly |
| Starts with `MEHOINUS`, ends with `A646N` | `"{abbr} Median Household Income"` | `$` | Annual |
| Other | raw series ID | `""` | `""` |

**Overview cards:** one `st.metric()` per series found for the selected state. Value is formatted as `"{unit}{latest:,.2f}"` for `$` unit, or `"{latest:.2f}{unit}"` otherwise. Delta is `latest - prev` (second-to-last observation).

**Series detail:** selectbox to choose one series. Shows:
- 5 stat metrics: Latest, Mean, Min, Max, Total Change % (calculated as `(last - first) / first * 100`).
- A line chart of `Date` vs `Value`.
- Expander "Descriptive Statistics": `df["Value"].describe()` formatted to 4 decimal places.
- Expander "Raw Data": the DataFrame renamed with the series label and unit as the column header, height 300.

**Compare series:** `st.multiselect` defaulting to all available series. Renders a normalized overlay chart. All selected series are individually indexed to 100 at their first observation, then merged on `Date`. Caption: `"Normalized to 100 at start date for comparability"`.

## Tab 3: Graph Explorer

Heading: "Graph Explorer". Two-column layout (ratio 1:4).

**Left column (filters):**

- `st.multiselect` for entity types: options are all 5 node colors. Default: `["State", "County", "Municipality", "Individual"]`.
- State focus selector: shown when County or Municipality is in the selected types. A selectbox of all State individuals, with `"— All states (no municipalities) —"` as the first option. Defaults to New Jersey (found by substring match on the label).
- Toggle "Show edge labels" (default on).
- Toggle "Size nodes by population" (default on).
- Color legend: filled circle + class name for each selected type.

**Right column (graph):**

When Municipality is in selected types but no state is focused: `st.info` message. Municipalities are never shown unless a state is focused.

When a state is focused:
- Counties are filtered to those where `isPartOf == focus_state_ind`.
- Municipalities are filtered to those where `isPartOf` is in the focused county set.

**Node sizing** (when "Size nodes by population" is on):

Population range per type is pre-computed across all visible nodes. Size is linearly interpolated within the type's range:

| Type | Min size | Max size | Notes |
|------|----------|----------|-------|
| State | 22 | 55 | |
| County | 10 | 28 | |
| Municipality | — | — | Fixed 14 |
| Individual | — | — | Fixed 12 |
| Measure | — | — | Fixed 8 |

When "Size nodes by population" is off, the minimum of the range is used for sized types.

**Node tooltip** shows: class name (colored), hasName, hasFIPS, hasPopulation (formatted `{:,}`), hasIncome, hasValue, hasDate, hasSeries — only non-null attributes.

**pyvis configuration:**

- `bgcolor="#0d1117"`, `font_color="#e6edf3"`, `directed=True`.
- Node style: shape `dot`, shadow enabled (size 6, offset 2,2), border width 1.
- Edge style: color `#484f58`, highlight/hover color `#adbac7`, width 1.2, selection width 2.5, smooth type `dynamic`, arrow scale 0.5.
- Physics: Barnes-Hut solver, gravitationalConstant `-6000`, centralGravity `0.3`, springLength `160`, springConstant `0.04`, damping `0.09`, avoidOverlap `0.4`, stabilization 200 iterations at 25-iteration update interval, maxVelocity 50, minVelocity 0.5.
- Interaction: hover enabled, tooltipDelay 80ms, navigation buttons, keyboard shortcuts, multiselect, zoom.

**Edges** are only added between nodes present in the filtered set. Duplicate edges (same source, target, property name) are deduplicated. Edge labels show `prop.python_name` when "Show edge labels" is on.

Caption shows: `"Showing {N} nodes · {E} edges — drag to pan, scroll to zoom, click to select"`.

Graph saved to `graph_full.html` and rendered via `components.html(height=720, scrolling=False)`.

## Tab 4: Analysis

Heading: "Analysis". Caption: `"Drop a .py file with analyze(onto) into the analysis/ directory and it appears here automatically."`.

Discovers plugins via `engine.analysis_runner.discover()`.

If no modules are found, shows `st.info`.

Two-column layout (ratio 1:4):

**Left column:**
- `st.radio` list of available modules, labeled by `NAME` attribute (falls back to stem).
- "Run" button (primary style, full width).
- Static code snippet showing the analysis plugin API.

**Right column:**
- Before run: `st.info("Select a module on the left and click Run.")`.
- On run: calls `module.analyze(onto)` inside `st.spinner`. On success: `st.success(f"{result['title']} — complete")`, then renders each section via `_render_section`. On failure: `st.error` with exception message and `st.exception` traceback.

## CLI Entry Point (`hydrate.py`)

```
python hydrate.py [--pipeline PATH]
```

`--pipeline` defaults to `configs/pipelines/nj_hydration.yaml`. Calls `engine.pipeline_runner.run_pipeline(args.pipeline)`.

## Footer

`st.markdown("---")` followed by `st.caption("Rutgers Agentic Intelligence Labs — 2026")`.
