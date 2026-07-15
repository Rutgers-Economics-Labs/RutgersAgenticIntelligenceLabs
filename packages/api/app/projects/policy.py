"""Explicit containment and filesystem-access policy for registered workspaces."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import WorkspacePolicyError, WorkspaceValidationError
from .models import WorkspaceMode


def _resolve_existing(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    try:
        return candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise WorkspaceValidationError(
            "Workspace path does not exist", details={"path": str(candidate)}
        ) from exc
    except OSError as exc:
        raise WorkspaceValidationError(
            "Workspace path could not be resolved", details={"path": str(candidate)}
        ) from exc


@dataclass(frozen=True)
class PathAccessPolicy:
    """Allow registration only under configured canonical roots.

    Resolution happens before containment checks, so a symlink inside an allowed
    root cannot be used to register a target outside that root.
    """

    managed_root: Path
    linked_roots: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "managed_root", self.managed_root.expanduser().resolve())
        object.__setattr__(
            self,
            "linked_roots",
            tuple(root.expanduser().resolve() for root in self.linked_roots),
        )

    def canonicalize(self, path: str | Path, mode: WorkspaceMode) -> Path:
        resolved = _resolve_existing(path)
        if not resolved.is_dir():
            raise WorkspaceValidationError(
                "Workspace path must be a directory", details={"path": str(resolved)}
            )

        allowed_roots = (
            (self.managed_root,)
            if mode is WorkspaceMode.MANAGED
            else self.linked_roots
        )
        if not allowed_roots:
            raise WorkspacePolicyError(
                "Linked-local workspaces are disabled until explicit allowed roots are configured"
            )
        if not any(resolved.is_relative_to(root) for root in allowed_roots):
            raise WorkspacePolicyError(
                "Workspace path is outside the configured access policy",
                details={"path": str(resolved), "mode": mode.value},
            )
        if not os.access(resolved, os.R_OK | os.X_OK):
            raise WorkspacePolicyError(
                "Service account cannot read the workspace", details={"path": str(resolved)}
            )
        return resolved
