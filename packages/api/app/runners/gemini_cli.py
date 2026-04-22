from __future__ import annotations

from app.runners.cli_base import LocalCLIRunner


class GeminiCliRunner(LocalCLIRunner):
    runner_name = "gemini_cli"
    description_text = "Gemini CLI runner"
