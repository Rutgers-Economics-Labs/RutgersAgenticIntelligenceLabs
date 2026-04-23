from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from rail.manifest import load_manifest

from app.services import planner_service, session_files


async def _run_planner_turn(**kwargs):
    from app.services import planner_runtime

    return await planner_runtime.run_planner_turn(**kwargs)


def build_local_project_record(
    project_root: str | Path,
    *,
    project_id: str | None = None,
    git_repo_url: str | None = None,
) -> dict[str, Any]:
    """
    Build a minimal project record from a local repo for planner execution.

    This is useful for harnessing the planner against a repo checkout without
    requiring the full project-creation UX first. Database-backed planner tools
    still require the operational backend to be configured.
    """
    root = Path(project_root).resolve()
    manifest = load_manifest(root)
    return {
        "_id": project_id or f"local-{manifest.project.slug}-{uuid4().hex[:8]}",
        "name": manifest.project.name,
        "slug": manifest.project.slug,
        "description": manifest.project.description,
        "defaultBranch": manifest.project.default_branch,
        "gitRepoUrl": git_repo_url or "",
        "localRepoPath": str(root),
        "status": "ready",
    }


@dataclass
class PlannerHarness:
    """
    Thin stateful wrapper around the planner runtime.

    The harness keeps conversation history between turns and exposes a simple
    `ask()` method that can be used by a future UI, a CLI, or tests.
    """

    project: dict[str, Any]
    model: str | None = None
    persist: bool = False
    history: list[dict[str, str]] = field(default_factory=list)
    thread_id: str = "planner"

    @classmethod
    async def from_project_slug(
        cls,
        slug: str,
        *,
        model: str | None = None,
        persist: bool = True,
    ) -> "PlannerHarness":
        project = await planner_service.get_project_by_slug(slug)
        return cls(project=project, model=model, persist=persist)

    @classmethod
    def from_local_repo(
        cls,
        project_root: str | Path,
        *,
        model: str | None = None,
        persist: bool = False,
        git_repo_url: str | None = None,
    ) -> "PlannerHarness":
        project = build_local_project_record(
            project_root,
            git_repo_url=git_repo_url,
        )
        return cls(project=project, model=model, persist=persist)

    async def ask(self, user_message: str) -> dict[str, Any]:
        root = None
        local_root = self.project.get("localRepoPath")
        if local_root:
            root = session_files.ensure_session_root(local_root, "planner", self.thread_id)
            session_files.append_event(
                root,
                "user_message",
                role="user",
                content=user_message,
                message_type="chat",
            )
        result = await _run_planner_turn(
            project=self.project,
            user_message=user_message,
            history=self.history,
            model=self.model,
            persist=self.persist,
        )
        self.history.append({"role": "user", "content": user_message})
        assistant_message = result.get("assistantMessage") or ""
        self.history.append({"role": "assistant", "content": assistant_message})
        if root is not None:
            session_files.append_event(
                root,
                "assistant_message",
                role="assistant",
                content=assistant_message,
                message_type="chat",
            )
        return result


def format_planner_result(result: dict[str, Any]) -> str:
    """
    Human-friendly formatter for terminal use.
    """
    lines: list[str] = []

    assistant = (result.get("assistantMessage") or "").strip()
    if assistant:
        lines.append(assistant)
    else:
        lines.append("[No assistant message returned]")

    tasks = result.get("tasks") or []
    if tasks:
        lines.append("")
        lines.append("Tasks:")
        for task in tasks:
            title = task.get("title") or str(task.get("_id"))
            status = task.get("status") or "unknown"
            role = task.get("agentRole") or task.get("agent_role") or "unknown"
            lines.append(f"- [{status}] ({role}) {title}")

    return "\n".join(lines)
