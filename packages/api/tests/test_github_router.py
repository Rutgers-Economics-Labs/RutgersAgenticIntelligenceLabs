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

    with patch("app.routers.github.github_service.commit_files", new=AsyncMock(return_value={
        "commit_sha": "abc123",
        "branch": "main",
        "changed": True,
        "files": [
            {"path": ".ontology/sources/census_states.yaml", "changed": True},
            {"path": "configs/apis/census_states.yaml", "changed": True},
        ],
    })) as commit_mock:
        resp = await client.post("/api/v1/github/publish", json={
            "project_slug": "sad",
            "strategy": "direct_commit",
            "files": [
                {"path": ".ontology/sources/census_states.yaml", "content": "name: census_states\n"},
                {"path": "configs/apis/census_states.yaml", "content": "name: census_states\n"},
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
            return "version: 1\nproject:\n  name: NJ Data\n  slug: sad\n  default_branch: main\nhydration:\n  ontology_file: .ontology/ontologies/core.yaml\n  sources_dir: .ontology/sources\n  pipelines_dir: .ontology/pipelines\n  default_pipeline: nj-hydration\n  linked_sources:\n    - census_states\nagents:\n  roles_dir: agents\n  default_runner: jules\n  sequential_execution: true\n  approval_required_for_write_runs: true\n  planner_thread_mode: project\n  default_planner_role: planner\nfrontend:\n  topic_index_mode: filesystem\n  artifact_index_mode: filesystem\n"
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
