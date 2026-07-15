from __future__ import annotations

import time
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.execution import CommandExecutor, ExecutionService, InMemoryRunStore, LocalRunSupervisor, PermissionProfile, PermissionProfileRegistry, RunStatus, WorktreeManager
from app.krail_runtime.contracts import ProjectHealth, ProjectHealthCheck, RunHandle
from app.main_krail import create_app
from app.projects.registry import RegistryConfig


class Runtime:
    def __init__(self) -> None:
        self.calls = []

    def doctor(self, project):
        return ProjectHealth(ok=True, checks=[ProjectHealthCheck(name="ok", ok=True, detail="ok")], krail_version="test")

    def execute_workflow(self, project, request):
        self.calls.append((project, request))
        if request.inputs.get("wait"):
            time.sleep(0.15)
        if request.inputs.get("failure"):
            raise RuntimeError("/secret/path command output")
        return RunHandle(run_id="runtime-run", workflow_id=request.workflow_id, status="succeeded")


def client(tmp_path: Path, *, full_access_enabled: bool = False):
    root = tmp_path / "linked"; root.mkdir()
    project = root / "project"; project.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(project)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "Test"], check=True)
    (project / "README.md").write_text("fixture")
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-m", "base"], check=True, capture_output=True)
    runtime = Runtime()
    app = create_app(
        registry_config=RegistryConfig(tmp_path / "registry.json", tmp_path / "managed", (root,)),
        runtime=runtime,
        run_store=InMemoryRunStore(),
        permission_profiles=PermissionProfileRegistry(full_access_enabled=full_access_enabled),
        max_run_workers=1,
    )
    http = TestClient(app)
    assert http.post("/api/v1/projects", json={"projectId": "p", "displayName": "P", "path": str(project), "workspaceMode": "linked_local"}).status_code == 201
    return http, runtime


def wait_for(http, run_id):
    for _ in range(40):
        response = http.get(f"/api/v1/projects/p/runs/{run_id}")
        if response.json()["run"]["status"] in {"succeeded", "failed", "cancelled"}:
            return response
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_authorization_async_lifecycle_and_project_isolation(tmp_path: Path):
    http, runtime = client(tmp_path)
    denied = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "dryRun": False})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "execution_permission_denied"
    unknown = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "permissionProfile": "made-up"})
    assert unknown.status_code == 403
    disabled_full = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "permissionProfile": "full-access"})
    assert disabled_full.status_code == 403
    response = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "inputs": {"wait": True}})
    assert response.status_code == 202
    run_id = response.json()["run"]["runId"]
    assert response.json()["run"]["permissionProfile"] == "restricted-dry-run"
    done = wait_for(http, run_id)
    assert done.json()["run"]["status"] == "succeeded"
    assert runtime.calls[0][0].path.name == "project"
    assert http.get(f"/api/v1/projects/other/runs/{run_id}").status_code == 404
    assert http.get("/api/v1/projects/p/runs/bad!").status_code == 422


def test_operator_enabled_full_access_can_run_non_dry_workflow(tmp_path: Path):
    http, runtime = client(tmp_path, full_access_enabled=True)
    response = http.post(
        "/api/v1/projects/p/runs",
        json={"workflowId": "w", "dryRun": False, "permissionProfile": "full-access"},
    )
    assert response.status_code == 202
    done = wait_for(http, response.json()["run"]["runId"])
    assert done.json()["run"]["status"] == "succeeded"
    assert runtime.calls[0][1].dry_run is False


def test_events_order_reconnect_terminal_and_structured_runtime_failure(tmp_path: Path):
    http, _ = client(tmp_path)
    response = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "inputs": {"failure": True}})
    run_id = response.json()["run"]["runId"]
    assert wait_for(http, run_id).json()["run"]["result"]["error"] == "Workflow execution failed"
    events = http.get(f"/api/v1/projects/p/runs/{run_id}/events").json()["events"]
    assert [event["kind"] for event in events] == ["queued", "running", "failed"]
    stream = http.get(f"/api/v1/projects/p/runs/{run_id}/events/stream")
    assert stream.status_code == 200
    assert [event["eventId"] for event in events] == [line[4:] for line in stream.text.splitlines() if line.startswith("id: ")]
    reconnect = http.get(f"/api/v1/projects/p/runs/{run_id}/events/stream", headers={"Last-Event-ID": events[0]["eventId"]})
    assert events[0]["eventId"] not in reconnect.text and events[1]["eventId"] in reconnect.text
    unknown = http.get(f"/api/v1/projects/p/runs/{run_id}/events/stream", headers={"Last-Event-ID": "gone"})
    assert unknown.status_code == 409 and unknown.json()["error"]["code"] == "event_cursor_unknown"


def test_cancel_does_not_depend_on_stream_viewer(tmp_path: Path):
    http, _ = client(tmp_path)
    response = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "inputs": {"wait": True}})
    run_id = response.json()["run"]["runId"]
    cancelled = http.post(f"/api/v1/projects/p/runs/{run_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["run"]["status"] == "cancelled"


def test_read_only_projects_rejected_before_supervisor_submission(tmp_path: Path):
    http, runtime = client(tmp_path)
    readonly = tmp_path / "linked" / "readonly"; readonly.mkdir()
    assert http.post("/api/v1/projects", json={"projectId": "ro", "displayName": "RO", "path": str(readonly), "workspaceMode": "linked_local"}).status_code == 201
    response = http.post("/api/v1/projects/ro/runs", json={"workflowId": "w"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "project_read_only"
    assert runtime.calls == []


def test_profile_registry_empty_and_package_exports_are_fail_closed():
    assert PermissionProfileRegistry(profiles=())._profiles == {}
    assert CommandExecutor and WorktreeManager
    with pytest.raises(PermissionError):
        PermissionProfileRegistry(profiles=()).select(None, dry_run=True)


def test_supervisor_waits_for_profile_capacity_cancellation_and_shutdown(tmp_path: Path):
    class BlockingRuntime:
        def __init__(self): self.calls = 0
        def execute_workflow(self, project, request):
            self.calls += 1; time.sleep(0.12)
            return RunHandle(workflow_id=request.workflow_id, status="succeeded")
    runtime = BlockingRuntime(); service = ExecutionService(InMemoryRunStore(), runtime)
    profile = PermissionProfile.full_access(max_concurrency=1)
    first = service.create_run(project_id="p", project_path=tmp_path, kind="workflow", profile=profile, workflow_id="one")
    second = service.create_run(project_id="p", project_path=tmp_path, kind="workflow", profile=profile, workflow_id="two")
    third = service.create_run(project_id="p", project_path=tmp_path, kind="workflow", profile=profile, workflow_id="three")
    supervisor = LocalRunSupervisor(service, max_workers=2)
    from app.krail_runtime.contracts import RunRequest
    supervisor.submit_workflow(first.run_id, RunRequest(workflow_id="one", dry_run=False))
    supervisor.submit_workflow(second.run_id, RunRequest(workflow_id="two", dry_run=False))
    supervisor.submit_workflow(third.run_id, RunRequest(workflow_id="three", dry_run=False))
    assert service.cancel(third.run_id).status is RunStatus.CANCELLED
    for _ in range(50):
        if service.store.get(second.run_id).status is RunStatus.SUCCEEDED:
            break
        time.sleep(0.02)
    assert service.store.get(first.run_id).status is RunStatus.SUCCEEDED
    assert service.store.get(second.run_id).status is RunStatus.SUCCEEDED
    assert service.store.get(third.run_id).status is RunStatus.CANCELLED
    supervisor.shutdown(wait=True, cancel_futures=True)
