from __future__ import annotations

from app.runners.cli_base import LocalCLIRunner


class CursorCliRunner(LocalCLIRunner):
    runner_name = "cursor_cli"
    description_text = "Cursor CLI runner"
