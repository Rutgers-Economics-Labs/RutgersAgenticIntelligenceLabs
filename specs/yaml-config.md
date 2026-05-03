# YAML Configuration Schemas

There are three kinds of YAML configuration files: API source configs, the ontology schema, and pipeline configs.

> **Note:** All paths in this document are relative to the `packages/engine/` directory.

---

## Common Fields

All configuration types (API, Ontology, Pipeline) support a top-level **`meta`** block. This block is ignored by the engine and validation logic, providing a "safe sandbox" for agents and researchers to store notes, status flags, and descriptions.

```yaml
meta:
  readiness: "needs_review"
  source_notes: "This URL might change quarterly"
  agent_intent: "Linking population to municipality"
```

---

## API Source Config (`configs/apis/*.yaml`)

Defines one data source. The filename stem is the API name used to reference the source in pipeline steps and `foreach` clauses.

### Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Must match the filename stem. Used as the key in `resolved_data` and as the base for cache filenames. |
| `type` | string | yes | `api` (or `http_json`), `csv`, `excel`, `uploaded`, `scrape`, `pdf`, `docx`, `parquet`, `sql_mirror` |
| `extends` | string | no | Slug of a shared connector template in the Convex `connectorTemplates` table. When present, the template is fetched and deep-merged with this config before hydration. This config's fields override the template's. See `specs/connectors.md`. |
| `fields` | list | no | Column mapping rules (see below). If absent, the raw columns are passed through unchanged. |
| `fields_append` | list | no | Additional field entries to append to the template's `fields` list after merging. Only meaningful when `extends` is set. If `fields` is also present, it replaces the template's list entirely; `fields_append` then appends to the replacement. |
| `schema_contract` | list | no | (Optional) Explicit list of allowed column names and types. If provided, coding agents are prohibited from referencing columns not present in this list to prevent hallucinations. |

### `type: api`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | HTTP endpoint. `${VAR_NAME}` tokens are replaced with environment variables. |
| `params` | map | no | Query parameters appended to the request. `${VAR_NAME}` tokens are resolved from environment variables. |
| `response_format` | string | yes | `json` or `census_array` |
| `response_path` | string | no | If set, traverses the raw response using dot-notation (e.g., `features.attributes`) before parsing. |
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

### `type: parquet`

Reads a Parquet file. Handled by the `handlers/parquet.py` plugin.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | one of | Local path to a `.parquet` file. |
| `url` | string | one of | Remote URL — downloaded and cached by SHA1 hash. |
| `storage_key` | string | one of | S3 key (`s3://bucket/key`) or local artifact path written by `storage_service`. |

### `type: sql_mirror`

Connects to an external database via SQLAlchemy and fetches a query result. Handled by the `handlers/sql_mirror.py` plugin.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `connection_string` | string | yes | SQLAlchemy URL (e.g. `postgresql://user:pass@host/db`). Use `${ENV_VAR}` for secrets. |
| `query` | string | one of | Raw SQL query string. |
| `table` | string | one of | Table name — equivalent to `SELECT * FROM {table}`. |

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

**Design principle:** Abstract parent classes (`GeographicRegion`, `Observation`) act as the extensibility hooks. To add a new entity type (e.g. `Nation`, `ZipCode`, `Firm`) add a single entry to `classes` with the appropriate `parent`. No code changes in the engine or API are required.

**Classes:**

| Name | Parent | Purpose |
|------|--------|---------|
| `GeographicRegion` | Thing | Abstract root for all geographic entities |
| `Nation` | GeographicRegion | Country-level geography |
| `Region` | GeographicRegion | Multi-state / multi-country grouping |
| `State` | GeographicRegion | US state |
| `County` | GeographicRegion | US county |
| `Municipality` | GeographicRegion | City / town |
| `ZipCode` | GeographicRegion | USPS ZIP code area |
| `CensusTract` | GeographicRegion | Sub-county Census tract |
| `Individual` | Thing | Agent / person record |
| `Observation` | Thing | Abstract root for all measured series values |
| `Measure` | Observation | Generic/untyped observation (backward-compat) |
| `LaborIndicator` | Observation | Unemployment, labor force participation |
| `HousingIndicator` | Observation | HPI, vacancy, permits |
| `IncomeIndicator` | Observation | Median income, poverty rate |
| `MacroIndicator` | Observation | GDP, CPI, rates |
| `EnvironmentIndicator` | Observation | Air quality, emissions |
| `DemographicIndicator` | Observation | Population, age distribution |
| `EducationIndicator` | Observation | Graduation rates, enrollment |
| `DataSeries` | Thing | One instance per series; holds metadata |

