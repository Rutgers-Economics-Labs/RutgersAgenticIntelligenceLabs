# Work Order 7.5: UI — Agentic Observability & Context Dashboard

## Objective
Upgrade the Research Agent UI to provide visibility into the role-based reasoning process and the formal "operational slice" context.

## Requirements
1.  **Role-Based Stepper**:
    *   Update `AgentChat.tsx` to display the current sub-agent role (e.g., "Planner is decomposing your question...", "Coverage is verifying data...").
    *   Implement an "Expert Mode" toggle to show the low-level tool calls and thoughts per role.
2.  **Context Dashboard**:
    *   Create a per-session sidebar or overlay that visualizes the `StructuredContextBundle`.
    *   Show table names, row counts, and active ontology classes for the current query.
3.  **Coverage Heatmap**:
    *   Update the `SchemaBrowser.tsx` to include a "Coverage Status" column.
    *   Highlight classes that have hydrated data in the current project context.
4.  **Stability & Cleanup**:
    *   Ensure the UI correctly handles job statuses from the new `artifact_registry`.
    *   Fix any regressions in the SQL and Ontology explorer pages caused by the project-scoped routing migration.

## Verification
- Manual verification of the "Role Thinking" state in the Chat UI.
- Verify that the Schema Browser correctly highlights hydrated data.
