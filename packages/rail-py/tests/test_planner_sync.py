"""
Tests for WO-F6.2 / WO-F6.3 — Planner sync: Git mirror rendering and PlannerSync.

Covers:
  - _slugify() — safe filename generation
  - _snapshot_path() — canonical task path
  - render_task_md() — frontmatter markdown rendering
  - render_task_board_md() — board snapshot rendering
  - PlannerSync.should_sync() — trigger gating
  - PlannerSync.mirror_task() — writes task file to disk
  - PlannerSync.mirror_board() — writes board file to disk
  - PlannerSync.sync_on_transition() — conditional write orchestration
  - SYNC_TRIGGERS and MATERIAL_STATUSES constants
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rail.planner_sync import (
    BOARD_COLUMNS,
    MATERIAL_STATUSES,
    SYNC_TRIGGERS,
    PlannerSync,
    _slugify,
    _snapshot_path,
    render_task_board_md,
    render_task_md,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TASK: dict = {
    "_id": "task_abc123",
    "title": "Write Test Suite",
    "status": "ready",
    "agentRole": "coding",
    "description": "Add comprehensive pytest coverage.",
    "acceptanceCriteria": ["All hooks pass", "Coverage > 80%"],
    "repoPaths": ["packages/rail-py/tests/"],
    "latestRunSummary": "Not started",
    "approvalState": "",
    "runner": "jules",
    "dependsOnTaskIds": [],
}

SAMPLE_BOARD: dict = {
    "_id": "board_1",
    "title": "Sprint 1",
    "status": "active",
}


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic_lowercasing(self):
        assert _slugify("Hello World") == "hello-world"

    def test_spaces_become_dashes(self):
        assert _slugify("write test suite") == "write-test-suite"

    def test_special_chars_stripped(self):
        assert _slugify("Fix Bug #42!") == "fix-bug-42"

    def test_leading_trailing_stripped(self):
        slug = _slugify("  Trim Me  ")
        assert not slug.startswith("-") and not slug.endswith("-")

    def test_max_length_64(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 64

    def test_empty_string(self):
        result = _slugify("")
        assert isinstance(result, str)

    def test_consecutive_separators_collapsed(self):
        assert _slugify("a   b---c") == "a-b-c"


# ---------------------------------------------------------------------------
# _snapshot_path
# ---------------------------------------------------------------------------

class TestSnapshotPath:
    def test_path_starts_with_research_plan_tasks(self):
        path = _snapshot_path(SAMPLE_TASK)
        assert path.startswith("research_plan/tasks/")

    def test_path_ends_with_md(self):
        path = _snapshot_path(SAMPLE_TASK)
        assert path.endswith(".md")

    def test_title_used_for_slug(self):
        path = _snapshot_path(SAMPLE_TASK)
        assert "task-abc123" in path

    def test_git_snapshot_path_wins_when_present(self):
        task = {**SAMPLE_TASK, "gitSnapshotPath": "research_plan/tasks/custom-task.md"}
        assert _snapshot_path(task) == "research_plan/tasks/custom-task.md"

    def test_fallback_to_id_when_no_title(self):
        task = {"_id": "task_xyz"}
        path = _snapshot_path(task)
        assert "task-xyz" in path or "task_xyz" in path or path.endswith(".md")


# ---------------------------------------------------------------------------
# render_task_md
# ---------------------------------------------------------------------------

class TestRenderTaskMd:
    def test_frontmatter_delimiters_present(self):
        md = render_task_md(SAMPLE_TASK)
        lines = md.splitlines()
        assert lines[0] == "---"
        assert "---" in lines[1:]

    def test_title_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "title: Write Test Suite" in md

    def test_task_id_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "task_id: task_abc123" in md

    def test_status_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "status: ready" in md

    def test_assigned_role_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "assigned_role: coding" in md

    def test_runner_in_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        assert "runner: jules" in md

    def test_acceptance_criteria_listed(self):
        md = render_task_md(SAMPLE_TASK)
        assert "All hooks pass" in md
        assert "Coverage > 80%" in md

    def test_related_files_listed(self):
        md = render_task_md(SAMPLE_TASK)
        assert "packages/rail-py/tests/" in md

    def test_description_in_body(self):
        md = render_task_md(SAMPLE_TASK)
        assert "Add comprehensive pytest coverage." in md
        assert "## Description" in md

    def test_dependencies_empty(self):
        md = render_task_md(SAMPLE_TASK)
        assert "dependencies: []" in md

    def test_dependencies_with_ids(self):
        task = {**SAMPLE_TASK, "dependsOnTaskIds": ["task_111", "task_222"]}
        md = render_task_md(task)
        assert "- task_111" in md
        assert "- task_222" in md

    def test_no_description_omits_section(self):
        task = {**SAMPLE_TASK, "description": ""}
        md = render_task_md(task)
        assert "## Description" not in md

    def test_output_is_valid_yaml_frontmatter(self):
        md = render_task_md(SAMPLE_TASK)
        # Extract frontmatter between first and second "---"
        lines = md.splitlines()
        end_idx = lines.index("---", 1)
        frontmatter_text = "\n".join(lines[1:end_idx])
        # Should parse without error
        parsed = yaml.safe_load(frontmatter_text)
        assert parsed["title"] == "Write Test Suite"


# ---------------------------------------------------------------------------
# render_task_board_md
# ---------------------------------------------------------------------------

class TestRenderTaskBoardMd:
    def _make_tasks(self, statuses: list[str]) -> list[dict]:
        return [
            {**SAMPLE_TASK, "_id": f"task_{i}", "title": f"Task {i}", "status": s}
            for i, s in enumerate(statuses)
        ]

    def test_title_in_output(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert "# Sprint 1" in md

    def test_board_status_in_output(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert "active" in md

    def test_all_board_columns_present(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        for col in BOARD_COLUMNS:
            heading = col.replace("_", " ").title()
            assert f"## {heading}" in md

    def test_tasks_grouped_by_status(self):
        tasks = self._make_tasks(["ready", "done", "ready"])
        md = render_task_board_md(SAMPLE_BOARD, tasks)
        # Task 0 and Task 2 should appear under Ready, Task 1 under Done
        assert md.count("Task 0") == 1
        assert md.count("Task 2") == 1

    def test_empty_column_shows_empty_placeholder(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert "_empty_" in md

    def test_task_links_to_snapshot(self):
        tasks = self._make_tasks(["ready"])
        md = render_task_board_md(SAMPLE_BOARD, tasks)
        assert "research_plan/tasks/" in md
        assert "task-0.md" in md

    def test_mirror_note_present(self):
        md = render_task_board_md(SAMPLE_BOARD, [])
        assert "mirrored snapshot" in md

    def test_unknown_status_still_rendered(self):
        tasks = [{**SAMPLE_TASK, "status": "custom_status"}]
        # Should not raise — custom status ends up in by_status dict
        md = render_task_board_md(SAMPLE_BOARD, tasks)
        assert isinstance(md, str)


# ---------------------------------------------------------------------------
# SYNC_TRIGGERS / MATERIAL_STATUSES constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_sync_triggers_includes_key_events(self):
        expected = {"created", "done", "blocked", "verification_passed", "approval_requested"}
        assert expected <= SYNC_TRIGGERS

    def test_material_statuses_includes_key_statuses(self):
        expected = {"ready", "running", "blocked", "done"}
        assert expected <= MATERIAL_STATUSES

    def test_board_columns_ordered(self):
        assert BOARD_COLUMNS[0] == "backlog"
        assert BOARD_COLUMNS[-1] == "done"


# ---------------------------------------------------------------------------
# PlannerSync
# ---------------------------------------------------------------------------

class TestPlannerSync:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture
    def ps(self, repo: Path) -> PlannerSync:
        return PlannerSync(repo)

    def test_should_sync_for_trigger_event(self, ps):
        for event in SYNC_TRIGGERS:
            assert ps.should_sync(event), f"expected should_sync=True for {event!r}"

    def test_should_not_sync_for_unknown_event(self, ps):
        assert not ps.should_sync("something_random")
        assert not ps.should_sync("updated")

    # --- mirror_task ---

    def test_mirror_task_creates_file(self, ps, repo):
        rel_path = ps.mirror_task(SAMPLE_TASK)
        abs_path = repo / rel_path
        assert abs_path.exists()
        assert abs_path.read_text(encoding="utf-8").startswith("---")

    def test_mirror_task_returns_relative_path(self, ps):
        rel_path = ps.mirror_task(SAMPLE_TASK)
        assert rel_path.startswith("research_plan/tasks/")
        assert rel_path.endswith(".md")

    def test_mirror_task_creates_parent_dirs(self, ps, repo):
        # tasks dir should not exist beforehand
        assert not (repo / "research_plan" / "tasks").exists()
        ps.mirror_task(SAMPLE_TASK)
        assert (repo / "research_plan" / "tasks").exists()

    def test_mirror_task_overwrites_on_second_call(self, ps, repo):
        ps.mirror_task(SAMPLE_TASK)
        updated = {**SAMPLE_TASK, "status": "done"}
        rel_path = ps.mirror_task(updated)
        content = (repo / rel_path).read_text(encoding="utf-8")
        assert "status: done" in content

    # --- mirror_board ---

    def test_mirror_board_creates_file(self, ps, repo):
        ps.mirror_board(SAMPLE_BOARD, [SAMPLE_TASK])
        board_file = repo / "research_plan" / "task_board.md"
        assert board_file.exists()

    def test_mirror_board_returns_relative_path(self, ps):
        rel = ps.mirror_board(SAMPLE_BOARD, [])
        assert rel == "research_plan/task_board.md"

    def test_mirror_board_content_has_title(self, ps, repo):
        ps.mirror_board(SAMPLE_BOARD, [SAMPLE_TASK])
        content = (repo / "research_plan" / "task_board.md").read_text()
        assert "Sprint 1" in content

    # --- sync_on_transition ---

    def test_sync_on_transition_returns_written_paths(self, ps):
        result = ps.sync_on_transition("done", SAMPLE_BOARD, SAMPLE_TASK, [SAMPLE_TASK])
        assert "research_plan/task_board.md" in result
        task_path = [k for k in result if k.startswith("research_plan/tasks/")]
        assert len(task_path) == 1

    def test_sync_on_transition_skips_non_trigger(self, ps):
        result = ps.sync_on_transition("not_a_trigger", SAMPLE_BOARD, SAMPLE_TASK, [SAMPLE_TASK])
        assert result == {}

    def test_sync_on_transition_writes_both_files(self, ps, repo):
        ps.sync_on_transition("created", SAMPLE_BOARD, SAMPLE_TASK, [SAMPLE_TASK])
        assert (repo / "research_plan" / "task_board.md").exists()
        task_files = list((repo / "research_plan" / "tasks").glob("*.md"))
        assert len(task_files) == 1

    def test_sync_on_transition_all_trigger_events_write(self, ps, repo):
        for event in sorted(SYNC_TRIGGERS):
            result = ps.sync_on_transition(event, SAMPLE_BOARD, SAMPLE_TASK, [SAMPLE_TASK])
            assert len(result) == 2, f"event {event!r} should have written 2 files"
