from __future__ import annotations

from app.runners.base import TaskPayload
from app.runners.cli_base import LocalCLIRunner


class CursorCliRunner(LocalCLIRunner):
    runner_name = "cursor_cli"
    description_text = "Cursor CLI runner"

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = self._base_command_parts()
        return [*parts, "agent", prompt]
