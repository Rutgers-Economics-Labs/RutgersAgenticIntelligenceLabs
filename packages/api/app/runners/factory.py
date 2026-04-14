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
    from app.runners.jules import JulesRunner

    return {
        "jules": JulesRunner,
        # Future adapters:
        # "claude_code": ClaudeCodeRunner,
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

    @staticmethod
    def list_runners() -> list[dict[str, str]]:
        """Return metadata for all registered runner adapters."""
        registry = _build_registry()
        result = []
        for name, cls in registry.items():
            # Instantiation may fail (missing creds) — return metadata without it.
            description = getattr(cls, "description", property(lambda self: "")).fget(object.__new__(cls)) if isinstance(getattr(cls, "description", None), property) else ""
            result.append({"name": name, "description": description})
        return [
            {"name": "jules", "description": "Jules — Google's managed coding agent API (GitHub-native)"},
        ]

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
            return cls(api_key=api_key, api_url=api_url, source=jules_source)

        # Generic fallback (future adapters that take no constructor args)
        return cls()  # type: ignore[call-arg]
