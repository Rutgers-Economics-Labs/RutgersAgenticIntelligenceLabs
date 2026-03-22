# Work Order 03 — Environment Setup & End-to-End Agent Test

## Goal
Verify the full chain works: `.env` configured → hydration pipeline runs → DuckDB populated → AI Workspace agent answers a real research question using SQL and Python.

## Prerequisites
- Work orders 01–02 complete
- At least one pipeline config seeded in Convex (e.g. `nj_hydration`)
- One LLM provider API key available

## Steps

### 1. Add AI keys to `.env`
Add at minimum one of the following to `.env` at the repo root:
```
AI_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
```
Other supported vars (optional): `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`.

### 2. Verify API startup
```bash
make dev-api
```
Expected startup logs:
- `[startup] Loaded ontology from .../onto.db` (if a prior hydration exists)
- `[startup] Loaded DuckDB from .../onto.duckdb` (if DuckDB export exists)
- No import errors

### 3. Run a hydration pipeline
From the `/pipelines` page, click "Run" on any available pipeline. Monitor `/jobs` until status = `success`. Confirm the job log includes the line:
```
[job] DuckDB export ready: .../onto.duckdb
```

### 4. Verify SQL endpoint
```bash
curl -X POST http://localhost:8000/api/v1/sql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM \"State\" LIMIT 5"}'
```
Expected: `{columns: [...], rows: [...], rowCount: 5}`

### 5. Verify agent models endpoint
```bash
curl http://localhost:8000/api/v1/agent/models
```
Expected: list of model objects, `default` matches `AI_MODEL` env var.

### 6. Test AI Workspace end-to-end
Navigate to `/workspace`. Select the configured model. Ask:
> "What states are in the ontology? Show me the top 5 by population."

Expected agent behavior:
1. Calls `get_sql_schema` or `query_ontology`
2. Calls `run_sql` with a query against the `State` table
3. Returns a text answer with a data table in the tool result

### 7. Test Python execution via agent
Ask:
> "Calculate the mean population across all states using Python."

Expected: agent calls `execute_python`, returns `stdout` with the computed value.

## Acceptance Criteria
- [ ] API starts without errors with AI keys set
- [ ] Hydration job completes with DuckDB export log line
- [ ] `POST /sql` returns data
- [ ] `/workspace` streams a complete agent response with at least one tool call
- [ ] Agent correctly uses `run_sql` or `execute_python` and returns a real answer

## Files Touched
- `.env` (local only, not committed)
- No code changes expected — this is a validation work order
