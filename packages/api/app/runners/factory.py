"""
RunnerFactory — resolves runner adapter instances by name.

Usage::

    from app.runners.factory import RunnerFactory

    runner = RunnerFactory.get("jules")
    session = await runner.create_session(task_payload)

Adding a new runner:
    1. Implement ``BaseRunner`` in a new module (e.g. ``app/runners/claude_code.py``).
    2. Add its class to ``REGISTRY`` below.
    3. Ensure required settings fields are present in ``app.core.config.Settings``.
"""
from __future__ import annotations

from typing import Type

from app.runners.base import BaseRunner


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _build_registry() -> dict[str, Type[BaseRunner]]:
    """Lazy-import adapters so the factory never hard-fails at import time."""
    from app.runners.claude_code import ClaudeCodeRunner
    from app.runners.copilot_cli import CopilotCliRunner
    from app.runners.codex_cli import CodexCliRunner
    from app.runners.cursor_cli import CursorCliRunner
    from app.runners.gemini_cli import GeminiCliRunner
    from app.runners.jules import JulesRunner

    return {
        "jules": JulesRunner,
        "claude_code": ClaudeCodeRunner,
        "codex_cli": CodexCliRunner,
        "gemini_cli": GeminiCliRunner,
        "cursor_cli": CursorCliRunner,
        "copilot_cli": CopilotCliRunner,
    }


# ---------------------------------------------------------------------------
# RunnerFactory
# ---------------------------------------------------------------------------

class RunnerFactory:
    """Factory that instantiates the correct runner adapter from a name string.

    Runner adapters are instantiated with their required credentials sourced
    from ``app.core.config.settings``.  Raises ``ValueError`` for unknown
    runner names; raises ``RuntimeError`` if required credentials are absent.
    """

    _instances: dict[str, BaseRunner] = {}

    @staticmethod
    def list_runners() -> list[dict[str, str]]:
        """Return metadata for all registered runner adapters."""
        registry = _build_registry()
        result = []
        for name, cls in registry.items():
            # Instantiation may fail (missing creds) — return metadata without it.
            description = getattr(cls, "description", property(lambda self: "")).fget(object.__new__(cls)) if isinstance(getattr(cls, "description", None), property) else ""
            result.append({"name": name, "description": description})
        return result

    @staticmethod
    def get(name: str) -> BaseRunner:
        """Return an authenticated runner adapter for ``name``.

        Args:
            name: Runner identifier, e.g. ``"jules"``.

        Raises:
            ValueError:     Unknown runner name.
            RuntimeError:   Required credentials not configured in settings.
        """
        from app.core.config import settings

        cached = RunnerFactory._instances.get(name)
        if cached is not None:
            return cached

        registry = _build_registry()
        cls = registry.get(name)
        if cls is None:
            known = ", ".join(sorted(registry.keys()))
            raise ValueError(
                f"Unknown runner '{name}'. Available runners: {known}"
            )

        # ------------------------------------------------------------------
        # Jules
        # ------------------------------------------------------------------
        if name == "jules":
            api_key = getattr(settings, "jules_api_key", None) or ""
            if not api_key:
                raise RuntimeError(
                    "JulesRunner requires JULES_API_KEY to be set in the environment."
                )
            api_url = getattr(settings, "jules_api_url", "https://jules.googleapis.com/v1alpha")
            jules_source = getattr(settings, "jules_source", "sources/github/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs")
            instance = cls(api_key=api_key, api_url=api_url, source=jules_source)
            RunnerFactory._instances[name] = instance
            return instance

        if name == "claude_code":
            instance = cls(command=getattr(settings, "claude_code_command", "claude"))
            RunnerFactory._instances[name] = instance
            return instance
        if name == "codex_cli":
            instance = cls(command=getattr(settings, "codex_cli_command", "codex"))
            RunnerFactory._instances[name] = instance
            return instance
        if name == "gemini_cli":
            instance = cls(command=getattr(settings, "gemini_cli_command", "gemini"))
            RunnerFactory._instances[name] = instance
            return instance
        if name == "cursor_cli":
            instance = cls(command=getattr(settings, "cursor_cli_command", "agent"))
            RunnerFactory._instances[name] = instance
            return instance
        if name == "copilot_cli":
            instance = cls(command=getattr(settings, "copilot_cli_command", "gh copilot suggest"))
            RunnerFactory._instances[name] = instance
            return instance

        # Generic fallback (future adapters that take no constructor args)
        instance = cls()  # type: ignore[call-arg]
        RunnerFactory._instances[name] = instance
        return instance
