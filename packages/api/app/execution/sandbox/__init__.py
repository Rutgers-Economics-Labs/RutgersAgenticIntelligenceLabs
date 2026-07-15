"""Enforcing local execution sandboxes.

``sandbox-exec`` is a macOS compatibility backend, not a portable isolation
primitive.  Callers must select a provider explicitly (or use
``select_sandbox``) and restricted execution never falls back to the raw
runner.
"""

from .capabilities import SandboxCapability, detect_capability
from .errors import SandboxPolicyError, SandboxUnavailableError
from .macos import MacOSSandboxExec
from .policy import SandboxPolicy, build_macos_policy
from .provider import select_sandbox

__all__ = [
    "MacOSSandboxExec",
    "SandboxCapability",
    "SandboxPolicy",
    "SandboxPolicyError",
    "SandboxUnavailableError",
    "build_macos_policy",
    "detect_capability",
    "select_sandbox",
]
