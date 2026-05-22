"""
MCP Injector — handles per-session MCP configuration generation.

Provides a mechanism to inject local rail-mcp server tool access into 
launched runner processes (like Claude Code, Cursor, etc.) without 
mutating the user's global MCP config.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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

    # Note: This assumes 'rail-mcp' is on the PATH and points to 
    # the entrypoint in packages/mcp-server/rail_mcp/server.py
    config = {
        "mcpServers": {
            "rail": {
                "command": "rail-mcp",
                "args": ["--transport", "stdio"],
                "env": env
            }
        }
    }

    mcp_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return mcp_config_path
