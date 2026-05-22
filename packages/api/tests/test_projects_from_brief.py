from unittest.mock import AsyncMock, patch

import pytest
import yaml


pytestmark = pytest.mark.asyncio


async def test_preview_from_brief_returns_preview(client):
    response = await client.post("/api/v1/projects/from-brief/preview", json={"brief": "Research objective: estimate housing affordability trends using ACS and FRED."})
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["slug"]
    assert "repoFiles" in body
    assert "sourceCandidates" in body


async def test_create_from_brief_writes_project_and_skips_hydration(client, tmp_path):
    preview = {
        "briefHash": "abc123",
        "project": {"name": "Grid Costs", "slug": "grid-costs", "description": "Research kickoff", "approach": "ontology-first"},
        "researchGraph": {"title": "Grid Costs", "objective": "Understand costs", "methods": ["regression"], "deliverables": ["report"]},
        "sourceCandidates": [
            {
                "slug": "grid-costs-fred-unrate",
                "name": "Unemployment Rate",
                "provider": "fred",
                "externalId": "UNRATE",
                "description": "Test source",
                "readiness": "ready",
                "reason": "Registry match",
                "configKind": "api",
                "content": "name: grid-costs-fred-unrate\ntype: api\nurl: https://api.stlouisfed.org/fred/series/observations\nresponse_format: json\nfields:\n  - source: observations[].date\n    alias: date\n  - source: observations[].value\n    alias: value\n",
            }
        ],
        "ontology": {
            "name": "Grid Costs Ontology",
            "slug": "grid-costs-ontology",
            "content": "uri: http://rail.rutgers.edu/ontology/grid-costs\nclasses:\n  - name: Observation\ndata_properties: []\nobject_properties: []\n",
            "parsedSpec": {"uri": "http://rail.rutgers.edu/ontology/grid-costs", "classes": [{"name": "Observation"}], "data_properties": [], "object_properties": []},
        },
        "pipeline": {
            "name": "Grid Costs Pipeline",
            "slug": "grid-costs-pipeline",
            "content": "name: grid-costs-pipeline\nontology: grid-costs-ontology\nsteps:\n  - name: load_grid_costs_fred_unrate\n    api: grid-costs-fred-unrate\n    class: Observation\n    uri: http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}\n",
            "parsedSpec": {"name": "grid-costs-pipeline", "ontology": "grid-costs-ontology", "steps": [{"name": "load_grid_costs_fred_unrate", "api": "grid-costs-fred-unrate", "class": "Observation", "uri": "http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}"}]},
            "referencedApiSlugs": ["grid-costs-fred-unrate"],
        },
        "repoFiles": [
            {"path": "specs/research_question.yaml", "content": "title: Grid Costs\n"},
            {"path": "research_plan/graph/summary.yaml", "content": "title: Grid Costs\n"},
        ],
        "readiness": {"ready": 1, "draft_for_review": 0, "missing_auth_or_manual": 0},
    }
    project_record = {
        "_id": "project-1",
        "name": "Grid Costs",
        "slug": "grid-costs",
        "description": "Research kickoff",
        "status": "ready_for_hydration_review",
        "localRepoPath": str(tmp_path / "grid-costs"),
        "githubSyncMode": "manual",
    }
    mutation = AsyncMock(side_effect=["project-1", "api-id", "ontology-id", "pipeline-id", None])
    query = AsyncMock(side_effect=[None, project_record, project_record])

    with patch("app.routers.projects.build_preview", new=AsyncMock(return_value=preview)), \
         patch("app.routers.projects.convex.mutation", new=mutation), \
        patch("app.routers.projects.convex.query", new=query), \
        patch("app.routers.projects._git_init", return_value=None), \
        patch("app.routers.projects._git_create_initial_commit", return_value="deadbeef"), \
        patch("app.routers.projects.GitHubService.create_repo", new=AsyncMock(return_value={"full_name": "Rutgers-Economics-Labs/RAIL-grid-costs"})), \
        patch("app.routers.projects.GitHubService.commit_files", new=AsyncMock(return_value={"sha": "deadbeef"})), \
        patch("app.routers.projects.planner_service.ensure_planner_thread", new=AsyncMock(return_value="planner")), \
        patch("app.routers.projects.planner_service.ensure_main_board", new=AsyncMock(return_value={"_id": "board-1"})), \
        patch("app.routers.projects.planner_service.append_planner_message", new=AsyncMock()), \
        patch("app.routers.projects.planner_service.sync_planner_files", new=AsyncMock()), \
        patch("app.routers.projects.should_auto_publish", new=AsyncMock(return_value=False)):
        response = await client.post("/api/v1/projects/from-brief/create", json={
            "brief": "Research brief",
            "targetDir": str(tmp_path / "grid-costs"),
        })

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["slug"] == "grid-costs"
    assert body["hydrationReady"] is False
    assert body["nextAction"].lower().startswith("review")


