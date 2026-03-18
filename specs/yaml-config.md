# YAML Configuration Schemas

There are three kinds of YAML configuration files: API source configs, the ontology schema, and pipeline configs.

> **Note:** All paths in this document are relative to the `packages/engine/` directory.

---

## API Source Config (`configs/apis/*.yaml`)

Defines one data source. The filename stem is the API name used to reference the source in pipeline steps and `foreach` clauses.

### Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Must match the filename stem. Used as the key in `resolved_data` and as the base for cache filenames. |
| `type` | string | yes | `api`, `csv`, or `excel` |
| `fields` | list | no | Column mapping rules (see below). If absent, the raw columns are passed through unchanged. |

### `type: api`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | HTTP endpoint. `${VAR_NAME}` tokens are replaced with environment variables. |
| `params` | map | no | Query parameters appended to the request. `${VAR_NAME}` tokens are resolved from environment variables. |
| `response_format` | string | yes | `json` or `census_array` |
| `response_path` | string | no | If set, extracts `raw[response_path]` from the JSON response before parsing (e.g., `observations` for FRED responses). |
| `cache` | boolean | default `true` | Cache the HTTP response to `cache/`. Set `false` to always re-fetch. |
| `drop_na` | boolean | no | If `true`, drop rows with any NaN values after field mapping. |
| `foreach` | map | no | Iterate over a parent dataset (see below). |

**`response_format` values:**

- `census_array` — the response is a 2D array where `raw[0]` is the column header row and `raw[1:]` are data rows.
- `json` — if the response is a list, `pd.DataFrame(raw)`; if the response is a dict, `pd.DataFrame([raw])`.

### `type: csv`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Path to the CSV file, read with `pd.read_csv()`. |

### `type: excel`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Path to the Excel file, read with `pd.read_excel()`. |

### `foreach`

Causes the API to be called once per row of a parent dataset. The parent dataset must have been resolved by an earlier pipeline step.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | yes | Name of a previously resolved API. Must match a key already in `resolved_data`. |
| `field` | string | yes | Column from the parent DataFrame to iterate over. |
| `filter` | string | no | A pandas `.query()` expression applied to the parent DataFrame before iteration. |
| `inject_param` | string | no | Adds `{inject_param: value}` to query params for each iteration, where `value` is `inject_template` rendered against the parent row. |
| `inject_template` | string | default `"{field}"` | Python `.format()` template for the injected param value, using `{column_name}` placeholders from the parent row. |
| `inject_fields` | list of strings | no | Columns from the parent row to carry forward and append to every row in each response chunk. |

The cache key for foreach requests is `{name}_{param_k}_{param_v}_...` (sorted by key), with `:`, ` `, `*` replaced by `_`, `_`, `all`.

If an HTTP request in a foreach loop fails (any exception), that iteration is skipped and the loop continues.

### Field Mapping (`fields`)

Each entry is either a **source field** or a **computed field**. Evaluation is two-pass: all source fields are resolved first, then computed fields can reference the aliased output column names from pass 1.

**Source field:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `source` | string | yes | Column name in the raw response. Missing columns are skipped with a warning. |
| `alias` | string | no | Output column name. Defaults to `source`. |
| `cast` | string | no | `int`, `float`, or `str`. See casting rules below. |

**Computed field:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `computed` | string | yes | Python `.format()` template. Uses `{alias}` names from pass 1. Applied row-by-row. |
| `alias` | string | yes | Output column name. |

**Casting rules:**

