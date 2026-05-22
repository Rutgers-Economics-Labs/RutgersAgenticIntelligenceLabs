"""Tests for the extended /runners API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runners.probe import ProbeResult, ProbeCheck, CheckStatus, ReadinessLevel

client = TestClient(app)


@pytest.fixture
def mock_probes(monkeypatch):
    import app.runners.probe as probe_module

    # Create dummy ProbeResult for any requested runner name
    def make_fake_result(name: str) -> ProbeResult:
        return ProbeResult(
            runner_name=name,
            timestamp=datetime.now(timezone.utc),
            installed=ProbeCheck(status=CheckStatus.PASS, detail=f"/mock/path/{name}"),
            authenticated=ProbeCheck(status=CheckStatus.SKIP, detail="auth not probed"),
            version="1.0.0",
            readiness=ReadinessLevel.YELLOW,
            notes=["mocked probe result"]
        )

    async def fake_probe_all():
        runners = ["jules", "claude_code", "codex_cli", "gemini_cli", "cursor_cli", "copilot_cli"]
        return {name: make_fake_result(name) for name in runners}

    async def fake_probe_runner(name: str):
        valid_runners = {"jules", "claude_code", "codex_cli", "gemini_cli", "cursor_cli", "copilot_cli"}
        if name not in valid_runners:
            return None
        return make_fake_result(name)

    monkeypatch.setattr(probe_module, "probe_all", fake_probe_all)
    monkeypatch.setattr(probe_module, "probe_runner", fake_probe_runner)


def test_list_runners_success(mock_probes):
    response = client.get("/api/v1/runners")
    assert response.status_code == 200
    data = response.json()
    assert "runners" in data
    runners = data["runners"]

    expected_names = {
        "jules",
        "claude_code",
        "codex_cli",
        "gemini_cli",
        "cursor_cli",
        "copilot_cli",
    }
    runner_names = {r["name"] for r in runners}
    assert expected_names.issubset(runner_names)

    for runner in runners:
        name = runner["name"]
        if name in expected_names:
            assert runner["registered"] is True
            assert "profile" in runner
            assert "probe" in runner

            probe = runner["probe"]
            assert probe["runner_name"] == name
            assert probe["readiness"] == "yellow"
            assert probe["installed"]["status"] == "pass"


def test_probe_runner_endpoint_success(mock_probes):
    response = client.get("/api/v1/runners/claude_code/probe")
    assert response.status_code == 200
    probe = response.json()
    assert probe["runner_name"] == "claude_code"
    assert probe["installed"]["status"] == "pass"
    assert probe["installed"]["detail"] == "/mock/path/claude_code"
    assert probe["readiness"] == "yellow"


def test_probe_runner_endpoint_not_found(mock_probes):
    response = client.get("/api/v1/runners/not_a_real_runner/probe")
    assert response.status_code == 404
    assert "no profile for runner" in response.json()["detail"]
