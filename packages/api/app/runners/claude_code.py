from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.cli_base import LocalCLIRunner


class ClaudeCodeRunner(LocalCLIRunner):
    runner_name = "claude_code"
    description_text = "Claude Code CLI runner"

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = self._base_command_parts()
        args = [
            *parts,
            "--print",
            "--output-format",
            "stream-json",
            "--permission-mode",
            "bypassPermissions",
        ]
        if task_payload.local_repo_path:
            args.extend(["--add-dir", task_payload.local_repo_path])
        return [*args, prompt]
