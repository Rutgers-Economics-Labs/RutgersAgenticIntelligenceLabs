from __future__ import annotations

from app.runners.factory import RunnerFactory


def test_list_runners_includes_cli_backends():
    runners = {item["name"] for item in RunnerFactory.list_runners()}
    assert {"jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli", "copilot_cli"}.issubset(runners)
