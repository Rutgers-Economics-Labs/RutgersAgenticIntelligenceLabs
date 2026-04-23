# Planner-First Work Orders

This queue replaces the old DB-first/platform-first backlog.

Durable project state belongs in Git and Markdown. The runtime database should only track projects, currently running agents, and encrypted secrets/policies. The planner is the only user-facing agent. Workers run one at a time and are controlled through file-backed sessions.

## Rules For Workers

- Do not restore the deleted legacy UI.
- Do not create new durable task, approval, planner-message, or historical-session database tables.
- Keep plans, approvals, tasks, blockers, and session summaries in repo files.
- Keep live machine traffic in `session.ndjson`, `commands.ndjson`, and `state.json`.
- Keep worker changes small enough for review.
- Run the most relevant tests or compile checks before finishing.

