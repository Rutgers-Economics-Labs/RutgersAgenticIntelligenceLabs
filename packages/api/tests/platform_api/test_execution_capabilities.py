from __future__ import annotations

from fastapi.testclient import TestClient

from app.execution import PermissionProfileRegistry
from app.krail_runtime.contracts import ProjectHealth, ProjectHealthCheck
from app.main_krail import create_app
from app.projects.registry import RegistryConfig


class Runtime:
    def doctor(self, project):
        return ProjectHealth(ok=True, checks=[ProjectHealthCheck(name="ok", ok=True, detail="ok")], krail_version="test")


def test_operator_execution_capabilities_inventory_is_server_owned(tmp_path):
    app = create_app(
        registry_config=RegistryConfig(tmp_path / "registry.json", tmp_path / "managed"),
        runtime=Runtime(),
        permission_profiles=PermissionProfileRegistry(full_access_enabled=False),
    )
    client = TestClient(app)
    response = client.get("/api/v1/operator/execution-capabilities", headers={"X-Request-ID": "cap-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "cap-1"
    profiles = {profile["name"]: profile for profile in response.json()["profiles"]}
    assert profiles["restricted-dry-run"]["enabled"] is True
    assert profiles["restricted-dry-run"]["processEnabled"] is False
    assert profiles["full-access"]["enabled"] is False
    assert "sandbox" in response.json()
