from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.cli_base import LocalCLIRunner


class CodexCliRunner(LocalCLIRunner):
    runner_name = "codex_cli"
    description_text = "Codex CLI runner"

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = self._base_command_parts()
        sandbox = "danger-full-access" if task_payload.role == "data" else "workspace-write"
        args = [
            *parts,
            "exec",
            "--skip-git-repo-check",
            "--json",
            "--sandbox",
            sandbox,
        ]
        if task_payload.local_repo_path:
            args.extend(["--cd", task_payload.local_repo_path])
        return [*args, prompt]
