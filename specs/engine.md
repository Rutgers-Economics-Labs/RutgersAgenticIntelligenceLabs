# Engine

The engine is five Python modules in `engine/`. None contain domain knowledge — all mappings come from YAML.

---

## `engine/api_runner.py`

Loads API/CSV/Excel configs and returns DataFrames. Entry point: `fetch_api`.

### `fetch_api(api_name, resolved_data=None) -> pd.DataFrame`

1. Loads `configs/apis/{api_name}.yaml`.
2. Recursively replaces all `${VAR_NAME}` tokens in string values with `os.environ.get(VAR_NAME)`. Unresolved tokens are left as-is.
3. Dispatches by `type`:

**`type: csv`** — reads `spec["path"]` with `pd.read_csv()`. Applies `fields` mapping if present.

**`type: excel`** — reads `spec["path"]` with `pd.read_excel()`. Applies `fields` mapping if present.

**`type: api` without `foreach`** — makes one HTTP GET to `url` with `params`, caches the response, parses it, applies `fields` mapping, applies `drop_na` if set.

**`type: api` with `foreach`** — iterates over `resolved_data[foreach.source]` (after applying `filter` if set), makes one HTTP GET per row, injects `{inject_param: inject_template.format(**row)}` into params, carries `inject_fields` columns from the parent row into each response chunk, concatenates all chunks into one DataFrame, applies `fields` mapping, applies `drop_na` if set.

If any HTTP request in a foreach loop raises an exception, that iteration is skipped with a `[skip]` log message; the loop continues.

### HTTP caching

Responses are cached to `cache/{cache_key}.json`.

- Single request: cache key is `spec["name"]`.
- Foreach request: cache key is `{name}_{k1}_{v1}_{k2}_{v2}_...` where pairs are sorted by key.
- In both cases: `:` → `_`, ` ` → `_`, `*` → `all`.

A cached response is returned if the file exists and `cache` is not `false` in the spec.

### Response parsing (`_to_dataframe`)

- If `response_path` is set, extracts `raw[response_path]` before parsing.
- `census_array`: `raw[0]` is the header row; `raw[1:]` are data rows → `pd.DataFrame(raw[1:], columns=raw[0])`.
- `json`: if `raw` is a list → `pd.DataFrame(raw)`; otherwise → `pd.DataFrame([raw])`.

### Field mapping (`_apply_fields`)

Two-pass evaluation. Returns a new DataFrame with only the aliased columns.

**Pass 1 — source fields** (entries without `computed`):
- Extracts `df[source]`, renames to `alias`.
- `cast: float` or `cast: int`: `pd.to_numeric(col, errors="coerce")`. FRED's `"."` missing value sentinel becomes `NaN`.
- `cast: int`: additionally `.round().astype("Int64")`.
- `cast: str`: `.astype(str)`.
- Missing source columns are skipped with a warning printed to stdout.

**Pass 2 — computed fields** (entries with `computed`):
- Evaluates `field["computed"].format(**row.to_dict())` for each row using the pass-1 result.
- Can reference any alias produced in pass 1.

---

## `engine/ontology_builder.py`

Builds or loads an owlready2 ontology. Entry point: `load_ontology`.

### `build_from_yaml(yaml_path, world) -> (onto, class_map)`

Parses the ontology YAML and creates owlready2 classes and properties inside `world`.

Returns `(onto, class_map)` where `class_map` starts as `{"Thing": Thing}` and is populated with every created class and property.

1. `onto = world.get_ontology(spec["uri"])`.
2. **Classes:** `type(name, (parent,), {})` where `parent` defaults to `Thing`.
3. **Object properties (pass 1):** `type(name, (ObjectProperty,), {"domain": [...], "range": [...]})`. Collects `(prop_name, inverse_name)` pairs for properties with `inverse`.
4. **Object properties (pass 2):** for each collected inverse pair, `type(inv_name, (ObjectProperty,), {"inverse_property": class_map[prop_name]})`.
5. **Data properties:** `range` string mapped to Python type via `{"str": str, "int": int, "float": float, "bool": bool}`. If `functional: true`, bases are `(DataProperty, FunctionalProperty)`; otherwise `(DataProperty,)`.

### `load_from_owl(owl_path, world) -> (onto, class_map)`

`onto = world.get_ontology(f"file://{Path(owl_path).resolve()}").load()`.

Populates `class_map` from `onto.classes()` and `onto.properties()`. Returns `(onto, class_map)`.

### `load_ontology(ontology_config, world) -> (onto, class_map)`

Dispatches:
- `.yaml` or `.yml` suffix → `build_from_yaml`.
- `.owl` suffix → `load_from_owl`.
- Other suffix → raises `ValueError`.

---

## `engine/pipeline_runner.py`

