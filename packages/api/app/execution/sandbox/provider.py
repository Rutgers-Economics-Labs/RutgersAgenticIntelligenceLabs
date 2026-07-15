"""Fail-closed selection seam for local and future hosted sandbox providers."""

from __future__ import annotations

from ..commands import ExecutionSandbox
from .capabilities import detect_capability
from .errors import SandboxUnavailableError
from .macos import MacOSSandboxExec


def select_sandbox() -> ExecutionSandbox:
    """Select an enforcing local backend or raise; never return an unsafe runner.

    Linux bwrap and container providers belong behind this same protocol when
    they are implemented. Docker is intentionally not probed or assumed here.
    """
    capability = detect_capability()
    if capability.provider == "macos-sandbox-exec" and capability.available:
        return MacOSSandboxExec()
    raise SandboxUnavailableError(capability.reason or "No enforcing sandbox provider is available")