- `float` and `int`: `pd.to_numeric(col, errors="coerce")` — non-numeric values (including FRED's `"."` missing value sentinel) become `NaN`.
- `int`: additionally applies `.round().astype("Int64")` (pandas nullable integer type).
- `str`: `.astype(str)`.

The output DataFrame contains only the aliased columns produced by the `fields` spec.

---

## Ontology Schema (`configs/ontology/*.yaml`)

Defines the OWL ontology: its IRI, classes, object properties, and data properties.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `uri` | string | yes | OWL ontology IRI, passed to `world.get_ontology()`. |
| `classes` | list | no | OWL classes to create. |
| `object_properties` | list | no | OWL object properties to create. |
| `data_properties` | list | no | OWL data properties to create. |

### `classes`

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Class name. |
| `parent` | string | no | Parent class name as it appears in `class_map`. Defaults to `Thing`. |

### `object_properties`

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Property name. |
| `domain` | list of class names | no | OWL domain restriction. |
| `range` | list of class names | no | OWL range restriction. |
| `inverse` | string | no | If set, a second property with this name is created with `inverse_property` pointing to the first. |

Object properties are created in two passes: first all properties (without inverses), then all inverse properties. This ensures that the forward property exists before its inverse is created.

### `data_properties`

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Property name. |
| `domain` | list of class names | yes | OWL domain. Each name is looked up in `class_map`; unknown names fall back to `Thing`. |
| `range` | string | yes | `str`, `int`, `float`, or `bool`. Mapped to Python types `str`, `int`, `float`, `bool`. |
| `functional` | boolean | no | If `true`, the property inherits from both `DataProperty` and `FunctionalProperty`. |

### Current Schema (`configs/ontology/core.yaml`)

**URI:** `http://example.org/rutgers_ontology.owl`

**Classes:**

| Name | Parent |
|------|--------|
| `State` | Thing |
| `County` | Thing |
| `Municipality` | Thing |
| `Individual` | Thing |
| `Measure` | Thing |

**Object properties:**

| Name | Domain | Range | Inverse |
|------|--------|-------|---------|
| `isPartOf` | County, Municipality | State, County | `hasPart` |
| `locatedIn` | Individual, Municipality, County | Municipality, County, State | — |
| `measuredFor` | Measure | State, County, Municipality | — |

**Data properties:**

| Name | Domain | Range | Functional |
|------|--------|-------|------------|
| `hasName` | Thing | str | yes |
| `hasPopulation` | State, County, Municipality | int | yes |
| `hasFIPS` | State, County, Municipality | str | yes |
| `hasIncome` | Individual | float | yes |
| `hasValue` | Measure | float | yes |
| `hasDate` | Measure | str | yes |
| `hasSeries` | Measure | str | yes |
| `hasUnit` | Measure | str | yes |

---

## Pipeline Config (`configs/pipelines/*.yaml`)

Orchestrates a full hydration run: which ontology to use, which steps to execute in order, and where to write output.

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ontology` | string | yes | Path to an ontology YAML (`.yaml`/`.yml`) or `.owl` file. |
| `output_owl` | string | default `"ontology/populated_ontology.owl"` | Path for the RDF/XML output. |
| `db` | string | default `"ontology/onto.db"` | Path for the SQLite quadstore. |
| `steps` | list | yes | Ordered list of hydration steps. |
| `post_hydration_transforms` | list | no | Ontology transforms run after all steps complete. |

### Step Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Display name for log output. |
| `api` | string | yes | Name of the API config to fetch. Must match a file in `configs/apis/`. |
| `class` | string | yes | OWL class name for created individuals. Must exist in the ontology schema. |
| `uri` | string | yes | URI local-name template. `{column_name}` placeholders are replaced with sanitized row values (non-`[A-Za-z0-9_\-.]` characters replaced with `_`). |
| `properties` | map | no | `{property_name: template}`. Templates use `{column_name}` placeholders; values are **not** URI-sanitized. |
| `transform` | string | no | `"module_name::function_name"` notation for a DataFrame transform to apply before ontology mapping. |
| `transform_config` | map | no | Keyword arguments passed to the transform function. |
| `relationships` | list | no | Object property links to create from each individual. |

### Relationship Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `property` | string | yes | Object property name. Must exist in the ontology schema. |
| `target_class` | string | yes | OWL class of the target individual. |
| `target_uri` | string | yes | URI template for the target individual (sanitized). |
| `create_if_missing` | boolean | default `false` | If `true`, create the target individual when it does not already exist. If `false` and the target is not found, the relationship is silently skipped. |
| `create_with_properties` | map | no | `{property_name: template}` properties to set on a newly created target (only applied when `create_if_missing: true` and the target was created by this step). |

### `post_hydration_transforms`

Each entry is either:
- A string `"module_name::function_name"` (config defaults to `{}`).
- A map `{spec: "module_name::function_name", config: {key: value, ...}}`.

### Ordering Constraint

Steps are executed sequentially. Each step's API result is stored in `resolved[api_name]` after fetch and transform. A `foreach` source in any API config must resolve to a key that was stored by an earlier step; otherwise an error is raised.

### Current Pipeline (`configs/pipelines/nj_hydration.yaml`)

| Step | API | Class | URI Template | Transform |
|------|-----|-------|--------------|-----------|
| `load_states` | `census_states` | State | `State_{fips}` | `census_clean::add_state_abbreviations` |
| `load_counties` | `census_counties` | County | `County_{full_fips}` | `census_clean::strip_state_suffix` |
| `load_municipalities` | `census_municipalities` | Municipality | `Municipality_{full_fips}` | `census_clean::strip_municipality_name` |
| `load_individuals` | `sample_individuals` | Individual | `{id}` | — |
| `link_municipalities_to_counties` | `municipality_map` | Municipality | `Municipality_{municipality}` | — |
| `load_unemployment` | `fred_unemployment` | Measure | `Measure_{abbr}URN_{date}` | — |
| `load_housing` | `fred_housing` | Measure | `Measure_{abbr}STHPI_{date}` | — |
| `load_income` | `fred_income` | Measure | `Measure_MEHOINUS{abbr}A646N_{date}` | — |
