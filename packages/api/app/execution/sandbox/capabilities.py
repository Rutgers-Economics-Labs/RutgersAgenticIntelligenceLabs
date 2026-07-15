"""Provider capability discovery without attempting an unsafe fallback."""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxCapability:
    provider: str
    available: bool
    reason: str | None = None
    filesystem_enforcement: bool = False
    network_enforcement: bool = False
    portability_note: str | None = None


_MACOS_NOTE = (
    "sandbox-exec is a deprecated macOS compatibility backend; it is not portable. "
    "Use a Linux bwrap/container provider for hosted Linux execution."
)


def detect_capability() -> SandboxCapability:
    """Return the local backend capability; do not infer Docker availability."""
    if platform.system() != "Darwin":
        return SandboxCapability(
            provider="none", available=False,
            reason="No local restricted sandbox provider for this platform (Linux bwrap/container provider pending)",
        )
    executable = shutil.which("sandbox-exec")
    if executable is None:
        return SandboxCapability(
            provider="macos-sandbox-exec", available=False,
            reason="sandbox-exec is not installed or not on PATH", portability_note=_MACOS_NOTE,
        )
    return SandboxCapability(
        provider="macos-sandbox-exec", available=True, filesystem_enforcement=True,
        network_enforcement=True, portability_note=_MACOS_NOTE,
    )
