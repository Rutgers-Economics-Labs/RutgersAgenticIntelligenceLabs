from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.cli_base import LocalCLIRunner


class CodexCliRunner(LocalCLIRunner):
    runner_name = "codex_cli"
    description_text = "Codex CLI runner"

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = self._base_command_parts()
        args = [
            *parts,
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "--json",
        ]
        if task_payload.local_repo_path:
            args.extend(["--cd", task_payload.local_repo_path])
        return [*args, prompt]