async def test_git_create_initial_commit_creates_head_on_requested_branch(tmp_path):
    from app.routers import projects as projects_router

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")

    projects_router._git_init(repo, default_branch="main")
    sha = projects_router._git_create_initial_commit(repo, default_branch="main", message="initial")

    assert sha
    branch = __import__("subprocess").run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch.stdout.strip() == "main"


async def test_create_from_brief_writes_extended_manifest_contract(client, tmp_path):
    preview = {
        "briefHash": "abc123",
        "project": {"name": "Grid Costs", "slug": "grid-costs", "description": "Research kickoff", "approach": "ontology-first"},
        "researchGraph": {"title": "Grid Costs", "objective": "Understand costs", "methods": ["regression"], "deliverables": ["report"]},
        "sourceCandidates": [],
        "ontology": {
            "name": "Grid Costs Ontology",
            "slug": "grid-costs-ontology",
            "content": "uri: http://rail.rutgers.edu/ontology/grid-costs\nclasses:\n  - name: Observation\ndata_properties: []\nobject_properties: []\n",
            "parsedSpec": {"uri": "http://rail.rutgers.edu/ontology/grid-costs", "classes": [{"name": "Observation"}], "data_properties": [], "object_properties": []},
        },
        "pipeline": {
            "name": "Grid Costs Pipeline",
            "slug": "grid-costs-pipeline",
            "content": "name: grid-costs-pipeline\nontology: grid-costs-ontology\nsteps:\n  - name: noop\n    class: Observation\n    uri: http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}\n",
            "parsedSpec": {"name": "grid-costs-pipeline", "ontology": "grid-costs-ontology", "steps": [{"name": "noop", "class": "Observation", "uri": "http://rail.rutgers.edu/ontology/grid-costs#Observation_{id}"}]},
            "referencedApiSlugs": [],
        },
        "repoFiles": [
            {"path": "specs/research_question.yaml", "content": "title: Grid Costs\n"},
            {"path": "research_plan/graph/summary.yaml", "content": "title: Grid Costs\n"},
        ],
        "readiness": {"ready": 0, "draft_for_review": 0, "missing_auth_or_manual": 0},
    }
    project_record = {
        "_id": "project-1",
        "name": "Grid Costs",
        "slug": "grid-costs",
        "description": "Research kickoff",
        "status": "ready_for_hydration_review",
        "localRepoPath": str(tmp_path / "grid-costs"),
        "githubSyncMode": "manual",
    }
    mutation = AsyncMock(side_effect=["project-1", "ontology-id", "pipeline-id", None])
    query = AsyncMock(side_effect=[None, project_record, project_record])

    with patch("app.routers.projects.build_preview", new=AsyncMock(return_value=preview)), \
         patch("app.routers.projects.convex.mutation", new=mutation), \
         patch("app.routers.projects.convex.query", new=query), \
         patch("app.routers.projects._git_init", return_value=None), \
         patch("app.routers.projects._git_create_initial_commit", return_value="deadbeef"), \
         patch("app.routers.projects.GitHubService.create_repo", new=AsyncMock(return_value={"full_name": "Rutgers-Economics-Labs/RAIL-grid-costs"})), \
         patch("app.routers.projects.GitHubService.commit_files", new=AsyncMock(return_value={"sha": "deadbeef"})), \
         patch("app.routers.projects.planner_service.ensure_planner_thread", new=AsyncMock(return_value="planner")), \
         patch("app.routers.projects.planner_service.ensure_main_board", new=AsyncMock(return_value={"_id": "board-1"})), \
         patch("app.routers.projects.planner_service.append_planner_message", new=AsyncMock()), \
         patch("app.routers.projects.planner_service.sync_planner_files", new=AsyncMock()), \
         patch("app.routers.projects.should_auto_publish", new=AsyncMock(return_value=False)):
        response = await client.post("/api/v1/projects/from-brief/create", json={
            "brief": "Research brief",
            "targetDir": str(tmp_path / "grid-costs"),
        })

    assert response.status_code == 200
    manifest = yaml.safe_load((tmp_path / "grid-costs" / "rail.yaml").read_text(encoding="utf-8"))
    assert manifest["project"]["mode"] == "ontology_first"
    assert manifest["repo_contract"]["source_of_truth"] == "git"
    assert manifest["research"]["brief_path"] == "topics/brief.md"
    assert manifest["planner"]["task_root"] == "research_plan/tasks"
    assert manifest["verification"]["deterministic_command"] == "scripts/run-verification.sh"
    assert "hydrated" in manifest["lifecycle"]["phases"]


