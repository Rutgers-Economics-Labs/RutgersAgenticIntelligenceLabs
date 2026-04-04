# WO-5.1 — Incremental Hydration Mode

**Status:** ready  
**Spec:** `specs/schedule.md`, `specs/engine.md`  
**Depends on:** nothing  
**Blocks:** WO-5.2  

---

## Goal

Add `hydration_mode: incremental` support to the pipeline YAML and engine. When set, the worker does not delete `onto.db` before running, allowing append-only time series to accumulate across multiple runs.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/api/app/services/yaml_service.py` | **Modify** | Allow `hydration_mode` field in pipeline configs |
| `packages/api/app/services/hydration_worker.py` | **Modify** | Skip onto.db deletion when `hydration_mode: incremental` |
| `packages/engine/pipeline_runner.py` | **Modify** | Skip onto.db deletion when mode flag is set |

---

## Steps

### 1. Update `yaml_service.validate()` for `"pipeline"` type

Add `hydration_mode` to the allowed top-level fields:

```python
PIPELINE_ALLOWED_MODES = {"full", "incremental"}

# In validate(), pipeline section:
mode = parsed.get("hydration_mode", "full")
if mode not in PIPELINE_ALLOWED_MODES:
    errors.append(f"hydration_mode must be 'full' or 'incremental', got '{mode}'")
```

Also allow the `schedule` field (object) at the top level — it will be validated more thoroughly in WO-5.2.

### 2. Update `hydration_worker.py`

Pass `hydration_mode` through to the subprocess via environment variable:

```python
# Parse pipeline YAML to read hydration_mode
pipeline_parsed = yaml.safe_load(pipeline_content)
hydration_mode = pipeline_parsed.get("hydration_mode", "full")

# Add to env vars passed to the subprocess
env["RAIL_HYDRATION_MODE"] = hydration_mode
```

When `hydration_mode == "incremental"`, do NOT delete existing onto.db before the run:

```python
# Existing code deletes the tmpdir and creates fresh
# Change: if incremental, copy existing onto.db into tmpdir first
if hydration_mode == "incremental":
    existing_db = project.get("activeOntologyDbPath") if project_id else None
    if existing_db and Path(existing_db).exists():
        import shutil
        shutil.copy2(existing_db, tmpdir / "ontology/onto.db")
        await _log(job_id, "[info] Incremental mode: using existing onto.db as base")
    else:
        await _log(job_id, "[info] Incremental mode: no existing onto.db, starting fresh")
```

### 3. Update `packages/engine/pipeline_runner.py`

Read `RAIL_HYDRATION_MODE` env var. If `"incremental"`, skip the step that deletes/creates a fresh SQLite quadstore:

```python
hydration_mode = os.environ.get("RAIL_HYDRATION_MODE", "full")

# Existing code (around line where quadstore is initialized):
# if not incremental, delete existing onto.db
if hydration_mode != "incremental":
    if onto_db_path.exists():
        onto_db_path.unlink()

# Then load/create the world as normal
world = World(filename=str(onto_db_path))
```

The owlready2 `_get_or_create` pattern means that re-running the pipeline with incremental mode:
- Creates new individuals for new URIs (e.g., new dates in time series)
- Updates data properties on existing individuals for existing URIs (upsert behavior)

---

## Acceptance

- [ ] A pipeline YAML with `hydration_mode: incremental` validates without errors
- [ ] Running a hydration twice in incremental mode: second run does not lose individuals from the first run
- [ ] Append-only time series (date-keyed URIs) accumulates across runs — individual count grows
- [ ] `hydration_mode: full` (default) continues to work as before — fresh rebuild each run
- [ ] `make hydrate` against the NJ pipeline (without `hydration_mode` field) still works
