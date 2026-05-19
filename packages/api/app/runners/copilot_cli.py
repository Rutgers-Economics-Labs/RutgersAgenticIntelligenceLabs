from __future__ import annotations

from app.runners.cli_base import LocalCLIRunner


class CopilotCliRunner(LocalCLIRunner):
    runner_name = "copilot_cli"
    description_text = "GitHub Copilot CLI runner"
    prompt_flag = "-p"