**Object properties:**

| Name | Domain | Range | Inverse |
|------|--------|-------|---------|
| `isPartOf` | GeographicRegion | GeographicRegion | `hasPart` |
| `locatedIn` | Individual, GeographicRegion | GeographicRegion | — |
| `measuredFor` | Observation | GeographicRegion | — |
| `belongsToSeries` | Observation | DataSeries | — |

**Data properties:**

| Name | Domain | Range | Functional | Notes |
|------|--------|-------|------------|-------|
| `hasName` | Thing | str | yes | Universal label |
| `hasFIPS` | GeographicRegion | str | yes | |
| `hasAbbreviation` | GeographicRegion | str | yes | State abbr etc. |
| `hasISO2` / `hasISO3` | GeographicRegion | str | yes | Country codes |
| `hasRegionCode` | GeographicRegion | str | yes | |
| `hasPopulation` | GeographicRegion | int | yes | |
| `hasIncome` | Individual | float | yes | |
| `hasValue` | Observation | float | yes | |
| `hasDate` | Observation | str | yes | ISO date string |
| `hasSeries` | Observation | str | yes | Series identifier |
| `hasUnit` | Observation | str | yes | |
| `hasYear` | Observation | int | yes | For DuckDB range queries |
| `hasMonth` | Observation | int | yes | 1–12, nullable |
| `hasQuarter` | Observation | int | yes | 1–4, nullable |
| `hasSeriesID` | DataSeries | str | yes | |
| `hasSeriesTitle` | DataSeries | str | yes | |
| `hasFrequency` | DataSeries | str | yes | `monthly`, `quarterly`, `annual` |
| `hasSeasonalAdj` | DataSeries | str | yes | `SA`, `NSA` |
| `hasSource` | DataSeries | str | yes | `FRED`, `Census`, etc. |
| `hasSourceURL` | Thing | str | yes | Provenance URL |
| `hasIngestDate` | Thing | str | yes | ISO date of hydration |
| `hasPipelineID` | Thing | str | yes | Pipeline run identifier |


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
| `hydration_mode` | string | default `"full"` | `full` or `incremental`. In `full` mode (default), `onto.db` is deleted and rebuilt from scratch on every run. In `incremental` mode, existing individuals are preserved and new ones are appended; existing URIs are updated in-place. Use `incremental` for scheduled/live data collection. See `specs/schedule.md`. |
| `schedule` | map | no | Cron-based scheduling for automated hydration runs. See `specs/schedule.md` and the schedule fields table below. |

### Schedule Fields (inside `schedule:`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cron` | string | no | Standard 5-field cron expression (e.g. `"0 8 * * *"` = daily at 8am). Mutually exclusive with `frequency`. |
| `frequency` | string | no | Human-readable interval shorthand: `15m`, `1h`, `6h`, `1d`, `1w`. Mutually exclusive with `cron`. |
| `window` | string | no | Auto-stop duration after which the schedule is disabled. Format: `Nd`, `Nw`, `Nh` (e.g. `7d` = stop after 7 days). If absent, the schedule runs indefinitely. |
| `enabled` | boolean | default `true` | Set to `false` to pause the schedule without removing it. |

**Example — daily scheduled pipeline:**
```yaml
hydration_mode: incremental
schedule:
  cron: "0 8 * * *"          # every day at 8am
  window: 30d                 # stop after 30 days
```

**Example — high-frequency collection window:**
```yaml
hydration_mode: incremental
schedule:
  frequency: 1h               # every hour
  window: 7d                  # for one week
```

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
