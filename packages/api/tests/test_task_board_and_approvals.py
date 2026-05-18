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


def test_update_task_can_clear_repo_backed_optional_fields(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    board = asyncio.run(planner_service.ensure_main_board(project))
    task = asyncio.run(
        planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title="Recover blocked task",
            description="Clear stale task metadata after recovery.",
            status="blocked",
            agent_role="health",
            approval_state="pending",
        )
    )
    asyncio.run(
        planner_service.update_task(
            task["_id"],
            project=project,
            blockerCategory="verification_failure",
        )
    )

    updated = asyncio.run(
        planner_service.update_task(
            task["_id"],
            project=project,
            status="done",
            approvalState=None,
            blockerCategory=None,
        )
    )

    assert updated is not None
    assert updated["status"] == "done"
    assert updated["approvalState"] is None
    assert updated["blockerCategory"] is None

    task_text = (tmp_path / "research_plan" / "tasks" / f"{task['_id']}.md").read_text(encoding="utf-8")
    assert "approval_state:" not in task_text
    assert "blocker_category:" not in task_text


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
    assert approval["status"] == "granted"
    approval_path = tmp_path / "research_plan" / "approvals" / f"{approval_id}.md"
    assert approval_path.exists()
    assert "status: granted" in approval_path.read_text(encoding="utf-8")
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


def test_list_tasks_dedupes_legacy_and_canonical_task_files(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)

    legacy_name = "resolve-artifact-integrity-gate-mismatch-for-pre-hydration-plann.md"
    canonical_name = "resolve-artifact-integrity-gate-mismatch-for-pre-hydration-planning.md"
    title = "Resolve artifact integrity-gate mismatch for pre-hydration planning"

    _write(
        task_dir / legacy_name,
        """---
title: Resolve artifact integrity-gate mismatch for pre-hydration planning
status: done
assigned_role: planner
---

## Description

Legacy task file.
""",
    )
    _write(
        task_dir / canonical_name,
        f"""---
task_id: resolve-artifact-integrity-gate-mismatch-for-pre-hydration-planning
title: {title}
status: done
assigned_role: planner
---

## Description

Canonical task file.
""",
    )

    tasks = asyncio.run(planner_service.list_tasks("main", project=project))

    assert len(tasks) == 1
    assert tasks[0]["_id"] == "resolve-artifact-integrity-gate-mismatch-for-pre-hydration-planning"


def test_reconcile_task_files_removes_lower_preference_duplicates(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    task_dir = tmp_path / "research_plan" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)

    _write(
        task_dir / "resolve-artifact-integrity-gate-mismatch-for-pre-hydration-plann.md",
        """---
title: Resolve artifact integrity-gate mismatch for pre-hydration planning
status: done
assigned_role: planner
---

## Description

Legacy task file.
""",
    )
    canonical = task_dir / "resolve-artifact-integrity-gate-mismatch-for-pre-hydration-planning.md"
    _write(
        canonical,
        """---
task_id: resolve-artifact-integrity-gate-mismatch-for-pre-hydration-planning
title: Resolve artifact integrity-gate mismatch for pre-hydration planning
status: done
assigned_role: planner
---

## Description

Canonical task file.
""",
    )

    result = asyncio.run(planner_service.reconcile_task_files(project))

    assert result["removed"] == ["research_plan/tasks/resolve-artifact-integrity-gate-mismatch-for-pre-hydration-plann.md"]
    assert canonical.exists()


def test_list_tasks_hides_stale_terminal_task_metadata(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    _write(
        tmp_path / "research_plan" / "tasks" / "done-task.md",
        """---
task_id: done-task
title: Done task
status: done
assigned_role: health
approval_state: pending
blocker_category: publish_failure
---

## Description

Completed task with stale metadata.
""",
    )

    tasks = asyncio.run(planner_service.list_tasks("main", project=project))

    assert len(tasks) == 1
    assert tasks[0]["status"] == "done"
    assert tasks[0]["approvalState"] is None


def test_list_tasks_leniently_parses_task_frontmatter_with_unquoted_backticks(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    _write(
        tmp_path / "research_plan" / "tasks" / "implement-first-pass-soccer-pipeline-steps-for-football-data-and.md",
        """---
title: Implement first-pass soccer pipeline steps for football-data and ClubElo
status: done
assigned_role: data
runner: codex_cli
dependencies: []
acceptance_criteria:
  - the default soccer pipeline no longer has `steps: []`
  - at least football-data and ClubElo are represented as executable pipeline steps or clearly justified alternates
related_files:
  - .ontology/pipelines
  - .ontology/sources
latest_run_summary: "Published commit 8b913f8e0f9b095993cc06a4152aac7aaa5fb84e"
---

## Description

Concrete pipeline task.
""",
    )

    tasks = asyncio.run(planner_service.list_tasks("main", project=project))

    assert len(tasks) == 1
    assert tasks[0]["status"] == "done"
    assert tasks[0]["agentRole"] == "data"
    assert tasks[0]["runner"] == "codex_cli"
    assert tasks[0]["acceptanceCriteria"][0] == "the default soccer pipeline no longer has `steps: []`"
    assert tasks[0]["blockerCategory"] is None


def test_reconcile_task_session_states_updates_terminal_task_from_session_truth(tmp_path: Path):
    from app.services import planner_service

    project = _project(tmp_path)
    _write(
        tmp_path / "research_plan" / "tasks" / "hydrate-task.md",
        """---
task_id: hydrate-task
title: Hydrate task
status: running
assigned_role: data
approval_state: granted
latest_run_summary: Not started
---

## Description

Hydrate the ontology.
""",
    )

    session_root = planner_service.session_files.ensure_session_root(tmp_path, "data", "sess-1")
    planner_service.session_files.update_state(
        session_root,
        session_id="sess-1",
        task_id="hydrate-task",
        status="completed",
        review_status="review",
        publish_commit_sha="abc123",
        completion_summary={
            "status": "completed",
            "assumptions_added": [],
            "assumptions_changed": [],
            "sources_used": [],
            "datasets_created": [],
            "artifacts_created": [],
            "claims_created": [],
            "verification_results": [],
            "open_questions": [],
            "blockers": [],
            "recommended_next_tasks": [],
        },
    )

    result = asyncio.run(planner_service.reconcile_task_session_states(project))
    tasks = asyncio.run(planner_service.list_tasks("main", project=project))

    assert result == {"updated": ["hydrate-task"]}
    assert tasks[0]["status"] == "done"
    assert tasks[0]["approvalState"] is None
    assert tasks[0]["latestRunSummary"] == "Published commit abc123"