Orchestrates a full hydration run. Entry point: `run_pipeline`.

### `run_pipeline(pipeline_path)`

1. Reads pipeline YAML.
2. Deletes `db_path` and `db_path + "-journal"` if they exist (ensures clean rebuild).
3. `world = World(); world.set_backend(filename=db_path)`.
4. `onto, class_map = load_ontology(pipeline["ontology"], world=world)`.
5. `resolved = {}` — stores `{api_name: DataFrame}` for foreach lookups.
6. `_cache = {}` — stores `{uri_string: individual}` to avoid repeat `onto.search_one()` calls.
7. For each step in `pipeline["steps"]`:
   - Fetch the API: `df = fetch_api(api_name, resolved_data=resolved)`.
   - Apply optional DataFrame transform: `df = run_dataframe_transform(spec, df, config)`.
   - Store: `resolved[api_name] = df`.
   - Look up the OWL class; raise `ValueError` if not found.
   - For each row in `df` (inside `with onto:`):
     - Build `row_dict` excluding keys starting with `_`.
     - Resolve URI: `_resolve(uri_template, row_dict, sanitize=True)`.
     - `individual, created = _get_or_create(onto, onto_class, uri, _cache)`.
     - Set each data property: `_set_data_property(individual, prop_name, prop, resolved_value)`.
     - For each relationship: resolve `target_uri`, get or create the target, set the object property.
8. Run `post_hydration_transforms` (if any) inside `with onto:`.
9. `onto.save(file=output_owl, format="rdfxml")`.
10. `world.save()`.

### `_sanitize(value) -> str`

Replaces all characters not in `[A-Za-z0-9_\-.]` with `_`. Used for URI local names.

### `_resolve(template, row, sanitize=False) -> str`

Replaces `{key}` placeholders in `template` with values from `row`. When `sanitize=True`, string values are passed through `_sanitize` before substitution.

### `_get_or_create(onto, onto_class, uri, cache) -> (individual, was_created)`

1. Returns `(cache[uri], False)` if `uri` is in `cache`.
2. `onto.search_one(iri=f"*#{uri}")` — if found, adds to cache and returns `(existing, False)`.
3. Otherwise creates `onto_class(uri)`, adds to cache, returns `(individual, True)`.

### `_set_data_property(individual, prop_name, prop, raw_value)`

Casts `raw_value` to `prop.range[0]` if available:
- `int`: `int(float(str(raw_value)))`.
- `float`: `float(raw_value)`.
- Other: `str(raw_value)`.

Falls back to `str(raw_value)` on `ValueError` or `TypeError`.

- Functional property: `setattr(individual, prop_name, value)`.
- Non-functional property: appends `value` to the existing list if not already present.

### `_set_object_property(individual, prop_name, prop, target)`

- Functional property: `setattr(individual, prop_name, target)`.
- Non-functional property: appends `target` to the existing list if not already present.

### Relationship resolution

When `create_if_missing: false`: target is looked up in `_cache` first, then via `onto.search_one()`. If the target is not found, the relationship is silently skipped.

When `create_if_missing: true`: `_get_or_create` is called. If the target was just created and `create_with_properties` is set, those properties are set on the new target using `_set_data_property`.

---

## `engine/transform_runner.py`

Loads and runs transform functions. Entry point: `run_dataframe_transform` and `run_ontology_transform`.

### `_load_fn(spec_str) -> callable`

Parses `"module_name::function_name"` notation. If no `::` separator, module name is the full string and function name defaults to `"transform"`.

Searches `transforms/{module_name}.py` first. If found, loads via `importlib.util.spec_from_file_location`. Otherwise falls back to `importlib.import_module(module_name)`.

Raises `AttributeError` if the function name is not found in the loaded module.

### `run_dataframe_transform(spec_str, df, config=None) -> pd.DataFrame`

Calls `fn(df, **(config or {}))`. Raises `ValueError` if the function returns `None`.

### `run_ontology_transform(spec_str, onto, config=None)`

Calls `fn(onto, **(config or {}))`. Modifies the ontology in-place; return value is ignored.

---

## `engine/analysis_runner.py`

Discovers and runs analysis plugins. Entry point: `discover` and `run`.

### `discover() -> dict`

Scans `analysis/*.py`. For each file not starting with `_`:
- Loads the module via `importlib.util.spec_from_file_location`.
- Adds `{stem: module}` to the result dict if the module has an `analyze` attribute.
- Modules that fail to load are skipped with a warning printed to stdout.

Returns `{module_stem: module}`, sorted by filename.

### `run(module_name, onto, config=None) -> dict`

Calls `discover()`, then `modules[module_name].analyze(onto, **(config or {}))`. Raises `ValueError` if `module_name` is not in the discovered modules.
