"""MCP injector — writes .mcp.json with the right command resolution."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.runners import mcp_injector


def test_inject_writes_mcp_config(tmp_path):
    out = mcp_injector.inject_mcp_config(
        tmp_path,
        project_slug="alpha",
        session_id="sess-001",
        work_order_id="wo_abc",
    )
    assert out == tmp_path / ".mcp.json"
    assert out.is_file()
    payload = json.loads(out.read_text())

    assert "mcpServers" in payload
    assert "rail" in payload["mcpServers"]
    rail = payload["mcpServers"]["rail"]
    assert rail["env"]["RAIL_PROJECT"] == "alpha"
    assert rail["env"]["RAIL_SESSION_ID"] == "sess-001"
    assert rail["env"]["RAIL_WORK_ORDER_ID"] == "wo_abc"
    assert "--transport" in rail["args"]
    assert "stdio" in rail["args"]


def test_uses_path_binary_when_available(tmp_path):
    """If rail-mcp is on PATH, prefer it over the python -m fallback."""
    with patch("app.runners.mcp_injector.shutil.which", return_value="/usr/local/bin/rail-mcp"):
        mcp_injector.inject_mcp_config(tmp_path, project_slug="a", session_id="s")
    payload = json.loads((tmp_path / ".mcp.json").read_text())
    assert payload["mcpServers"]["rail"]["command"] == "rail-mcp"
    # No -m prefix when using the entry point
    assert "-m" not in payload["mcpServers"]["rail"]["args"]


def test_falls_back_to_python_m_when_binary_missing(tmp_path):
    """If the rail-mcp entry point is missing, fall back to python -m rail_mcp.server
    using the *current* interpreter so the spawned subprocess inherits the venv.

    This is the workaround for ``Executable not found in $PATH`` that broke the
    Phase 4 Q&A flow in the wild — see docs/smoke-test-nj-housing.md.
    """
    with patch("app.runners.mcp_injector.shutil.which", return_value=None):
        mcp_injector.inject_mcp_config(tmp_path, project_slug="a", session_id="s")
    payload = json.loads((tmp_path / ".mcp.json").read_text())
    assert payload["mcpServers"]["rail"]["command"] == sys.executable
    assert payload["mcpServers"]["rail"]["args"][:2] == ["-m", "rail_mcp.server"]
    assert "--transport" in payload["mcpServers"]["rail"]["args"]


def test_local_mode_env_vars(tmp_path):
    mcp_injector.inject_mcp_config(
        tmp_path,
        project_slug="alpha",
        session_id="s",
        local_mode=True,
    )
    payload = json.loads((tmp_path / ".mcp.json").read_text())
    env = payload["mcpServers"]["rail"]["env"]
    assert env["RAIL_LOCAL"] == "1"
    assert env["RAIL_PATH"] == str(tmp_path)


def test_optional_args_omitted_when_not_provided(tmp_path):
    mcp_injector.inject_mcp_config(
        tmp_path,
        project_slug="alpha",
        session_id="s",
        local_mode=False,
    )
    env = json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["rail"]["env"]
    assert "RAIL_WORK_ORDER_ID" not in env
    assert "RAIL_API_URL" not in env
    assert "RAIL_API_KEY" not in env
    assert "RAIL_LOCAL" not in env
