"""
MCP Injector — handles per-session MCP configuration generation.

Provides a mechanism to inject local rail-mcp server tool access into
launched runner processes (like Claude Code, Cursor, etc.) without
mutating the user's global MCP config.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


def _resolve_mcp_command() -> tuple[str, list[str]]:
    """Resolve how to spawn the rail-mcp server.

    Prefer the installed ``rail-mcp`` entry point (shipped by
    packages/mcp-server). If that's not on PATH — common when the operator
    forgot ``make install-mcp`` — fall back to ``python -m rail_mcp.server``
    using the *current* interpreter so the spawned process inherits the venv
    that the API is running in.

    Returns ``(command, args_prefix)``. The injector still appends its own
    transport args after the prefix.
    """
    if shutil.which("rail-mcp"):
        return "rail-mcp", []
    # Fall back to module form. sys.executable is the venv's python; this
    # works in dev (editable install of rail-mcp) and in any deployment
    # where the package is importable.
    return sys.executable, ["-m", "rail_mcp.server"]


def inject_mcp_config(
    workspace_root: Path,
    *,
    project_slug: str,
    session_id: str,
    work_order_id: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    local_mode: bool = True,
) -> Path:
    """
    Generate a per-session .mcp.json in the workspace root.
    Returns the path to the generated config.
    """
    mcp_config_path = workspace_root / ".mcp.json"

    # Environment variables for the mcp-server process
    env = {
        "RAIL_PROJECT": project_slug,
        "RAIL_SESSION_ID": session_id,
    }
    if work_order_id:
        env["RAIL_WORK_ORDER_ID"] = work_order_id
    if api_url:
        env["RAIL_API_URL"] = api_url
    if api_key:
        env["RAIL_API_KEY"] = api_key
    if local_mode:
        env["RAIL_LOCAL"] = "1"
        env["RAIL_PATH"] = str(workspace_root)

    command, prefix_args = _resolve_mcp_command()
    config = {
        "mcpServers": {
            "rail": {
                "command": command,
                "args": [*prefix_args, "--transport", "stdio"],
                "env": env,
            }
        }
    }

    mcp_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return mcp_config_path
