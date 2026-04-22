from __future__ import annotations

from app.runners.cli_base import LocalCLIRunner


class ClaudeCodeRunner(LocalCLIRunner):
    runner_name = "claude_code"
    description_text = "Claude Code CLI runner"
