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
            "--verbose",
        ]
        if task_payload.local_repo_path:
            args.extend(["--add-dir", task_payload.local_repo_path])
        if task_payload.session_root:
            from pathlib import Path
            log_path = Path(task_payload.session_root) / "claude_debug.log"
            args.extend(["--debug-file", str(log_path)])
        return [*args, prompt]
