# Work Order 7.3: Role-Based Agentic Runtime

## Objective
Decompose the monolithic agent into specialized roles with restricted tool access to improve accuracy and auditability.

## Requirements
1.  **Role Definitions**:
    *   Create `packages/api/app/services/agent_roles/`:
        *   `planner.py`: Goal decomposition.
        *   `coverage.py`: Data-gap identification.
        *   `onboarding.py`: Connector/API config creation.
        *   `analyzer.py`: SQL/Python execution.
        *   `explainer.py`: Insight synthesis.
2.  **Orchestrator Refactor**:
    *   Update `agent_service.py` to manage multi-role turn sequences.
    *   Implement "Tool Masking": Only roles like `analyzer` should see the `run_sql` tool.
3.  **State Management**:
    *   Persist role-specific "Thoughts" (Chain of Thought) in the Convex `agentSessions` table so the UI can display them.

## Verification
- Run a multi-step research query and verify that the `Planner` runs before the `Analyzer`.
- Ensure the `Analyzer` cannot call `create_pipeline` even if it tried.
