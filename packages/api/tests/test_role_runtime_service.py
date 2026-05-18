from __future__ import annotations

from pathlib import Path

from app.services.role_runtime_service import load_role_runtime_config, read_project_skills, summarize_role_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bootstrap_manifest(tmp_path: Path) -> None:
    _write(
        tmp_path / "rail.yaml",
        """
version: 1
project:
  name: Demo
  slug: demo
  default_branch: main
paths:
  ontology_root: .ontology
  topics_root: topics
  specs_root: specs
  plan_root: research_plan
  agents_root: agents
  skills_root: skills
  artifacts_root: artifacts
hydration:
  ontology_file: .ontology/ontology.yaml
  sources_dir: .ontology/sources
  pipelines_dir: .ontology/pipelines
  transforms_dir: .ontology/transforms
  hydration_mode: full
agents:
  roles_dir: agents
  default_runner: codex_cli
  sequential_execution: true
  approval_required_for_write_runs: true
  planner_thread_mode: project
  default_planner_role: planner
frontend:
  topic_index_mode: filesystem
  artifact_index_mode: filesystem
  show_repo_tree: true
  show_task_board_snapshot: true
  default_home_view: project_home
""".strip(),
    )


def test_load_role_runtime_config_reads_runner_and_skills(tmp_path: Path):
    _bootstrap_manifest(tmp_path)
    _write(tmp_path / "agents" / "prompts" / "planner.md", "# planner prompt")
    _write(tmp_path / "agents" / "checklists" / "planner.md", "- verify")
    _write(
        tmp_path / "agents" / "planner.yaml",
        """
role: planner
label: Planner Agent
purpose: Coordinate work.
runner:
  default: gemini_cli
  approval_required: true
  bash_access: true
threading:
  mode: project_scoped
permissions:
  read: [skills, specs]
  write: [research_plan, specs, agents]
  deny: []
secrets:
  allow: []
skills:
  allow_use: true
tools:
  allow: [read_repo]
  deny: []
prompts:
  system: agents/prompts/planner.md
  checklist: agents/checklists/planner.md
completion:
  requires: [task_documented]
""".strip(),
    )
    _write(tmp_path / "skills" / "repo-contract.md", "# Repo Contract")

    project = {"localRepoPath": str(tmp_path), "slug": "demo", "name": "Demo"}
    config = load_role_runtime_config(project, "planner")

    assert config.policy.runner.default == "gemini_cli"
    assert config.policy.runner.bash_access is True
    assert config.policy.skills.allow_use is True
    assert "planner prompt" in config.system_prompt
    assert summarize_role_config(config)["runner"]["default"] == "gemini_cli"

    skills = read_project_skills(project)
    assert skills[0]["path"] == "skills/repo-contract.md"


def test_load_role_runtime_config_normalizes_legacy_role_alias_from_yaml(tmp_path: Path):
    _bootstrap_manifest(tmp_path)
    _write(tmp_path / "agents" / "prompts" / "coding.md", "# coding prompt")
    _write(tmp_path / "agents" / "checklists" / "coding.md", "- ship")
    _write(
        tmp_path / "agents" / "coding.yaml",
        """
role: developer
label: Coding Agent
purpose: Build features.
runner:
  default: codex_cli
  approval_required: true
  bash_access: true
threading:
  mode: task_scoped
permissions:
  read: [specs]
  write: [packages]
  deny: []
secrets:
  allow: []
skills:
  allow_use: true
tools:
  allow: [read_repo]
  deny: []
prompts:
  system: agents/prompts/coding.md
  checklist: agents/checklists/coding.md
completion:
  requires: [task_documented]
""".strip(),
    )

    project = {"localRepoPath": str(tmp_path), "slug": "demo", "name": "Demo"}
    config = load_role_runtime_config(project, "coding")

    assert config.role == "coding"
    assert summarize_role_config(config)["role"] == "coding"
