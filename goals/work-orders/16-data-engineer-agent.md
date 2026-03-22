# Work Order 16 — AI Data Engineer Agent

## Layer
3 — AI Agent Specialization

## Goal
Create a specialized Data Engineer agent with a system prompt, tool set, and workflow focused exclusively on data acquisition, pipeline construction, and data quality. Distinct from the generalist agent.

## Background
The current generalist agent handles both data engineering and analysis. As research complexity grows, mixing these concerns produces lower quality outputs. A specialized Data Engineer agent follows best practices for data acquisition: validating sources, checking coverage, detecting schema drift, and producing clean, documented pipelines.

## Steps

### 1. Create `data_engineer_agent.py`
File: `packages/api/app/services/data_engineer_agent.py`

Separate module with its own system prompt and tool set.

**System prompt focus:**
- Data source discovery and validation
- YAML config generation for APIs, CSVs, PDFs, scraped pages
- Pipeline construction (wiring sources → ontology)
- Data quality checks (missing values, outliers, coverage gaps, unit consistency)
- Schema drift detection
- Incremental ingestion setup

**Tools (subset of main agent + new data-specific tools):**
- All existing tools from `agent_service.py`
- `validate_data_source(url_or_path)` — fetches the source and reports: row count, columns, null rates, value ranges, date coverage
- `check_schema_drift(slug)` — fetches current source and compares to the last-fetched schema stored in Convex; reports added/removed/changed columns
- `run_data_quality_check(table_name)` — runs a standard DuckDB quality report: null counts, distinct values, min/max/mean per column, returns structured result
- `search_data_registry(query, ...)` — from WO-14

### 2. New API endpoint
File: `packages/api/app/routers/agent.py`

```
POST /api/v1/agent/data-engineer/chat
```

Same SSE streaming interface as `/agent/chat`. Uses `data_engineer_agent.run_chat()` instead.

### 3. `validate_data_source` tool implementation
```python
async def _validate_source(url_or_path: str) -> dict:
    """Fetch source, return quality report: {columns, rowCount, nullRates, dateRange, sample}"""
```

For HTTP sources: fetch 1 page/first 100 rows. For files: read via pandas. Returns a summary the agent uses to decide if the source is usable.

### 4. `check_schema_drift` tool implementation
Stored schema snapshots in Convex: new table `sourceSchemas`
| Field | Type |
|-------|------|
| `slug` | string (indexed) |
| `columns` | `{name, dtype, nullRate}[]` |
| `snapshotAt` | number |

After each successful hydration, update the snapshot. `check_schema_drift` compares current fetch to the snapshot and returns a diff.

### 5. `run_data_quality_check` tool implementation
Runs this DuckDB query pattern:
```sql
SELECT
  COUNT(*) as total_rows,
  COUNT(col) as non_null_col,
  MIN(col) as min_col,
  MAX(col) as max_col,
  AVG(col) as avg_col
FROM "TableName"
```
Returns structured quality report as a dict.

### 6. Workspace UI: agent role selector
File: `packages/web/app/(dashboard)/workspace/page.tsx`

Add a role selector in the workspace header: **General** | **Data Engineer** | **Analyst** (Analyst comes in WO-17).

When "Data Engineer" is selected, requests go to `/agent/data-engineer/chat` instead of `/agent/chat`.

Show role-appropriate example prompts:
- "Validate the FRED unemployment source for NJ"
- "Check if any source schemas have changed since last run"
- "Find and add a housing price data source for NJ counties"
- "Run a data quality report on the County table"

## New Convex Schema
- `sourceSchemas` table (see step 4 above)
- New `convex/sourceSchemas.ts`: `get(slug)`, `upsert(slug, columns)`

## Affected Files
- `packages/api/app/services/data_engineer_agent.py` — **create**
- `packages/api/app/routers/agent.py` — add `/data-engineer/chat` endpoint
- `packages/web/convex/schema.ts` — add `sourceSchemas` table
- `packages/web/convex/sourceSchemas.ts` — **create**
- `packages/api/app/services/hydration_worker.py` — snapshot schema after hydration
- `packages/web/app/(dashboard)/workspace/page.tsx` — add role selector
- `packages/web/lib/api.ts` — add `agent.dataEngineerChat()`

## Acceptance Criteria
- [ ] Data Engineer agent answers "validate this source" with null rates, row counts, date range
- [ ] Schema drift detection reports added/removed columns between runs
- [ ] Data quality check returns a structured report for any DuckDB table
- [ ] Workspace role selector correctly routes to the specialized agent
- [ ] Data Engineer agent refuses to run statistical analysis (out of scope for this role)
