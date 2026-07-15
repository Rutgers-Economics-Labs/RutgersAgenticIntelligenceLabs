from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.krail_runtime.contracts import ProjectHealth, ProjectHealthCheck, ProjectManifest, ProjectRef
from app.main_krail import create_app
from app.projects.registry import RegistryConfig


class FakeRuntime:
    def __init__(self, health: ProjectHealth | None = None) -> None:
        self.health = health or ProjectHealth(
            ok=True,
            checks=[ProjectHealthCheck(name="manifest", ok=True, detail="valid")],
            krail_version="0.2.2",
        )
        self.doctor_calls: list[ProjectRef] = []

    def doctor(self, project: ProjectRef) -> ProjectHealth:
        self.doctor_calls.append(project)
        return self.health

    def manifest(self, project: ProjectRef) -> ProjectManifest:
        return ProjectManifest(
            version=1,
            slug="fixture-project",
            name="Fixture project",
            default_branch="main",
            knowledge_mode="markdown_graph",
            paths={"topics_root": "topics"},
        )


def _git_project(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "rail.yaml").write_text("name: fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "rail.yaml"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
    return path


def _client(tmp_path: Path, runtime: FakeRuntime | None = None) -> TestClient:
    managed = tmp_path / "managed"
    managed.mkdir(exist_ok=True)
    config = RegistryConfig(
        storage_path=tmp_path / "registry.json",
        managed_workspace_root=managed,
        linked_workspace_roots=(tmp_path / "linked",),
    )
    return TestClient(create_app(registry_config=config, runtime=runtime or FakeRuntime()))


def test_register_list_get_health_and_manifest_for_linked_git_project(tmp_path: Path):
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    project = _git_project(linked_root / "fixture")
    runtime = FakeRuntime()
    client = _client(tmp_path, runtime)

    response = client.post(
        "/api/v1/projects",
        json={
            "projectId": "fixture-id",
            "displayName": "Fixture",
            "path": str(project),
            "workspaceMode": "linked_local",
        },
        headers={"X-Request-ID": "request-123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["projectId"] == "fixture-id"
    assert body["canonicalPath"] == str(project.resolve())
    assert body["access"] == "read_write"
    assert body["git"]["baselineCommit"]
    assert response.headers["X-Request-ID"] == "request-123"
    assert runtime.doctor_calls[0].canonical_path == str(project.resolve())

    assert client.get("/api/v1/projects").json()["projects"][0]["projectId"] == "fixture-id"
    assert client.get("/api/v1/projects/fixture-id").status_code == 200
    assert client.get("/api/v1/projects/fixture-id/health").json()["health"]["ok"] is True
    assert client.get("/api/v1/projects/fixture-id/manifest").json()["manifest"] == {
        "version": 1,
        "slug": "fixture-project",
        "name": "Fixture project",
        "defaultBranch": "main",
        "knowledgeMode": "markdown_graph",
        "paths": {"topics_root": "topics"},
    }


def test_symlink_target_outside_linked_policy_is_rejected(tmp_path: Path):
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    outside = _git_project(tmp_path / "outside")
    link = linked_root / "escape"
    link.symlink_to(outside, target_is_directory=True)
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/projects",
        json={"displayName": "Escape", "path": str(link), "workspaceMode": "linked_local"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "workspace_access_denied"


def test_path_traversal_outside_linked_policy_is_rejected(tmp_path: Path):
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    outside = _git_project(tmp_path / "outside")
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/projects",
        json={
            "displayName": "Traversal",
            "path": str(linked_root / ".." / outside.name),
            "workspaceMode": "linked_local",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "workspace_access_denied"


def test_managed_git_workspace_is_write_capable(tmp_path: Path):
    managed_root = tmp_path / "managed"
    managed_root.mkdir()
    project = _git_project(managed_root / "fixture")
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/projects",
        json={"displayName": "Managed", "path": str(project), "workspaceMode": "managed"},
    )

    assert response.status_code == 201
    assert response.json()["workspaceMode"] == "managed"
    assert response.json()["access"] == "read_write"


def test_non_git_linked_workspace_is_persisted_read_only(tmp_path: Path):
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    project = linked_root / "read-only-project"
    project.mkdir()
    client = _client(tmp_path)

    registered = client.post(
        "/api/v1/projects",
        json={"projectId": "read-only", "displayName": "Read only", "path": str(project), "workspaceMode": "linked_local"},
    )
    assert registered.status_code == 201
    assert registered.json()["access"] == "read_only"
    assert registered.json()["git"]["isRepository"] is False

    restarted = _client(tmp_path)
    persisted = restarted.get("/api/v1/projects/read-only")
    assert persisted.status_code == 200
    assert persisted.json()["canonicalPath"] == str(project.resolve())


def test_unhealthy_krail_project_is_not_registered(tmp_path: Path):
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    project = _git_project(linked_root / "broken")
    client = _client(
        tmp_path,
        FakeRuntime(
            ProjectHealth(
                ok=False,
                checks=[ProjectHealthCheck(name="manifest", ok=False, detail="bad manifest")],
                krail_version="0.2.2",
            )
        ),
    )

    response = client.post(
        "/api/v1/projects",
        json={"displayName": "Broken", "path": str(project), "workspaceMode": "linked_local"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "workspace_invalid"
    assert client.get("/api/v1/projects").json() == {"projects": []}
