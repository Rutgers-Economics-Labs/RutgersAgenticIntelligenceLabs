from __future__ import annotations

from app.runners.cli_base import LocalCLIRunner


class CodexCliRunner(LocalCLIRunner):
    runner_name = "codex_cli"
    description_text = "Codex CLI runner"
