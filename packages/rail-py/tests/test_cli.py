from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail import cli as rail_cli
from rail.client import CloudClient
from rail.local import LocalEngine
from rail.project import Project


MINIMAL_RAIL_YAML = textwrap.dedent(
    """\
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
      default_pipeline: "test_pipeline"
      hydration_mode: "full"

    agents:
      roles_dir: "agents"
      default_runner: "codex_cli"
      sequential_execution: true
      planner_thread_mode: "project"
      default_planner_role: "planner"

    frontend:
      topic_index_mode: "filesystem"
      artifact_index_mode: "filesystem"
    """
)


def test_project_reconcile_uses_cloud_backend_method():
    class _Backend:
        def __init__(self):
            self.calls: list[str] = []

        def reconcile_project(self, slug: str) -> dict:
            self.calls.append(slug)
            return {"status": "ok", "slug": slug}

    backend = _Backend()
    project = Project("demo-project", backend)

    result = project.reconcile()

    assert result == {"status": "ok", "slug": "demo-project"}
    assert backend.calls == ["demo-project"]


def test_get_project_uses_cloud_connect(monkeypatch):
    seen: dict[str, object] = {}

    class _Project:
        pass

    expected = _Project()

    def _fake_connect(*, slug: str, api_url: str | None = None, api_key: str | None = None):
        seen["slug"] = slug
        seen["api_url"] = api_url
        seen["api_key"] = api_key
        return expected

    monkeypatch.setattr(rail_cli.rail, "connect", _fake_connect)

    args = argparse.Namespace(
        local=False,
        path=".",
        project="demo-project",
        api_url="http://127.0.0.1:8000/api/v1",
        api_key="secret-token",
    )

    assert rail_cli._get_project(args) is expected
    assert seen == {
        "slug": "demo-project",
        "api_url": "http://127.0.0.1:8000/api/v1",
        "api_key": "secret-token",
    }


def test_cloud_client_retains_api_key_and_timeout():
    client = CloudClient(
        base_url="http://127.0.0.1:8000/api/v1",
        api_key="secret-token",
        timeout_seconds=45.0,
    )

    assert client.base_url == "http://127.0.0.1:8000/api/v1"
    assert client.api_key == "secret-token"
    assert client.timeout_seconds == 45.0
    assert client.headers == {"Authorization": "Bearer secret-token"}


def test_cmd_reconcile_prints_json(capsys):
    class _Project:
        def reconcile(self) -> dict:
            return {"status": "ok", "updatedTaskIds": ["task-1"]}

    rail_cli.cmd_reconcile(_Project(), argparse.Namespace())

    captured = capsys.readouterr()
    assert '"status": "ok"' in captured.out
    assert '"updatedTaskIds": [' in captured.out


def test_local_engine_reconcile_calls_reconciliation_service(tmp_path: Path, monkeypatch):
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    (tmp_path / ".ontology").mkdir()
    (tmp_path / "topics").mkdir()
    (tmp_path / "specs").mkdir()
    (tmp_path / "research_plan").mkdir()
    (tmp_path / "agents").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "artifacts").mkdir()
    (tmp_path / ".ontology" / "ontology.yaml").write_text(
        "uri: http://test.org/onto.owl\nclasses: []\n", encoding="utf-8"
    )
    (tmp_path / ".ontology" / "sources").mkdir()
    (tmp_path / ".ontology" / "pipelines").mkdir()

    seen: list[dict] = []

    class _ReconciliationService:
        async def reconcile_project_reality(self, project: dict) -> dict:
            seen.append(project)
            return {"hasChanges": True, "persistedControlPlaneSnapshot": {"snapshotVersion": 1}}

    engine = LocalEngine(project_path=str(tmp_path), engine_path=None)
    monkeypatch.setattr(engine, "_reconciliation_service_module", lambda: _ReconciliationService())

    result = engine.reconcile()

    assert result["hasChanges"] is True
    assert result["persistedControlPlaneSnapshot"]["snapshotVersion"] == 1
    assert seen[0]["slug"] == "test-project"
    assert seen[0]["name"] == "Test Project"
    assert seen[0]["localRepoPath"] == str(tmp_path)
