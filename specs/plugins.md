# Plugin System

RAIL has two plugin types: **transform plugins** (operate on DataFrames or the ontology during hydration) and **analysis plugins** (query the populated ontology and return renderable results).

---

## Transform Plugins

### Location and Reference

Transform plugins live in `transforms/{module_name}.py`. Reference them in a pipeline step as:

```yaml
transform: "module_name::function_name"
```

Or in `post_hydration_transforms` as:

```yaml
post_hydration_transforms:
  - "module_name::function_name"
  - spec: "module_name::function_name"
    config: {key: value}
```

If no `::` separator is present, the function name defaults to `"transform"`.

The loader searches `transforms/` first; if the file is not found there, it falls back to standard `importlib.import_module`.

### DataFrame Transform

**Signature:** `def fn(df: pd.DataFrame, **kwargs) -> pd.DataFrame`

- Receives the DataFrame produced by `fetch_api` for the current step.
- Must return a DataFrame. Returning `None` raises `ValueError`.
- `**kwargs` receives values from `transform_config` in the pipeline step.
- Called by `transform_runner.run_dataframe_transform`.

### Ontology Transform

**Signature:** `def fn(onto, **kwargs) -> None`

- Receives the live owlready2 `onto` object after all pipeline steps have completed.
- Modifies the ontology in-place; return value is ignored.
- `**kwargs` receives values from the `config` map in `post_hydration_transforms`.
- Called inside `with onto:` by `transform_runner.run_ontology_transform`.

---

### Built-in Transforms (`transforms/census_clean.py`)

**`strip_state_suffix(df) -> pd.DataFrame`**

Operates on the `name` column. Splits on `","` and takes the first part, stripping whitespace.

Example: `"Essex County, New Jersey"` → `"Essex County"`.

Returns the original DataFrame unchanged if `name` is not a column.

---

**`strip_municipality_name(df) -> pd.DataFrame`**

Operates on the `raw_name` column (not `name`). Returns the original DataFrame unchanged if `raw_name` is not a column.

1. Removes rows where `raw_name` starts with `"County subdivisions not defined"`.
2. Splits `raw_name` on `","` and takes the first part, stripping whitespace → new `name` column.
3. Resets the index.

Example: `"Hoboken city, Hudson County, New Jersey"` → `"Hoboken city"`.

---

**`add_state_abbreviations(df) -> pd.DataFrame`**

Operates on the `fips` column. Adds an `abbr` column by mapping FIPS code strings to 2-letter state abbreviations. Drops rows with no known abbreviation.

Returns the original DataFrame unchanged if `fips` is not a column.

Coverage: all 50 US states, DC (`"11"`), and Puerto Rico (`"72"`).

FIPS → abbreviation map (51 entries):

```
"01"→AL  "02"→AK  "04"→AZ  "05"→AR  "06"→CA  "08"→CO  "09"→CT
"10"→DE  "11"→DC  "12"→FL  "13"→GA  "15"→HI  "16"→ID  "17"→IL
"18"→IN  "19"→IA  "20"→KS  "21"→KY  "22"→LA  "23"→ME  "24"→MD
"25"→MA  "26"→MI  "27"→MN  "28"→MS  "29"→MO  "30"→MT  "31"→NE
"32"→NV  "33"→NH  "34"→NJ  "35"→NM  "36"→NY  "37"→NC  "38"→ND
"39"→OH  "40"→OK  "41"→OR  "42"→PA  "44"→RI  "45"→SC  "46"→SD
"47"→TN  "48"→TX  "49"→UT  "50"→VT  "51"→VA  "53"→WA  "54"→WV
"55"→WI  "56"→WY  "72"→PR
```

---

**`normalize_fips(df, pad_width=2) -> pd.DataFrame`**

Zero-pads the `fips` column to `pad_width` characters using `str.zfill(pad_width)`.

Default `pad_width` is `2`. Override via `transform_config: {pad_width: N}`.

