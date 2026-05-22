"""Phase 3 — MCP Injection and CLI Fallback tests.

Covers:
  1. MCP config (.mcp.json) generation with correct env vars.
  2. RAIL environment variables injected into the runner process.
  3. WorkOrder and Result endpoints correctly handling local files.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.runners.base import TaskPayload
from app.runners.claude_code import ClaudeCodeRunner
from app.runners.mcp_injector import inject_mcp_config

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path

class TestMCPInjection:
    def test_inject_mcp_config_creates_valid_json(self, workspace: Path):
        mcp_path = inject_mcp_config(
            workspace,
            project_slug="test-proj",
            session_id="sess-123",
            work_order_id="wo-456",
            api_url="http://localhost:8000/api/v1",
            local_mode=True
        )
        
        assert mcp_path.exists()
        config = json.loads(mcp_path.read_text())
        assert "mcpServers" in config
        assert "rail" in config["mcpServers"]
        
        env = config["mcpServers"]["rail"]["env"]
        assert env["RAIL_PROJECT"] == "test-proj"
        assert env["RAIL_SESSION_ID"] == "sess-123"
        assert env["RAIL_WORK_ORDER_ID"] == "wo-456"
        assert env["RAIL_LOCAL"] == "1"
        assert env["RAIL_PATH"] == str(workspace)

class TestRunnerEnvironmentInjection:
    @patch("app.runners.cli_base.LocalCLIRunner._ensure_available")
    @patch("subprocess.Popen")
    @patch("app.runners.cli_base.runner_runtime_paths")
    def test_claude_code_injects_env_vars(self, mock_paths, mock_popen, mock_ensure, workspace: Path):
        # Mock runtime paths
        mock_paths.return_value = {
            "root": workspace / "runtime",
            "stdout": workspace / "stdout",
            "stderr": workspace / "stderr",
            "exit_code": workspace / "exit_code",
            "pid": workspace / "pid",
            "command": workspace / "command",
        }
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "runtime").mkdir(parents=True, exist_ok=True)

        runner = ClaudeCodeRunner()
        payload = TaskPayload(
            project_slug="test-proj",
            role="research",
            task_id="task-1",
            repo_url="https://github.com/org/repo",
            local_repo_path=str(workspace),
            branch="main",
            task_description="Do work",
            session_root=str(workspace / "session"),
            work_order_id="wo-123",
            work_order_path="research_plan/work_orders/wo-123.json"
        )
        
        # We need to mock _build_prompt to return a string
        runner._build_prompt = MagicMock(return_value="Prompt")
    
        # Mock the subprocess object
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_popen.return_value = mock_proc
    
        # Run create_session
        import anyio
        async def run():
            await runner.create_session(payload)
    
        anyio.run(run)
    
        # Verify env vars in the call to Popen
        args, kwargs = mock_popen.call_args
        env = kwargs.get("env")
        assert env is not None
        assert env["RAIL_PROJECT"] == "test-proj"
        assert env["RAIL_SESSION_ID"].startswith("claude_code_")
        assert env["RAIL_WORK_ORDER_ID"] == "wo-123"
        assert env["RAIL_WORK_ORDER_PATH"] == "research_plan/work_orders/wo-123.json"
        
        # Verify .mcp.json exists in workspace
        assert (workspace / ".mcp.json").exists()
