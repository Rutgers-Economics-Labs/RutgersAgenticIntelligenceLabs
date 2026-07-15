"""Control-plane imports for the canonical KRAIL adapter boundary."""
from __future__ import annotations

from app.krail_runtime.contracts import KrailRuntime, ProjectHealth, ProjectManifest, ProjectRef

from .errors import RuntimeUnavailableError


class UnavailableKrailRuntime:
    """Safe bootstrap default until a concrete KRAIL adapter is configured."""

    def doctor(self, project: ProjectRef) -> ProjectHealth:
        raise RuntimeUnavailableError("No KRAIL runtime adapter has been configured")

    def manifest(self, project: ProjectRef) -> ProjectManifest:
        raise RuntimeUnavailableError("No KRAIL runtime adapter has been configured")


__all__ = [
    "KrailRuntime",
    "ProjectHealth",
    "ProjectManifest",
    "ProjectRef",
    "UnavailableKrailRuntime",
]
