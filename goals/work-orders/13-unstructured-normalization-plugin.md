# Work Order 13 — Unstructured Data Normalization Transform Plugin

## Layer
2 — Ingestion Expansion

## Goal
Add a built-in transform plugin that uses an LLM to normalize messy free-text columns into structured fields, so researchers can ingest data that doesn't already have clean categorical values.

## Background
Real-world datasets often have columns like `"Northeast region, Q3 2022"`, `"New Jersey (est.)"`, or `"$1.2M annually"`. The engine needs to map these to clean values before hydrating the ontology. This plugin handles that automatically.

## Steps

### 1. Create the transform plugin
File: `packages/engine/transforms/llm_normalize.py`

This is a DataFrame transform plugin (see `specs/plugins.md`).

```python
NAME = "llm_normalize"
DESCRIPTION = "Uses an LLM to normalize messy columns into structured fields."

def run(df: pd.DataFrame, config: dict, onto=None) -> pd.DataFrame:
    """
    config fields:
      columns: list of column names to normalize
      schema:  dict mapping column → target format description
               e.g. {"region": "US Census region code (string)", "quarter": "integer 1-4"}
      model:   optional model string override
      batch_size: rows per LLM call (default 20)
    """
```

The plugin batches rows, sends them to the LLM with a prompt describing the target schema, and parses the response. It replaces the original column values with the normalized ones.

### 2. LLM call mechanism
The transform plugin cannot import FastAPI services directly (engine is standalone). Instead, it reads the model from env var `RAIL_LLM_MODEL` and the API key from `ANTHROPIC_API_KEY` (or others). It calls `litellm.completion()` directly (litellm has no server dependency).

Add `litellm` to `packages/engine/pyproject.toml`.

### 3. Prompt design
```
You are normalizing data columns for a research database.
Target schema: {schema}

Normalize the following rows. Return ONLY a JSON array with the same number of objects,
each containing only the normalized column values:
{rows_as_json}
```

Include examples in the prompt for few-shot accuracy.

### 4. Error handling
- If LLM call fails: keep original values and log a warning
- If LLM returns malformed JSON: retry once, then fall back to original
- Column values that already match the target format: pass through unchanged

### 5. Pipeline YAML usage
```yaml
steps:
  - name: normalize_regions
    api: raw_regional_data
    class: Region
    uri: "Region_{code}"
    transform: llm_normalize
    transform_config:
      columns: [region_text, time_period]
      schema:
        region_text: "US Census region name (Northeast/Midwest/South/West)"
        time_period: "ISO 8601 year-quarter string (e.g. 2022-Q3)"
```

### 6. Add `RAIL_LLM_MODEL` env var to hydration worker
File: `packages/api/app/services/hydration_worker.py`

Pass `RAIL_LLM_MODEL` and all API key env vars to the subprocess env so the transform plugin can use them.

### 7. Frontend: no changes needed
This is a pure engine/API change. The transform plugin auto-discovers via `transform_runner.py`.

## New Dependencies
- `litellm` — add to `packages/engine/pyproject.toml` (already in API package)

## Affected Files
- `packages/engine/transforms/llm_normalize.py` — **create**
- `packages/engine/pyproject.toml` — add litellm
- `packages/api/app/services/hydration_worker.py` — pass LLM env vars to subprocess
- `specs/plugins.md` — document new built-in transform after implementation

## Acceptance Criteria
- [ ] A DataFrame with messy region strings is correctly normalized by the plugin
- [ ] Batch processing: 100 rows processed in ≤3 LLM calls
- [ ] LLM failure falls back gracefully without crashing the pipeline
- [ ] Transform is usable from pipeline YAML with no Python code
- [ ] Result integrates cleanly with downstream ontology mapping step
