from __future__ import annotations

import asyncio


def test_get_project_by_slug_falls_back_to_local_repo_manifest(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    project_root = tmp_path / "generated_projects" / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  description: Local fallback project
  default_branch: main
hydration:
  default_pipeline: baseline-pipeline
  linked_sources:
    - census
autonomy:
  mode: assisted
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def _query(path: str, payload: dict):
        assert path == "projects:getBySlug"
        return None

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_slug("demo-project"))

    assert project["slug"] == "demo-project"
    assert project["name"] == "Demo Project"
    assert project["localRepoPath"] == str(project_root.resolve())
    assert project["apiConfigSlugs"] == ["census"]
    assert project["pipelineConfigSlug"] == "baseline-pipeline"
    assert project["githubSyncMode"] == "assisted"


def test_get_project_by_slug_prefers_convex_record(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    convex_project = {
        "_id": "project-1",
        "name": "Convex Project",
        "slug": "demo-project",
        "localRepoPath": "/tmp/from-convex",
    }

    async def _query(path: str, payload: dict):
        assert path == "projects:getBySlug"
        return convex_project

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_slug("demo-project"))

    assert project is convex_project


def test_get_project_by_slug_merges_repo_truth_over_convex_metadata(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    project_root = tmp_path / "generated_projects" / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "rail.yaml").write_text(
        """
project:
  name: Repo Truth Name
  slug: demo-project
  description: Repo-backed description
  default_branch: trunk
  git_repo_url: https://github.com/Rutgers-Economics-Labs/demo-project
  agent_model: gpt-5
hydration:
  default_pipeline: repo-pipeline
  linked_sources:
    - repo-source
autonomy:
  mode: autonomous
""".strip()
        + "\n",
        encoding="utf-8",
    )

    convex_project = {
        "_id": "project-1",
        "name": "Convex Project",
        "slug": "demo-project",
        "description": "stale convex description",
        "localRepoPath": "/tmp/from-convex",
        "defaultBranch": "main",
        "agentModel": "old-model",
    }

    async def _query(path: str, payload: dict):
        assert path == "projects:getBySlug"
        return convex_project

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_slug("demo-project"))

    assert project["_id"] == "project-1"
    assert project["name"] == "Repo Truth Name"
    assert project["description"] == "Repo-backed description"
    assert project["localRepoPath"] == str(project_root.resolve())
    assert project["defaultBranch"] == "trunk"
    assert project["gitRepoUrl"] == "https://github.com/Rutgers-Economics-Labs/demo-project"
    assert project["github"] == "Rutgers-Economics-Labs/demo-project"
    assert project["agentModel"] == "gpt-5"
    assert project["pipelineConfigSlug"] == "repo-pipeline"
    assert project["apiConfigSlugs"] == ["repo-source"]
    assert project["githubSyncMode"] == "autonomous"


def test_get_project_by_slug_uses_repo_root_generated_projects_by_default(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    fake_module_path = tmp_path / "repo" / "packages" / "api" / "app" / "services" / "planner_service.py"
    fake_module_path.parent.mkdir(parents=True, exist_ok=True)
    fake_module_path.write_text("# stub\n", encoding="utf-8")

    project_root = tmp_path / "repo" / "generated_projects" / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "rail.yaml").write_text(
        "project:\n  name: Demo Project\n  slug: demo-project\n",
        encoding="utf-8",
    )

    async def _query(path: str, payload: dict):
        assert path == "projects:getBySlug"
        return None

    monkeypatch.delenv("RAIL_PROJECTS_DIR", raising=False)
    monkeypatch.setattr(planner_service, "__file__", str(fake_module_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_slug("demo-project"))

    assert project["localRepoPath"] == str(project_root.resolve())


def test_get_project_by_github_repo_falls_back_to_local_repo_manifest(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    project_root = tmp_path / "generated_projects" / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "rail.yaml").write_text(
        """
project:
  name: Demo Project
  slug: demo-project
  git_repo_url: https://github.com/Rutgers-Economics-Labs/demo-project
""".strip()
        + "\n",
        encoding="utf-8",
    )

    async def _query(path: str, payload: dict):
        assert path == "projects:getByGithubRepo"
        return None

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_github_repo("Rutgers-Economics-Labs/demo-project"))

    assert project["slug"] == "demo-project"
    assert project["github"] == "Rutgers-Economics-Labs/demo-project"


def test_get_project_by_github_repo_merges_repo_truth_over_convex_metadata(monkeypatch, tmp_path):
    import app.services.planner_service as planner_service

    project_root = tmp_path / "generated_projects" / "demo-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "rail.yaml").write_text(
        """
project:
  name: Repo Truth Name
  slug: demo-project
  default_branch: trunk
  git_repo_url: https://github.com/Rutgers-Economics-Labs/demo-project
""".strip()
        + "\n",
        encoding="utf-8",
    )

    convex_project = {
        "_id": "project-1",
        "name": "Convex Project",
        "slug": "demo-project",
        "github": "Rutgers-Economics-Labs/demo-project",
        "defaultBranch": "main",
        "localRepoPath": "/tmp/from-convex",
    }

    async def _query(path: str, payload: dict):
        assert path == "projects:getByGithubRepo"
        return convex_project

    monkeypatch.setenv("RAIL_PROJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(planner_service.convex, "query", _query)

    project = asyncio.run(planner_service.get_project_by_github_repo("Rutgers-Economics-Labs/demo-project"))

    assert project["_id"] == "project-1"
    assert project["name"] == "Repo Truth Name"
    assert project["defaultBranch"] == "trunk"
    assert project["localRepoPath"] == str(project_root.resolve())
