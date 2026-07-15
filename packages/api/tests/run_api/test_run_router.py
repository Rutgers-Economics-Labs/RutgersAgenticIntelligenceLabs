from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.run_router import router as runs_router
from app.execution import ExecutionService, InMemoryRunStore, LocalRunSupervisor, PermissionProfileRegistry
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


def client(tmp_path: Path):
    root = tmp_path / "linked"; root.mkdir()
    project = root / "project"; project.mkdir()
    runtime = Runtime()
    app = create_app(registry_config=RegistryConfig(tmp_path / "registry.json", tmp_path / "managed", (root,)), runtime=runtime)
    app.state.execution_service = ExecutionService(InMemoryRunStore(), runtime)
    app.state.permission_profiles = PermissionProfileRegistry(full_access_enabled=False)
    app.state.run_supervisor = LocalRunSupervisor(app.state.execution_service, max_workers=1)
    app.include_router(runs_router, prefix="/api/v1")
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
    response = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "inputs": {"wait": True}})
    assert response.status_code == 202
    run_id = response.json()["run"]["runId"]
    assert response.json()["run"]["permissionProfile"] == "restricted-dry-run"
    done = wait_for(http, run_id)
    assert done.json()["run"]["status"] == "succeeded"
    assert runtime.calls[0][0].path.name == "project"
    assert http.get(f"/api/v1/projects/other/runs/{run_id}").status_code == 404


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


def test_cancel_does_not_depend_on_stream_viewer(tmp_path: Path):
    http, _ = client(tmp_path)
    response = http.post("/api/v1/projects/p/runs", json={"workflowId": "w", "inputs": {"wait": True}})
    run_id = response.json()["run"]["runId"]
    cancelled = http.post(f"/api/v1/projects/p/runs/{run_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["run"]["status"] == "cancelled"