Returns the original DataFrame unchanged if `fips` is not a column.

---

## Analysis Plugins

### Location and Discovery

Analysis plugins live in `analysis/{module_name}.py`. Any file in that directory that:
1. Does **not** start with `_`
2. Exports an `analyze` attribute

is auto-discovered by `analysis_runner.discover()` and appears in the Analysis tab of the Streamlit app.

### Module-Level `NAME`

A module-level `NAME` string is used as the display label in the Streamlit UI. If absent, the module filename stem is used instead.

### Analysis Function

**Signature:** `def analyze(onto, **kwargs) -> dict`

The `onto` argument is the live owlready2 ontology loaded from `ontology/onto.db`.

**Return value schema:**

```python
{
    "title": str,       # shown as st.success() banner after run
    "sections": [...]   # list of section dicts
}
```

### Section Types

All section types optionally accept a `"title"` key, rendered as `st.subheader()` before the section content.

| `type` | Required keys | Rendered as |
|--------|--------------|-------------|
| `"metrics"` | `items: [{"label": str, "value": any}, ...]` | `st.columns` of `st.metric()` |
| `"table"` | `data: pd.DataFrame` | `st.dataframe(use_container_width=True, hide_index=True)` |
| `"chart"` | `data: pd.DataFrame`, `x: col_name`, `y: col_name` | `st.line_chart(data.set_index(x)[y])` |
| `"text"` | `content: str` | `st.markdown(content)` |
| `"divider"` | — | `st.divider()` |
| `"group"` | `items: [section, ...]` | recursively renders each nested section |

For `"table"`: if `data` is `None` or empty, renders `st.caption("No data.")` instead.

For `"metrics"`: the number of `st.columns` equals `max(len(items), 1)`.

---

### Built-in Analysis (`analysis/builtins.py`)

`NAME = "Built-in Ontology Analysis"`

Runs four analyses in sequence, separated by dividers:

**1. Entity Summary**

Table with columns `{Type, Instances}`. One row per class that has at least one instance, sorted by class name, plus a `TOTAL` row. Uses `cls.instances()` for each class in `onto.classes()`.

**2. Property Completeness**

Table with columns `{Class, Property, Filled, Total, Completeness}`. One row per class × property combination where `Filled > 0`. A value counts as filled if it is not `None`, not `[]`, and not `""`. Iterates over all classes in `onto.classes()` and all properties in `onto.properties()`.

**3. Population Insights**

Two separate tables — top 10 States and top 10 Counties by `hasPopulation`. Population values are formatted with commas. Rows with `hasPopulation is None` are excluded.

**4. Relationship Coverage**

Table with columns `{Class, Property, Linked, Total, Coverage}`. One row per domain class of each object property. A value counts as linked if it is not `None` and not `[]`. Only iterates over properties that are subclasses of `ObjectProperty`.

---

### Example Analysis (`analysis/unemployment_trends.py`)

`NAME = "NJ Unemployment Trends"`

Filters `Measure` instances where `hasSeries == "NJURN"`, collecting `{date, value}` pairs where both `hasDate` and `hasValue` are non-null.

If no `Measure` class exists in the ontology, returns a single `"text"` section with an error message.

If no `NJURN` data is found, returns a single `"text"` section with an error message.

Otherwise returns three sections:

1. **Metrics** — Latest (value + date), Historical Mean, Peak (value + date), Trough (value + date), and Year-over-Year Change. YoY change is computed as `df.iloc[-1]["value"] - df.iloc[-13]["value"]` and is only included if there are at least 13 observations. Unit is percentage points (`pp`).

2. **Chart** — Line chart of `date` vs `value`, titled `"NJ Unemployment Rate (Monthly, %)"`.

3. **Text** — Source attribution: Bureau of Labor Statistics LAUS programme via FRED series `NJURN`; seasonally adjusted monthly unemployment rates.
