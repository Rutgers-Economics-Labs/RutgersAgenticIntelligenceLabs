import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
    query = AsyncMock(side_effect=[
        None,  # existing api config lookup
    ])

    with patch("app.routers.github.github_service.list_changed_files", new=AsyncMock(return_value=[
        "configs/apis/census_states.yaml",
        ".ontology/sources/census_states.yaml",
        "rail.yaml",
    ])), patch("app.routers.github.github_service.get_file", new=get_file), patch("app.routers.github.convex.query", new=query), patch("app.routers.github.convex.mutation", new=mutation), patch("app.routers.github._trigger_job", new=AsyncMock(), create=True):
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
    query = AsyncMock(side_effect=[None])

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
        "app.routers.github.convex.query", new=query
    ), patch("app.routers.github.convex.mutation", new=mutation), patch(
        "app.routers.github._trigger_job", new=AsyncMock(), create=True
    ):
        await _sync_repo_changes("Rutgers-Economics-Labs/RAIL-sad", "before", "after", project)

    assert ".ontology/onto.duckdb" not in requested_paths
    assert ".ontology/sources/census_states.yaml" in requested_paths
    assert "rail.yaml" in requested_paths
