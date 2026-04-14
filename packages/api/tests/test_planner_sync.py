"""
Tests for rail.planner_sync — WO-F6.3

Covers:
  - SYNC_TRIGGERS / MATERIAL_STATUSES constants
  - _slugify() helper
  - render_task_md()
  - render_task_board_md()
  - PlannerSync.should_sync()
  - PlannerSync.mirror_task()
  - PlannerSync.mirror_board()
  - PlannerSync.sync_on_transition()
"""
from __future__ import annotations

import pytest
from pathlib import Path

from rail.planner_sync import (
    SYNC_TRIGGERS,
    MATERIAL_STATUSES,
    BOARD_COLUMNS,
    _slugify,
    _snapshot_path,
    render_task_md,
    render_task_board_md,
    PlannerSync,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TASK: dict = {
    "_id": "task123",
    "title": "Analyse Unemployment Data",
    "status": "ready",
    "agentRole": "data",
    "description": "Run the quarterly unemployment analysis pipeline.",
    "acceptanceCriteria": ["DuckDB file present", "Chart exported"],
    "repoPaths": ["research_plan/tasks/analyse-unemployment-data.md"],
    "latestRunSummary": "Not started",
    "approvalState": "pending",
    "runner": "jules",
    "dependsOnTaskIds": ["task_dep_1"],
}

SAMPLE_BOARD: dict = {
    "_id": "board001",
    "title": "Q2 Research Board",
    "status": "active",
}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_sync_triggers_is_frozenset(self):
        assert isinstance(SYNC_TRIGGERS, frozenset)

    def test_sync_triggers_contains_expected_events(self):
        expected = {"created", "moved_to_ready", "approval_requested", "approval_granted",
                    "runner_started", "blocked", "verification_passed", "done"}
        assert expected.issubset(SYNC_TRIGGERS)

    def test_sync_triggers_does_not_contain_noise(self):
        assert "status_changed" not in SYNC_TRIGGERS
        assert "comment_added" not in SYNC_TRIGGERS

    def test_material_statuses_is_frozenset(self):
        assert isinstance(MATERIAL_STATUSES, frozenset)

    def test_material_statuses_contains_key_statuses(self):
        for s in ("ready", "awaiting_approval", "running", "blocked", "review", "done", "cancelled"):
            assert s in MATERIAL_STATUSES

    def test_board_columns_is_ordered_list(self):
        assert isinstance(BOARD_COLUMNS, list)
        # backlog should come before done
        assert BOARD_COLUMNS.index("backlog") < BOARD_COLUMNS.index("done")


# ---------------------------------------------------------------------------
# _slugify helper
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_lowercases_input(self):
        assert _slugify("Hello World") == "hello-world"

    def test_replaces_spaces_with_dashes(self):
        assert _slugify("foo bar baz") == "foo-bar-baz"

    def test_strips_special_chars(self):
        slug = _slugify("Analyse: NJ (County-Level) GDP!")
        assert slug == "analyse-nj-county-level-gdp"

    def test_collapses_multiple_dashes(self):
        assert _slugify("foo  --  bar") == "foo-bar"

    def test_truncates_to_64_chars(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 64

    def test_strips_trailing_dash(self):
        slug = _slugify("hello-")
        assert not slug.endswith("-")

    def test_empty_string(self):
        result = _slugify("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _snapshot_path helper
# ---------------------------------------------------------------------------

class TestSnapshotPath:
    def test_returns_research_plan_prefix(self):
        path = _snapshot_path({"title": "My Task"})
        assert path.startswith("research_plan/tasks/")

    def test_uses_title_for_slug(self):
        path = _snapshot_path({"title": "Analyse Data"})
        assert "analyse-data" in path

    def test_falls_back_to_id(self):
        path = _snapshot_path({"_id": "abc123"})
        assert "abc123" in path

    def test_ends_with_md(self):
        path = _snapshot_path({"title": "My Task"})
        assert path.endswith(".md")


# ---------------------------------------------------------------------------
# render_task_md
# ---------------------------------------------------------------------------

class TestRenderTaskMd:
    def test_contains_yaml_frontmatter_delimiters(self):
        md = render_task_md(SAMPLE_TASK)
        assert md.startswith("---")
        # second delimiter
        assert md.count("---") >= 2

    def test_title_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "title: Analyse Unemployment Data" in md

    def test_status_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "status: ready" in md

    def test_assigned_role_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "assigned_role: data" in md

    def test_approval_state_present_when_set(self):
        md = render_task_md(SAMPLE_TASK)
        assert "approval_state: pending" in md

    def test_runner_present_when_set(self):
        md = render_task_md(SAMPLE_TASK)
        assert "runner: jules" in md

    def test_dependencies_listed(self):
        md = render_task_md(SAMPLE_TASK)
        assert "task_dep_1" in md

    def test_acceptance_criteria_listed(self):
        md = render_task_md(SAMPLE_TASK)
        assert "DuckDB file present" in md
        assert "Chart exported" in md

    def test_related_files_listed(self):
        md = render_task_md(SAMPLE_TASK)
        assert "research_plan/tasks/analyse-unemployment-data.md" in md

    def test_description_section_present(self):
        md = render_task_md(SAMPLE_TASK)
        assert "## Description" in md
        assert "unemployment analysis pipeline" in md

    def test_empty_lists_render_as_empty(self):
        task = {**SAMPLE_TASK, "acceptanceCriteria": [], "repoPaths": [], "dependsOnTaskIds": []}
        md = render_task_md(task)
        assert "acceptance_criteria: []" in md
        assert "related_files: []" in md
        assert "dependencies: []" in md

    def test_missing_description_omits_section(self):
        task = {**SAMPLE_TASK, "description": ""}
        md = render_task_md(task)
        assert "## Description" not in md

    def test_approval_state_omitted_when_empty(self):
        task = {**SAMPLE_TASK, "approvalState": ""}
        md = render_task_md(task)
        assert "approval_state" not in md

    def test_runner_omitted_when_empty(self):
        task = {**SAMPLE_TASK, "runner": ""}
        md = render_task_md(task)
        assert "runner:" not in md


# ---------------------------------------------------------------------------
# render_task_board_md
# ---------------------------------------------------------------------------

class TestRenderTaskBoardMd:
    def test_contains_board_title(self):
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK])
        assert "Q2 Research Board" in md

    def test_contains_board_status(self):
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK])
        assert "active" in md

    def test_all_columns_present(self):
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK])
        for col in BOARD_COLUMNS:
            heading = col.replace("_", " ").title()
            assert f"## {heading}" in md

    def test_task_appears_in_correct_column(self):
        # SAMPLE_TASK status = "ready"
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK])
        assert "Analyse Unemployment Data" in md

    def test_empty_column_shows_empty_marker(self):
        # Move task to done so other columns are empty
        task = {**SAMPLE_TASK, "status": "done"}
        md = render_task_board_md(SAMPLE_BOARD, [task])
        assert "_empty_" in md

    def test_includes_snapshot_path_reference(self):
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK])
        assert "research_plan/tasks/" in md

    def test_multiple_tasks_same_column(self):
        task2 = {**SAMPLE_TASK, "title": "Second Task", "_id": "task456"}
        md = render_task_board_md(SAMPLE_BOARD, [SAMPLE_TASK, task2])
        assert "Analyse Unemployment Data" in md
        assert "Second Task" in md

    def test_no_tasks_all_columns_empty(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert md.count("_empty_") == len(BOARD_COLUMNS)

    def test_disclaimer_line_present(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert "mirrored snapshot" in md


# ---------------------------------------------------------------------------
# PlannerSync
# ---------------------------------------------------------------------------

class TestPlannerSyncShouldSync:
    def test_returns_true_for_trigger_events(self):
        sync = PlannerSync("/tmp/fake")
        for event in SYNC_TRIGGERS:
            assert sync.should_sync(event) is True

    def test_returns_false_for_non_trigger(self):
        sync = PlannerSync("/tmp/fake")
        assert sync.should_sync("comment_added") is False
        assert sync.should_sync("") is False
        assert sync.should_sync("status_changed") is False


class TestPlannerSyncMirrorTask:
    def test_writes_file_to_correct_path(self, tmp_path):
        sync = PlannerSync(tmp_path)
        rel_path = sync.mirror_task(SAMPLE_TASK)
        assert rel_path.startswith("research_plan/tasks/")
        assert rel_path.endswith(".md")
        assert (tmp_path / rel_path).exists()

    def test_written_file_contains_task_title(self, tmp_path):
        sync = PlannerSync(tmp_path)
        rel_path = sync.mirror_task(SAMPLE_TASK)
        content = (tmp_path / rel_path).read_text()
        assert "Analyse Unemployment Data" in content

    def test_creates_parent_directories(self, tmp_path):
        sync = PlannerSync(tmp_path)
        sync.mirror_task(SAMPLE_TASK)
        assert (tmp_path / "research_plan" / "tasks").is_dir()

    def test_returns_string_rel_path(self, tmp_path):
        sync = PlannerSync(tmp_path)
        result = sync.mirror_task(SAMPLE_TASK)
        assert isinstance(result, str)


class TestPlannerSyncMirrorBoard:
    def test_writes_task_board_md(self, tmp_path):
        sync = PlannerSync(tmp_path)
        rel_path = sync.mirror_board(SAMPLE_BOARD, [SAMPLE_TASK])
        assert rel_path == "research_plan/task_board.md"
        assert (tmp_path / rel_path).exists()

    def test_board_file_contains_board_title(self, tmp_path):
        sync = PlannerSync(tmp_path)
        rel_path = sync.mirror_board(SAMPLE_BOARD, [SAMPLE_TASK])
        content = (tmp_path / rel_path).read_text()
        assert "Q2 Research Board" in content

    def test_creates_research_plan_dir(self, tmp_path):
        sync = PlannerSync(tmp_path)
        sync.mirror_board(SAMPLE_BOARD, [])
        assert (tmp_path / "research_plan").is_dir()


class TestPlannerSyncOnTransition:
    def test_sync_trigger_writes_both_files(self, tmp_path):
        sync = PlannerSync(tmp_path)
        result = sync.sync_on_transition(
            event_type="done",
            board=SAMPLE_BOARD,
            task=SAMPLE_TASK,
            all_board_tasks=[SAMPLE_TASK],
        )
        assert len(result) == 2
        for path, status in result.items():
            assert status == "written"
            assert (tmp_path / path).exists()

    def test_non_trigger_returns_empty_dict(self, tmp_path):
        sync = PlannerSync(tmp_path)
        result = sync.sync_on_transition(
            event_type="comment_added",
            board=SAMPLE_BOARD,
            task=SAMPLE_TASK,
            all_board_tasks=[SAMPLE_TASK],
        )
        assert result == {}
        # No files should have been written
        assert not (tmp_path / "research_plan").exists()

    def test_all_trigger_events_cause_sync(self, tmp_path):
        sync = PlannerSync(tmp_path)
        for event in SYNC_TRIGGERS:
            result = sync.sync_on_transition(
                event_type=event,
                board=SAMPLE_BOARD,
                task=SAMPLE_TASK,
                all_board_tasks=[SAMPLE_TASK],
            )
            assert len(result) == 2, f"Expected 2 written paths for event {event!r}"

    def test_repo_path_as_string(self, tmp_path):
        sync = PlannerSync(str(tmp_path))
        result = sync.sync_on_transition("created", SAMPLE_BOARD, SAMPLE_TASK, [SAMPLE_TASK])
        assert len(result) == 2
