# Work Order 17 — AI Analyst Agent

## Layer
3 — AI Agent Specialization

## Goal
Create a specialized Analyst agent focused on statistical analysis, econometric modeling, and research interpretation. Assumes clean data is already in the ontology.

## Background
The generalist agent writes passable analysis code but lacks the depth of econometric knowledge needed for rigorous research. The Analyst agent has a system prompt encoding best practices for causal inference, knows the available analysis modules (WO-19–22), and produces publication-quality outputs with correct interpretation.

## Steps

### 1. Create `analyst_agent.py`
File: `packages/api/app/services/analyst_agent.py`

**System prompt focus:**
- Assume the knowledge graph is populated and data is clean
- Always check parallel trends before running DiD
- Always report standard errors and confidence intervals
- Always interpret coefficients in plain English
- Flag threats to validity (selection bias, omitted variables, measurement error, SUTVA violations)
- Prefer APA-style result reporting
- Use the structured analysis modules (WO-19–22) when available, fall back to `execute_python` for custom analyses

**Tools (analysis-focused subset):**
- `get_sql_schema` — understand what data is available
- `run_sql` — explore the data
- `execute_python` — custom analysis code
- `get_series_data` — fetch time-series
- `run_did_analysis(config)` — from WO-19 (when available)
- `run_panel_regression(config)` — from WO-20 (when available)
- `run_event_study(config)` — from WO-21 (when available)
- `interpret_result(result_json)` — new tool: passes a result object back to the LLM for plain-English interpretation with validity flags

Does NOT have: `create_config`, `run_pipeline`, `list_configs` — data engineering is out of scope.

### 2. `interpret_result` tool
```python
async def _interpret_result(result: dict) -> dict:
    """
    Pass analysis output back to LLM for interpretation.
    Returns: {summary, key_findings, validity_concerns, suggested_next_steps}
    """
```

Uses a separate LLM call with a specialized interpretation prompt. This keeps the main analysis turn focused on computation and the interpretation turn focused on writing.

### 3. New API endpoint
File: `packages/api/app/routers/agent.py`

```
POST /api/v1/agent/analyst/chat
```

Same SSE streaming interface. Uses `analyst_agent.run_chat()`.

### 4. Workspace role selector update
Add "Analyst" option to the role selector from WO-16.

Role-appropriate example prompts:
- "Run a DiD analysis on NJ county income before and after 2020"
- "Is there a correlation between unemployment and housing prices across counties?"
- "Build a panel regression of GDP growth on population and employment"
- "Plot the unemployment time-series for Bergen, Hudson, and Essex counties"

### 5. Analyst-specific result rendering
When the Analyst agent returns results containing figures or tables, render them more prominently in the Workspace:
- Full-width figure display (not collapsed in a tool card)
- Result tables with sortable columns
- Interpretation text styled as a research finding (distinct visual treatment from normal prose)

This requires recognizing when an `execute_python` result contains `figures` or `dataframes` and promoting them out of the tool card into the main message flow.

### 6. Analysis history
Add a `savedAnalyses` Convex table to store the outputs of completed analyst sessions that the researcher chooses to save:
| Field | Type |
|-------|------|
| `title` | string |
| `sessionId` | string |
| `analysisType` | string |
| `summary` | string |
| `figures` | string[] (base64) |
| `tables` | any[] |
| `pipelineSlug` | string |
| `createdAt` | number |

"Save Analysis" button appears after a completed analyst session.

## New Convex Schema
- `savedAnalyses` table

## Affected Files
- `packages/api/app/services/analyst_agent.py` — **create**
- `packages/api/app/routers/agent.py` — add `/analyst/chat` endpoint
- `packages/web/convex/schema.ts` — add `savedAnalyses` table
- `packages/web/convex/analyses.ts` — **create**
- `packages/web/app/(dashboard)/workspace/page.tsx` — add Analyst role, promoted result rendering
- `packages/web/lib/api.ts` — add `agent.analystChat()`

## Acceptance Criteria
- [ ] Analyst agent correctly identifies and flags a violated parallel trends assumption
- [ ] Agent produces APA-style coefficient table output
- [ ] `interpret_result` returns validity concerns for a given analysis
- [ ] Analyst agent correctly refuses data-engineering requests ("please fetch unemployment data")
- [ ] Figures from `execute_python` render full-width in the workspace (not collapsed in tool card)
- [ ] "Save Analysis" creates a Convex record retrievable later
