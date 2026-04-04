# Q&A Interface

The **Q&A interface** provides single-shot natural-language question answering against a project's knowledge graph. It is designed for researchers who want quick, precise answers — not for multi-session research workflows.

---

## Purpose

When a researcher asks "What was the unemployment rate in Hudson County in 2022?" the Q&A interface:

1. Inspects the project's DuckDB schema
2. Decides if the data exists to answer the question
3. If yes: runs SQL or Python and returns a structured answer with supporting data
4. If no: calls `report_scope_exceeded` to explain what's missing and what data sources could fill the gap

This is distinct from the research agent (`/agent`): Q&A is single-turn (one question → one answer), while the research agent handles multi-turn workflows with persistent sessions.

---

## API Route — `/api/v1/questions`

Router: `packages/api/app/routers/questions.py`

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/ask` | `{question, project_id?, model?}` | SSE stream |

### Request

```json
{
  "question": "What was the unemployment rate in Hudson County in 2022?",
  "project_id": "nj-economics",
  "model": null
}
```

`project_id` is optional but recommended — it scopes SQL queries to the project's `activeOntologyDuckdbPath`.

### Response (SSE stream)

```
data: {"type": "text_delta", "text": "Hudson County's unemployment rate in 2022 was..."}
data: {"type": "tool_call", "id": "call_1", "name": "get_schema", "args": {}}
data: {"type": "tool_result", "id": "call_1", "name": "get_schema", "result": {...}}
data: {"type": "tool_call", "id": "call_2", "name": "run_sql", "args": {"query": "SELECT..."}}
data: {"type": "tool_result", "id": "call_2", "name": "run_sql", "result": {...}}
data: {"type": "text_delta", "text": "...5.8%, down from 7.2% in 2021."}
data: {"type": "done"}
```

If the question is out of scope, the final tool call will be `report_scope_exceeded` (see below).

---

## Tool Catalog

### `get_schema`

Returns all tables and columns in the project's DuckDB. **Always called first.**

Returns: `{tables: [{name, columns: [{name, type}]}]}`

### `search_context`

Searches `contextDocuments` for background knowledge from uploaded research papers, reports, and URLs.

| Parameter | Required |
|-----------|----------|
| `query` | yes |
| `project_id` | no |

Returns: `{results: [{name, type, snippet}]}` — up to 5 matches with 600-char snippets.

### `run_sql`

Runs a SQL query against the project's DuckDB. Use for aggregations and direct lookups.

| Parameter | Required |
|-----------|----------|
| `query` | yes |
| `project_id` | no |

### `execute_python`

Runs Python code in a sandboxed subprocess. Use for statistical analysis, charts, and multi-step computations.

Available in sandbox: `sql(query)→DataFrame`, `get_table(name)→DataFrame`, `pd`, `np`, `plt`, `smf`, `sklearn`.

Timeout: 120 seconds.

### `search_data_registry`

Searches the `dataSourceRegistry` catalog. Used when the question can't be answered — suggests what data could be added to answer it.

| Parameter | Required |
|-----------|----------|
| `query` | yes |
| `provider` | no — filter to `census`, `fred`, `worldbank`, `bls` |

### `report_scope_exceeded`

Called when the question **cannot** be answered with the project's current data. This is a terminal tool — the agent stops after calling it.

```json
{
  "explanation": "This project doesn't have monthly CPI data by state.",
  "missing_data": "Monthly CPI index by state, 2010–2024",
  "suggested_sources": ["fred-state-cpi", "bls-cpi-series"]
}
```

The API returns this as a `tool_result` in the SSE stream. **The frontend handles it specially** — instead of displaying a normal answer, it shows a "Data Gap" card with the explanation, missing data description, and "Add to Project" buttons for each suggested source.

### `save_to_knowledge_base`

Saves a compiled finding to `contextDocuments` for future Q&A sessions.

| Parameter | Required |
|-----------|----------|
| `name` | yes |
| `content` | yes |
| `project_id` | no |

---

## Agent Behavior

### Workflow (always followed)

1. Call `get_schema` — understand what tables exist
2. Call `search_context` if the question might require background knowledge
3. Decide: can this question be answered with available data?
   - **Yes** → run SQL or Python, then summarize with specific numbers
   - **No** → call `report_scope_exceeded`
4. If running Python: always `print()` key numbers and create charts for trends

### Output style rules

- Lead with the direct answer, not the method
- Use concrete numbers ("23% higher", not "significantly higher")
- If results are empty, say so clearly — do not fabricate
- Use SQL for lookups/aggregations; use Python for multi-step analysis and visualization

### Turn limit

The agent runs for up to 12 turns. If the question is not answered within 12 turns, it emits `{"type": "done"}`.

---

## Scope Exceeded — Frontend Behavior

When `report_scope_exceeded` is called, the frontend renders a **Data Gap card** instead of a normal text answer:

```
┌─────────────────────────────────────────────────────┐
│ ⚠ This question is out of scope for this project    │
│                                                      │
│ Why: This project doesn't have monthly CPI data...  │
│                                                      │
│ Missing: Monthly CPI index by state, 2010–2024       │
│                                                      │
│ Suggested sources:                                   │
│   [+ Add fred-state-cpi]  [+ Add bls-cpi-series]   │
└─────────────────────────────────────────────────────┘
```

"Add to Project" buttons invoke the project setup agent's `add_data_source` tool flow.

---

## Convex Table — `questionSessions`

Q&A history is stored per-project in `questionSessions`.

| Field | Type | Notes |
|-------|------|-------|
| `projectId` | string | Foreign key to `projects._id` |
| `question` | string | The original question text |
| `answer` | string | Final text answer from the agent |
| `toolCalls` | array | `[{name, args, result}]` — full tool trace |
| `scopeExceeded` | boolean | True if `report_scope_exceeded` was called |
| `missingData` | string? | From `report_scope_exceeded` if applicable |
| `suggestedSources` | string[]? | Registry slugs suggested |
| `createdAt` | number | ms timestamp |

---

## Frontend — `/questions`

The Q&A page at `/questions` (project-scoped) provides a search-bar style interface.

**Layout:**
- Search bar at top — type a question and press Enter
- Answer rendered below with structured blocks:
  - Text paragraphs
  - SQL result tables (sortable)
  - Python-generated charts (rendered as `<img>` base64 or artifact URL)
  - Data gap card (if scope exceeded)
- History sidebar — previous questions for this project

**Planned:** Questions page will be accessible at `/[project]/questions` in the new project-scoped routing model.