async def test_future_bootstrap_auto_creates_and_links_github_repo(client, tmp_path):
    project_record = {
        "_id": "project-9",
        "name": "Bootstrap Grid Costs",
        "slug": "bootstrap-grid-costs",
        "description": "Future RAIL project",
        "localRepoPath": str(tmp_path / "bootstrap-grid-costs"),
        "gitRepoUrl": "https://github.com/Rutgers-Economics-Labs/RAIL-bootstrap-grid-costs",
        "github": "Rutgers-Economics-Labs/RAIL-bootstrap-grid-costs",
    }
    mutation = AsyncMock(return_value="project-9")
    query = AsyncMock(return_value=project_record)

    with patch("app.routers.projects.convex.mutation", new=mutation), \
         patch("app.routers.projects.convex.query", new=query), \
         patch("app.routers.projects.GitHubService.create_repo", new=AsyncMock(return_value={"full_name": "Rutgers-Economics-Labs/RAIL-bootstrap-grid-costs"})), \
         patch("app.routers.projects.GitHubService.commit_files", new=AsyncMock(return_value={"commit_sha": "abc123", "branch": "main", "changed": True, "files": []})), \
         patch("app.routers.projects.planner_service.ensure_planner_thread", new=AsyncMock(return_value="planner")), \
         patch("app.routers.projects.planner_service.ensure_main_board", new=AsyncMock(return_value={"_id": "board-1"})), \
         patch("app.routers.projects.planner_service.append_planner_message", new=AsyncMock()), \
         patch("app.routers.projects.planner_service.sync_planner_files", new=AsyncMock()):
        response = await client.post(
            "/api/v1/projects/future/bootstrap",
            json={
                "name": "Bootstrap Grid Costs",
                "slug": "bootstrap-grid-costs",
                "targetDir": str(tmp_path / "bootstrap-grid-costs"),
            },
        )

    assert response.status_code == 200
    payload = mutation.await_args_list[0].args[1]
    assert payload["gitRepoUrl"] == "https://github.com/Rutgers-Economics-Labs/RAIL-bootstrap-grid-costs"
    assert payload["github"] == "Rutgers-Economics-Labs/RAIL-bootstrap-grid-costs"
