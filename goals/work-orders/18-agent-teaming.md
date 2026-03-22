# Work Order 18 — Agent Teaming Protocol

## Layer
3 — AI Agent Specialization

## Prerequisites
WO-16 (Data Engineer Agent), WO-17 (Analyst Agent)

## Goal
Implement a Coordinator agent that decomposes a research question into data engineering and analysis tasks, routes them to the appropriate specialized agents in sequence, and returns a unified result to the researcher.

## Background
This is the core vision: a researcher asks "What is the effect of the NJ minimum wage increase on county employment?" and the platform autonomously assembles the data, builds the pipeline, hydrates the graph, runs the analysis, and returns findings — without the researcher touching any config.

## Steps

### 1. Create `coordinator_agent.py`
File: `packages/api/app/services/coordinator_agent.py`

**System prompt:**
The coordinator receives a research question and produces a structured plan:
1. What data is needed (and whether it's already in the ontology)?
2. What analysis should be run?
3. Whether data engineering is required before analysis.

**Tool: `plan_research`**
The coordinator's only tool call. It asks the LLM to output a structured JSON plan:
```json
{
  "needs_data_engineering": true,
  "data_tasks": ["Fetch NJ county employment data from BLS", "Fetch minimum wage policy dates by state"],
  "analysis_tasks": ["DiD analysis: employment before/after minimum wage increase"],
  "has_all_data": false
}
```

### 2. Teaming loop
```python
async def run_team(
    research_question: str,
    history: list[dict],
    model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    1. Coordinator plans the work
    2. If needs_data_engineering: run Data Engineer agent for each data task
    3. Run Analyst agent for each analysis task
    4. Synthesize and return
    """
```

Yields SSE events with a new `agent_role` field:
```json
{"type": "role_change", "role": "coordinator", "message": "Planning research..."}
{"type": "role_change", "role": "data_engineer", "message": "Acquiring data..."}
{"type": "role_change", "role": "analyst", "message": "Running analysis..."}
```

### 3. Data check before engineering
Before routing to the Data Engineer, the coordinator checks whether the needed data is already in the ontology via `get_sql_schema`. If the required tables and columns exist, it skips data engineering entirely and goes directly to the Analyst.

### 4. Handoff context
When passing control from Data Engineer to Analyst, include a summary of what was built:
```
"The Data Engineer fetched BLS employment data for all NJ counties (2015–2024) and NJ minimum wage history. The ontology now contains Employment and WagePolicy classes. The DuckDB schema is: ..."
```

This context is prepended to the Analyst's first message.

### 5. New API endpoint
File: `packages/api/app/routers/agent.py`

```
POST /api/v1/agent/team/chat
```

Same SSE streaming interface. The workspace receives `role_change` events and displays them as phase indicators.

### 6. Workspace team mode UI
Add a "Team" option to the role selector (alongside General / Data Engineer / Analyst).

When Team mode is active:
- Show a phase indicator at the top: **Coordinator → Data Engineer → Analyst**
- Highlight the active phase
- Each agent's tool calls are grouped under their role header
- A final "Research Summary" section shows the Analyst's findings

### 7. Approval gate (optional, configurable)
Add a `require_approval` field to the team chat request. When `true`, the coordinator presents its plan and pauses, waiting for the researcher to confirm before dispatching agents. The UI shows "Approve Plan" and "Edit Plan" buttons.

This prevents the agent from autonomously running a pipeline and hydration without researcher oversight.

```
POST /api/v1/agent/team/chat
Body: { message, history, model, require_approval: true }
```

When the plan is ready, yields:
```json
{"type": "approval_required", "plan": {...}, "session_id": "..."}
```

The researcher calls:
```
POST /api/v1/agent/team/approve
Body: { session_id, approved: true }
```

## Affected Files
- `packages/api/app/services/coordinator_agent.py` — **create**
- `packages/api/app/routers/agent.py` — add `/team/chat` and `/team/approve` endpoints
- `packages/web/app/(dashboard)/workspace/page.tsx` — add Team role, phase indicator, approval gate UI
- `packages/web/lib/api.ts` — add `agent.teamChat()`, `agent.approveTeam()`

## Acceptance Criteria
- [ ] Team mode correctly routes a research question through Coordinator → Data Engineer → Analyst
- [ ] If data already exists in the ontology, the Data Engineer step is skipped
- [ ] Phase indicator updates in real time as each agent begins
- [ ] Approval gate pauses execution and waits for researcher confirmation
- [ ] The final output includes findings from the Analyst with data provenance from the Data Engineer
- [ ] Each agent's tool calls are visually grouped under their role label
