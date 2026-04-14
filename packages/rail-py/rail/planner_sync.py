"""
planner_sync.py — Sync rules and Git mirror logic for planner task state.

Responsible for writing research_plan/ files when the operational task board
reaches a meaningful state transition.  The DB (Convex) remains the live source
of truth; these files give users and future agents durable, Git-visible context.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Sync triggers
# ---------------------------------------------------------------------------

# Task event types that should trigger a Git mirror write.
SYNC_TRIGGERS: frozenset[str] = frozenset(
    [
        "created",
        "moved_to_ready",
        "approval_requested",
        "approval_granted",
        "runner_started",
        "blocked",
        "verification_passed",
        "done",
    ]
)

# Task status values that represent "material" state changes worth mirroring.
MATERIAL_STATUSES: frozenset[str] = frozenset(
    [
        "ready",
        "awaiting_approval",
        "running",
        "blocked",
        "review",
        "done",
        "cancelled",
    ]
)

# Ordered status columns for the task board markdown snapshot.
BOARD_COLUMNS: list[str] = [
    "backlog",
    "ready",
    "awaiting_approval",
    "running",
    "blocked",
    "review",
    "done",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a task title to a safe file slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:64].rstrip("-")


def _snapshot_path(task: dict[str, Any]) -> str:
    """Return the canonical research_plan/ path for a task file."""
    slug = _slugify(task.get("title", task.get("_id", "unknown")))
    return f"research_plan/tasks/{slug}.md"


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------

def render_task_md(task: dict[str, Any]) -> str:
    """Render a single task as a frontmatter markdown card."""
    title = task.get("title", "")
    status = task.get("status", "backlog")
    agent_role = task.get("agentRole", "")
    description = task.get("description", "")
    acceptance_criteria: list[str] = task.get("acceptanceCriteria") or []
    repo_paths: list[str] = task.get("repoPaths") or []
    latest_run_summary = task.get("latestRunSummary", "Not started")
    approval_state = task.get("approvalState", "")
    runner = task.get("runner", "")

    dep_ids: list[str] = [str(d) for d in (task.get("dependsOnTaskIds") or [])]

    lines: list[str] = ["---"]
    lines.append(f"title: {title}")
    lines.append(f"status: {status}")
    lines.append(f"assigned_role: {agent_role}")
    if approval_state:
        lines.append(f"approval_state: {approval_state}")
    if runner:
        lines.append(f"runner: {runner}")
    if dep_ids:
        lines.append("dependencies:")
        for d in dep_ids:
            lines.append(f"  - {d}")
    else:
        lines.append("dependencies: []")
    if acceptance_criteria:
        lines.append("acceptance_criteria:")
        for ac in acceptance_criteria:
            lines.append(f"  - {ac}")
    else:
        lines.append("acceptance_criteria: []")
    if repo_paths:
        lines.append("related_files:")
        for p in repo_paths:
            lines.append(f"  - {p}")
    else:
        lines.append("related_files: []")
    lines.append(f'latest_run_summary: "{latest_run_summary}"')
    lines.append("---")
    lines.append("")
    if description:
        lines.append("## Description")
        lines.append("")
        lines.append(description)
        lines.append("")
    return "\n".join(lines)


def render_task_board_md(board: dict[str, Any], tasks: list[dict[str, Any]]) -> str:
    """Render a Git-visible snapshot of the full task board."""
    title = board.get("title", "Task Board")
    board_status = board.get("status", "")

    by_status: dict[str, list[dict]] = {col: [] for col in BOARD_COLUMNS}
    for task in tasks:
        s = task.get("status", "backlog")
        if s not in by_status:
            by_status[s] = []
        by_status[s].append(task)

    lines: list[str] = [f"# {title}"]
    if board_status:
        lines.append(f"_Board status: {board_status}_")
    lines.append("")
    lines.append(
        "_This file is a mirrored snapshot of the operational task board. "
        "The DB remains authoritative for live execution state._"
    )
    lines.append("")

    for col in BOARD_COLUMNS:
        col_tasks = by_status.get(col, [])
        heading = col.replace("_", " ").title()
        lines.append(f"## {heading}")
        lines.append("")
        if col_tasks:
            for t in col_tasks:
                slug = _slugify(t.get("title", ""))
                role = t.get("agentRole", "")
                lines.append(f"- **{t['title']}** (`{role}`) → `research_plan/tasks/{slug}.md`")
        else:
            lines.append("_empty_")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PlannerSync
# ---------------------------------------------------------------------------

class PlannerSync:
    """Write Git-visible planner files when the task board changes materially."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path)

    def should_sync(self, event_type: str) -> bool:
        """Return True if this event type warrants a Git mirror write."""
        return event_type in SYNC_TRIGGERS

    def mirror_task(self, task: dict[str, Any]) -> str:
        """
        Write research_plan/tasks/<slug>.md for a single task.

        Returns the path written (relative to repo root), which should be
        stored back into tasks.gitSnapshotPath in the DB.
        """
        rel_path = _snapshot_path(task)
        abs_path = self.repo_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(render_task_md(task), encoding="utf-8")
        return rel_path

    def mirror_board(
        self, board: dict[str, Any], tasks: list[dict[str, Any]]
    ) -> str:
        """
        Write research_plan/task_board.md with all tasks grouped by status.

        Returns the path written (relative to repo root).
        """
        rel_path = "research_plan/task_board.md"
        abs_path = self.repo_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(render_task_board_md(board, tasks), encoding="utf-8")
        return rel_path

    def sync_on_transition(
        self,
        event_type: str,
        board: dict[str, Any],
        task: dict[str, Any],
        all_board_tasks: list[dict[str, Any]],
    ) -> dict[str, str]:
        """
        Central entry point called by the planner after a task event.

        If the event type is a sync trigger, writes both the individual task
        file and the board snapshot.

        Returns a dict of { rel_path: "written" } for paths that were updated,
        or an empty dict if no sync was needed.
        """
        if not self.should_sync(event_type):
            return {}

        written: dict[str, str] = {}
        task_path = self.mirror_task(task)
        written[task_path] = "written"
        board_path = self.mirror_board(board, all_board_tasks)
        written[board_path] = "written"
        return written
