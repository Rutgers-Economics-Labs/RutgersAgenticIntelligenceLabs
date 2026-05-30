from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.planner_harness import (
    PlannerHarness,
    build_local_project_record,
    format_planner_result,
)


def test_build_local_project_record(tmp_path: Path):
    (tmp_path / "rail.yaml").write_text(
        """
version: 1
project:
  name: "Test Project"
  slug: "test-project"
  default_branch: "main"
paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"
hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"
agents:
  roles_dir: "agents"
  default_runner: "codex_cli"
  sequential_execution: true
  approval_required_for_write_runs: true
  planner_thread_mode: "project"
  default_planner_role: "planner"
frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
""".strip(),
        encoding="utf-8",
    )
    project = build_local_project_record(tmp_path, git_repo_url="https://github.com/example/repo")
    assert project["name"] == "Test Project"
    assert project["slug"] == "test-project"
    assert project["defaultBranch"] == "main"
    assert project["gitRepoUrl"] == "https://github.com/example/repo"
    assert project["localRepoPath"] == str(tmp_path.resolve())


def test_planner_harness_tracks_history(monkeypatch):
    async def _fake_run_planner_turn(**kwargs):
        return {
            "threadId": "planner",
            "assistantMessage": "Planned next step.",
            "messages": [],
            "tasks": [{"_id": "task-1", "title": "Do work", "status": "ready", "agentRole": "data"}],
        }

    monkeypatch.setattr("app.services.planner_harness._run_planner_turn", _fake_run_planner_turn)

    harness = PlannerHarness(project={"_id": "p1", "name": "P", "slug": "p", "localRepoPath": "/tmp"})
    result = asyncio.run(harness.ask("figure out the next step"))

    assert result["assistantMessage"] == "Planned next step."
    assert harness.history == [
        {"role": "user", "content": "figure out the next step"},
        {"role": "assistant", "content": "Planned next step."},
    ]


def test_planner_harness_from_project_slug_uses_repo_first_resolution(monkeypatch):
    async def _resolve_project_reference(project_ref: str | None):
        assert project_ref == "demo-project"
        return {
            "_id": "local:demo-project",
            "name": "Demo Project",
            "slug": "demo-project",
            "localRepoPath": "/tmp/demo-project",
        }

    monkeypatch.setattr("app.services.planner_harness.planner_service.resolve_project_reference", _resolve_project_reference)

    harness = asyncio.run(PlannerHarness.from_project_slug("demo-project", persist=False))

    assert harness.project["slug"] == "demo-project"
    assert harness.persist is False


def test_format_planner_result():
    output = format_planner_result(
        {
            "assistantMessage": "Here is the plan.",
            "tasks": [
                {"title": "Task A", "status": "ready", "agentRole": "research"},
                {"title": "Task B", "status": "running", "agentRole": "data"},
            ],
        }
    )
    assert "Here is the plan." in output
    assert "- [ready] (research) Task A" in output
    assert "- [running] (data) Task B" in output
