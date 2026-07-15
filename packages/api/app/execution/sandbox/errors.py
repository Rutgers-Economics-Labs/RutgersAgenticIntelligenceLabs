"""Typed failures for sandbox selection and policy construction."""

from __future__ import annotations

from ..errors import SandboxRequiredError


class SandboxUnavailableError(SandboxRequiredError):
    """No installed provider can enforce the requested restricted profile."""


class SandboxPolicyError(SandboxRequiredError):
    """The requested profile cannot be represented safely by this backend."""
