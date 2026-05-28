import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.asyncio


def _project_query_response(project: dict) -> httpx.Response:
    return httpx.Response(200, json={"value": project})


async def test_publish_route_batches_files_into_single_commit(client, convex_mock):
    project = {
        "_id": "project-1",
        "slug": "sad",
        "github": "Rutgers-Economics-Labs/RAIL-sad",
        "defaultBranch": "main",
    }
    convex_mock.post("/api/query").mock(return_value=_project_query_response(project))
    convex_mock.post("/api/mutation").mock(return_value=httpx.Response(200, json={"value": {}}))

    # configs/ is no longer in the publish-allow list — only .ontology/ and
    # the other DEFAULT_REPO_PUBLISH_PREFIXES are admissible. Batch two
    # .ontology/ files to verify the multi-file → single-commit path.
    with patch("app.routers.github.github_service.commit_files", new=AsyncMock(return_value={
        "commit_sha": "abc123",
        "branch": "main",
        "changed": True,
        "files": [
            {"path": ".ontology/sources/census_states.yaml", "changed": True},
            {"path": ".ontology/pipelines/census_states.yaml", "changed": True},
        ],
    })) as commit_mock:
        resp = await client.post("/api/v1/github/publish", json={
            "project_slug": "sad",
            "strategy": "direct_commit",
            "files": [
                {"path": ".ontology/sources/census_states.yaml", "content": "name: census_states\n"},
                {"path": ".ontology/pipelines/census_states.yaml", "content": "ontology: core\nsteps: []\n"},
            ],
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["commit_sha"] == "abc123"
    assert body["published"] == 2
    commit_mock.assert_awaited_once()


async def test_sync_repo_changes_prefers_current_layout_and_updates_manifest():
    from app.routers.github import _sync_repo_changes

    project = {"_id": "project-1", "slug": "sad", "pipelineConfigSlug": "nj-hydration"}
    async def get_file(_repo: str, path: str, ref: str = "after") -> str:
        if path == "rail.yaml":
            return "version: 1\nproject:\n  name: NJ Data\n  slug: sad\n  default_branch: main\nhydration:\n  ontology_file: .ontology/ontologies/core.yaml\n  sources_dir: .ontology/sources\n  pipelines_dir: .ontology/pipelines\n  default_pipeline: nj-hydration\n  linked_sources:\n    - census_states\nagents:\n  roles_dir: agents\n  default_runner: codex_cli\n  sequential_execution: true\n  approval_required_for_write_runs: true\n  planner_thread_mode: project\n  default_planner_role: planner\nfrontend:\n  topic_index_mode: filesystem\n  artifact_index_mode: filesystem\n"
        return "name: census_states\n"

    mutation = AsyncMock()
    async def _query(path: str, payload: dict):
        if path == "configs:getApi":
            return None
        if path == "projects:get":
            return {"_id": "project-1", "slug": "sad", "pipelineConfigSlug": "nj-hydration"}
        raise AssertionError((path, payload))

    with patch("app.routers.github.github_service.list_changed_files", new=AsyncMock(return_value=[
        "configs/apis/census_states.yaml",
        ".ontology/sources/census_states.yaml",
        "rail.yaml",
    ])), patch("app.routers.github.github_service.get_file", new=get_file), patch("app.routers.github.convex.query", new=_query), patch("app.routers.github.convex.mutation", new=mutation), patch("app.routers.github._trigger_job", new=AsyncMock(), create=True):
        await _sync_repo_changes("Rutgers-Economics-Labs/RAIL-sad", "before", "after", project)

    calls = mutation.await_args_list
    assert any(call.args[0] == "projects:update" for call in calls)
    assert any(call.args[0] == "configs:upsertApi" for call in calls)
    api_calls = [call for call in calls if call.args[0] == "configs:upsertApi"]
    assert len(api_calls) == 1


async def test_sync_repo_changes_skips_binary_watched_paths():
    from app.routers.github import _sync_repo_changes

    project = {"_id": "project-1", "slug": "sad", "pipelineConfigSlug": "nj-hydration"}
    requested_paths: list[str] = []

    async def get_file(_repo: str, path: str, ref: str = "after") -> str:
        requested_paths.append(path)
        if path == "rail.yaml":
            return "version: 1\nproject:\n  name: NJ Data\n  slug: sad\n"
        return "name: census_states\n"

    mutation = AsyncMock()
    async def _query(path: str, payload: dict):
        if path == "configs:getApi":
            return None
        if path == "projects:get":
            return {"_id": "project-1", "slug": "sad", "pipelineConfigSlug": "nj-hydration"}
        raise AssertionError((path, payload))

    with patch(
        "app.routers.github.github_service.list_changed_files",
        new=AsyncMock(
            return_value=[
                ".ontology/onto.duckdb",
                ".ontology/sources/census_states.yaml",
                "rail.yaml",
            ]
        ),
    ), patch("app.routers.github.github_service.get_file", new=get_file), patch(
        "app.routers.github.convex.query", new=_query
    ), patch("app.routers.github.convex.mutation", new=mutation), patch(
        "app.routers.github._trigger_job", new=AsyncMock(), create=True
    ):
        await _sync_repo_changes("Rutgers-Economics-Labs/RAIL-sad", "before", "after", project)

    assert ".ontology/onto.duckdb" not in requested_paths
    assert ".ontology/sources/census_states.yaml" in requested_paths
    assert "rail.yaml" in requested_paths


async def test_github_status_uses_repo_first_local_project(client, convex_mock, monkeypatch):
    from app.routers import github as github_router

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in {"projects:getBySlug", "projects:get"}:
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return {
            "_id": "local:demo-project",
            "slug": "demo-project",
            "github": "Rutgers-Economics-Labs/demo-project",
            "defaultBranch": "main",
            "githubSyncMode": "manual",
            "localRepoPath": "/tmp/demo-project",
        }

    convex_mock.post("/api/query").mock(side_effect=_query)
    monkeypatch.setattr(github_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    resp = await client.get("/api/v1/github/status/demo-project")

    assert resp.status_code == 200
    assert resp.json()["github"] == "Rutgers-Economics-Labs/demo-project"


async def test_link_github_persists_repo_only_manifest(client, convex_mock, monkeypatch, tmp_path):
    from app.routers import github as github_router
    from rail.bootstrap import bootstrap_future_project
    from rail.manifest import load_manifest

    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    project = {
        "_id": "local:demo-project",
        "slug": "demo-project",
        "name": "Demo Project",
        "localRepoPath": str(root),
    }

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in {"projects:getBySlug", "projects:get"}:
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    async def _get_project_by_slug(slug: str):
        if slug != "demo-project":
            raise ValueError(slug)
        return project

    convex_mock.post("/api/query").mock(side_effect=_query)
    monkeypatch.setattr(github_router.planner_service, "get_project_by_slug", _get_project_by_slug)
    monkeypatch.setattr(github_router.planner_service, "project_root_from_record", lambda record: Path(record["localRepoPath"]))
    monkeypatch.setattr(github_router.github_service, "get_installation_token", AsyncMock(return_value="token"))

    resp = await client.post(
        "/api/v1/github/link",
        json={"project_slug": "demo-project", "github_repo": "Rutgers-Economics-Labs/demo-project"},
    )

    manifest = load_manifest(root)

    assert resp.status_code == 200
    assert resp.json() == {"linked": True, "repo": "Rutgers-Economics-Labs/demo-project"}
    assert manifest.project.git_repo_url == "https://github.com/Rutgers-Economics-Labs/demo-project"


async def test_persist_github_project_patch_prefers_repo_first_refresh(monkeypatch):
    from app.routers import github as github_router

    project = {
        "_id": "project-1",
        "slug": "demo-project",
        "github": "Rutgers-Economics-Labs/demo-project",
    }

    mutation = AsyncMock(return_value={"ok": True})
    convex_query = AsyncMock(side_effect=AssertionError("convex refresh should not be needed"))
    repo_first_refresh = AsyncMock(
        return_value={
            "_id": "project-1",
            "slug": "demo-project",
            "github": "Rutgers-Economics-Labs/demo-project",
            "defaultBranch": "main",
        }
    )

    monkeypatch.setattr(github_router.convex, "mutation", mutation)
    monkeypatch.setattr(github_router.convex, "query", convex_query)
    monkeypatch.setattr(github_router.planner_service, "get_project_by_slug", repo_first_refresh)

    refreshed = await github_router._persist_github_project_patch(project, {"defaultBranch": "main"})

    mutation.assert_awaited_once_with("projects:update", {"slug": "demo-project", "defaultBranch": "main"})
    repo_first_refresh.assert_awaited_once_with("demo-project")
    assert refreshed["defaultBranch"] == "main"


async def test_github_sync_uses_repo_first_local_project_link(client, monkeypatch):
    from app.routers import github as github_router

    project = {
        "_id": "local:demo-project",
        "slug": "demo-project",
        "pipelineConfigSlug": None,
        "localRepoPath": "/tmp/demo-project",
    }

    monkeypatch.setattr(github_router.github_service, "verify_webhook", lambda body, signature: True)
    monkeypatch.setattr(github_router.planner_service, "get_project_by_github_repo", AsyncMock(return_value=project))
    monkeypatch.setattr(github_router, "_sync_repo_changes", AsyncMock())

    resp = await client.post(
        "/api/v1/github/sync",
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=test",
        },
        content=json.dumps(
            {
                "repository": {"full_name": "Rutgers-Economics-Labs/demo-project"},
                "before": "oldsha",
                "after": "newsha",
            }
        ),
    )

    assert resp.status_code == 200
    assert resp.json() == {"synced": True, "project": "demo-project"}


async def test_sync_repo_changes_persists_local_project_manifest(monkeypatch, tmp_path):
    from app.routers import github as github_router
    from rail.bootstrap import bootstrap_future_project
    from rail.manifest import load_manifest

    root = bootstrap_future_project(tmp_path, name="Demo Project", slug="demo-project")
    project = {
        "_id": "local:demo-project",
        "slug": "demo-project",
        "name": "Demo Project",
        "localRepoPath": str(root),
        "pipelineConfigSlug": None,
    }

    async def get_file(_repo: str, path: str, ref: str = "after") -> str:
        if path == "rail.yaml":
            return (
                "version: 1\n"
                "project:\n"
                "  name: Demo Project\n"
                "  slug: demo-project\n"
                "  description: Synced from GitHub\n"
                "  default_branch: main\n"
            )
        raise AssertionError(path)

    monkeypatch.setattr(
        github_router.github_service,
        "list_changed_files",
        AsyncMock(return_value=["rail.yaml"]),
    )
    monkeypatch.setattr(github_router.github_service, "get_file", get_file)
    monkeypatch.setattr(github_router.convex, "query", AsyncMock())
    mutation = AsyncMock()
    monkeypatch.setattr(github_router.convex, "mutation", mutation)
    monkeypatch.setattr(github_router.planner_service, "project_root_from_record", lambda record: Path(record["localRepoPath"]))
    monkeypatch.setattr(github_router.planner_service, "get_project_by_slug", AsyncMock(return_value={**project, "description": "Synced from GitHub"}))

    await github_router._sync_repo_changes("Rutgers-Economics-Labs/demo-project", "before", "after", project)

    manifest = load_manifest(root)
    assert manifest.project.description == "Synced from GitHub"
    mutation.assert_not_awaited()


async def test_sync_repo_changes_triggers_pipeline_by_slug_for_repo_only_project(monkeypatch):
    from app.routers import github as github_router

    project = {
        "_id": "local:demo-project",
        "slug": "demo-project",
        "pipelineConfigSlug": "demo-pipeline",
        "localRepoPath": "/tmp/demo-project",
    }

    async def get_file(_repo: str, path: str, ref: str = "after") -> str:
        assert path == ".ontology/pipelines/demo-pipeline.yaml"
        return "ontology: .ontology/ontology.yaml\nsteps: []\n"

    triggered: list[tuple[str, str | None]] = []

    async def _trigger_job(pipeline_slug: str, project_id: str | None = None):
        triggered.append((pipeline_slug, project_id))
        return {"jobId": "job-123"}

    monkeypatch.setattr(
        github_router.github_service,
        "list_changed_files",
        AsyncMock(return_value=[".ontology/pipelines/demo-pipeline.yaml"]),
    )
    monkeypatch.setattr(github_router.github_service, "get_file", get_file)
    monkeypatch.setattr(github_router.convex, "query", AsyncMock(return_value=None))
    monkeypatch.setattr(github_router.convex, "mutation", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr("app.routers.jobs._trigger_job", _trigger_job)

    await github_router._sync_repo_changes("Rutgers-Economics-Labs/demo-project", "before", "after", project)

    assert triggered == [("demo-pipeline", "demo-project")]
