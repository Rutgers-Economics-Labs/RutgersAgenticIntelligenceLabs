"""The sole application boundary for the published KRAIL runtime.

No application code outside this package may import ``rail``.  The PyPI
distribution is named ``krail`` while its Python namespace is ``rail``.
"""

from .contracts import (
    ApprovalDecision,
    ApprovalInventory,
    FindQuery,
    GraphQuery,
    KrailRuntime,
    ProjectRef,
    RunRequest,
    SourceCheck,
    SourceImpact,
)
from .local import LocalKrailRuntime

__all__ = [
    "ApprovalDecision",
    "ApprovalInventory",
    "FindQuery",
    "GraphQuery",
    "KrailRuntime",
    "LocalKrailRuntime",
    "ProjectRef",
    "RunRequest",
    "SourceCheck",
    "SourceImpact",
]
