"""Planner task board and approval tests for the repo-backed planner state."""

from __future__ import annotations

import asyncio
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(tmp_path: Path) -> dict:
    return {
        "_id": "project-id-abc",
        "name": "Test Project",
        "slug": "test-project",
        "status": "ready",
        "localRepoPath": str(tmp_path),
        "apiConfigSlugs": [],
    }


def test_ensure_main_board_uses_project_record(tmp_path: Path):
    from app.services import planner_service

    board = asyncio.run(planner_service.ensure_main_board(_project(tmp_path)))

    assert board["_id"] == "main"
    assert board["projectId"] == "project-id-abc"


def test_create_task_writes_repo_backed_task_file(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    board = asyncio.run(planner_service.ensure_main_board(project))

    task = asyncio.run(
        planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title="Add county labor source",
            description="Add and validate a new county labor data source.",
            status="backlog",
            agent_role="data",
            repo_paths=[".ontology/sources/county_labor.yaml"],
            acceptance_criteria=["YAML validates", "dry run passes"],
        )
    )

    task_path = tmp_path / "research_plan" / "tasks" / f"{task['_id']}.md"

    assert task_path.exists()
    assert task["projectId"] == "project-id-abc"
    assert "county labor" in task_path.read_text(encoding="utf-8").lower()


def test_update_task_updates_repo_file(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    board = asyncio.run(planner_service.ensure_main_board(project))
    task = asyncio.run(
        planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title="Add county labor source",
            description="Add and validate a new county labor data source.",
            status="backlog",
            agent_role="data",
        )
    )

    updated = asyncio.run(planner_service.update_task(task["_id"], project=project, status="ready"))

    assert updated is not None
    assert updated["status"] == "ready"
    assert "status: ready" in (tmp_path / "research_plan" / "tasks" / f"{task['_id']}.md").read_text(encoding="utf-8")


def test_create_and_resolve_approval_use_repo_files(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)

    approval_id = asyncio.run(
        planner_service.create_approval(
            project=project,
            task_id="task-1",
            agent_session_id=None,
            approval_type="run_task",
        )
    )
    approval = asyncio.run(
        planner_service.resolve_approval(
            project=project,
            approval_id=approval_id,
            status="approved",
            granted_by_user_id="user-1",
            resolution_note="Looks good.",
        )
    )

    assert approval is not None
    assert approval["status"] == "approved"
    approval_path = tmp_path / "research_plan" / "approvals" / f"{approval_id}.md"
    assert approval_path.exists()
    assert "Looks good." in approval_path.read_text(encoding="utf-8")


def test_sync_planner_files_writes_indexes(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    board = asyncio.run(planner_service.ensure_main_board(project))
    asyncio.run(
        planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title="Blocked task",
            description="Something is blocked.",
            status="blocked",
            agent_role="data",
        )
    )
    asyncio.run(
        planner_service.create_approval(
            project=project,
            task_id="blocked-task",
            agent_session_id=None,
            approval_type="run_task",
        )
    )

    asyncio.run(planner_service.sync_planner_files(project, board))

    assert (tmp_path / "research_plan" / "current_plan.md").exists()
    assert (tmp_path / "research_plan" / "task_board.md").exists()
    assert (tmp_path / "research_plan" / "approvals.md").exists()
    blockers = (tmp_path / "research_plan" / "blockers.md").read_text(encoding="utf-8")
    assert "Blocked task" in blockers
