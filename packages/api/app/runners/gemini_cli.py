from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.cli_base import LocalCLIRunner


class GeminiCliRunner(LocalCLIRunner):
    runner_name = "gemini_cli"
    description_text = "Gemini CLI runner"

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = self._base_command_parts()
        args = [
            *parts,
            "--prompt",
            prompt,
            "--output-format",
            "stream-json",
            "--approval-mode",
            "yolo",
        ]
        if task_payload.local_repo_path:
            args.extend(["--include-directories", task_payload.local_repo_path])
        return args
