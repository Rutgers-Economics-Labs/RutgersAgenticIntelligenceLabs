"""Tests for the runner probe system."""
from __future__ import annotations

import asyncio
import os
import shutil
import pytest

from app.runners.probe import (
    CheckStatus,
    ReadinessLevel,
    probe_all,
    probe_runner,
)


@pytest.mark.asyncio
async def test_probe_claude_code_not_installed(monkeypatch):
    # Mock shutil.which to return None to simulate binary not on PATH
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    res = await probe_runner("claude_code")
    assert res is not None
    assert res.runner_name == "claude_code"
    assert res.installed.status == CheckStatus.FAIL
    assert "not on PATH" in res.installed.detail
    assert res.readiness == ReadinessLevel.RED


@pytest.mark.asyncio
async def test_probe_claude_code_installed_and_responsive(monkeypatch):
    # Mock shutil.which to simulate binary on PATH
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/local/bin/claude")

    # Mock asyncio.create_subprocess_exec to simulate command --version success
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"1.0.0\n", b""

        def kill(self):
            pass

        async def wait(self):
            pass

    async def mock_create_subprocess_exec(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    res = await probe_runner("claude_code")
    assert res is not None
    assert res.runner_name == "claude_code"
    assert res.installed.status == CheckStatus.PASS
    assert res.installed.detail == "/usr/local/bin/claude"
    assert res.version == "1.0.0"
    assert res.readiness == ReadinessLevel.YELLOW


@pytest.mark.asyncio
async def test_probe_jules_key_not_set(monkeypatch):
    # Ensure JULES_API_KEY is not in the environment
    monkeypatch.delenv("JULES_API_KEY", raising=False)

    res = await probe_runner("jules")
    assert res is not None
    assert res.runner_name == "jules"
    assert res.installed.status == CheckStatus.FAIL
    assert "not set" in res.installed.detail
    assert res.readiness == ReadinessLevel.RED


@pytest.mark.asyncio
async def test_probe_jules_key_set(monkeypatch):
    # Simulate JULES_API_KEY being present
    monkeypatch.setenv("JULES_API_KEY", "sk-fakejuleskey")

    res = await probe_runner("jules")
    assert res is not None
    assert res.runner_name == "jules"
    assert res.installed.status == CheckStatus.PASS
    assert "present" in res.installed.detail
    assert res.readiness == ReadinessLevel.YELLOW


@pytest.mark.asyncio
async def test_probe_nonexistent_runner():
    res = await probe_runner("not_a_real_runner")
    assert res is None


@pytest.mark.asyncio
async def test_probe_all_structure(monkeypatch):
    # Mock shutil.which to return None and delete JULES_API_KEY to ensure tests are deterministic
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    monkeypatch.delenv("JULES_API_KEY", raising=False)

    res = await probe_all()
    expected_runners = {
        "jules",
        "claude_code",
        "codex_cli",
        "gemini_cli",
        "cursor_cli",
        "copilot_cli",
    }
    assert set(res.keys()) == expected_runners
    for name in expected_runners:
        assert res[name] is not None
        assert res[name].runner_name == name
