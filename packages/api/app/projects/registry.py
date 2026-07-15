"""Persistent, single-node project registry for operational metadata."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import ProjectConflictError, ProjectNotFoundError, WorkspaceValidationError
from .models import GitMetadata, ProjectRecord, WorkspaceAccess, WorkspaceMode
from .policy import PathAccessPolicy
from .runtime import KrailRuntime, ProjectHealth, ProjectRef


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _configured_paths() -> tuple[Path, Path, tuple[Path, ...]]:
    registry_path = Path(
        os.environ.get("RAIL_PROJECT_REGISTRY_PATH", ".rail/platform-projects.json")
    )
    managed_root = Path(
        os.environ.get("RAIL_MANAGED_WORKSPACE_ROOT", ".rail/projects")
    )
    configured_linked = os.environ.get("RAIL_LINKED_PROJECT_ROOTS", "")
    linked_roots = tuple(Path(item) for item in configured_linked.split(os.pathsep) if item)
    return registry_path, managed_root, linked_roots


@dataclass(frozen=True)
class RegistryConfig:
    storage_path: Path
    managed_workspace_root: Path
    linked_workspace_roots: tuple[Path, ...] = ()

    @classmethod
    def from_environment(cls) -> "RegistryConfig":
        storage_path, managed_root, linked_roots = _configured_paths()
        return cls(storage_path, managed_root, linked_roots)


def inspect_git(path: Path) -> GitMetadata:
    """Capture a small registration-time Git baseline without inspecting content."""

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    try:
        repository = git("rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired):
        repository = None
    if repository is None or repository.returncode != 0 or repository.stdout.strip() != "true":
        return GitMetadata(is_repository=False)

    top_level = git("rev-parse", "--show-toplevel")
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    dirty = git("status", "--porcelain=v1", "--untracked-files=normal")
    head_commit = head.stdout.strip() if head.returncode == 0 else None
    return GitMetadata(
        is_repository=True,
        repository_root=top_level.stdout.strip() if top_level.returncode == 0 else None,
        head_commit=head_commit,
        branch=branch.stdout.strip() or None,
        is_dirty=bool(dirty.stdout.strip()),
        # A commit is an immutable baseline. An unborn repository has no
        # write-capable baseline and is therefore registered read-only below.
        baseline_commit=head_commit,
        baseline_recorded_at=_utc_now() if head_commit else None,
    )


class ProjectRegistry:
    """JSON-backed registry suitable for one API process on one node.

    File replacement makes individual writes crash-safe. The process lock is
    intentionally local: multi-node coordination belongs to a later control-plane
    store, not this M2 registry.
    """

    def __init__(self, config: RegistryConfig) -> None:
        self.config = config
        self.policy = PathAccessPolicy(
            managed_root=config.managed_workspace_root,
            linked_roots=config.linked_workspace_roots,
        )
        self._lock = threading.RLock()

    def list(self) -> list[ProjectRecord]:
        with self._lock:
            return sorted(self._load().values(), key=lambda record: record.created_at)

    def get(self, project_id: str) -> ProjectRecord:
        with self._lock:
            try:
                return self._load()[project_id]
            except KeyError as exc:
                raise ProjectNotFoundError(f"Project '{project_id}' is not registered") from exc

    def register(
        self,
        *,
        project_id: str | None,
        display_name: str,
        path: str | Path,
        workspace_mode: WorkspaceMode,
        runtime: KrailRuntime,
    ) -> ProjectRecord:
        canonical_path = self.policy.canonicalize(path, workspace_mode)
        git = inspect_git(canonical_path)
        access = self._access_for(workspace_mode, git)
        stable_id = project_id or str(uuid.uuid4())
        ref = ProjectRef(
            path=canonical_path,
            project_id=stable_id,
            read_only=access is WorkspaceAccess.READ_ONLY,
        )
        health = runtime.doctor(ref)
        if not health.ok:
            raise WorkspaceValidationError(
                "KRAIL project health check failed during registration",
                details={
                    "warnings": health.warnings,
                    "failedChecks": [check.name for check in health.checks if not check.ok],
                },
            )

        with self._lock:
            records = self._load()
            if stable_id in records:
                raise ProjectConflictError(f"Project ID '{stable_id}' is already registered")
            if any(record.canonical_path == str(canonical_path) for record in records.values()):
                raise ProjectConflictError("Workspace path is already registered")
            record = ProjectRecord(
                project_id=stable_id,
                display_name=display_name,
                canonical_path=str(canonical_path),
                workspace_mode=workspace_mode,
                access=access,
                git=git,
            )
            records[stable_id] = record
            self._save(records)
            return record

    @staticmethod
    def project_ref(record: ProjectRecord) -> ProjectRef:
        return ProjectRef(
            path=Path(record.canonical_path),
            project_id=record.project_id,
            read_only=record.access is WorkspaceAccess.READ_ONLY,
        )

    @staticmethod
    def _access_for(mode: WorkspaceMode, git: GitMetadata) -> WorkspaceAccess:
        if mode is WorkspaceMode.MANAGED:
            if not git.is_repository or not git.baseline_commit:
                raise WorkspaceValidationError(
                    "Managed workspaces must be Git repositories with a baseline commit"
                )
            return WorkspaceAccess.READ_WRITE
        # Linked non-Git directories are explicitly inspect-only. Dirty or unborn
        # linked repositories are also kept read-only until an operator establishes
        # a clean recorded baseline for a later workflow slice.
        if not git.is_repository or not git.baseline_commit or git.is_dirty:
            return WorkspaceAccess.READ_ONLY
        return WorkspaceAccess.READ_WRITE

    def _load(self) -> dict[str, ProjectRecord]:
        path = self.config.storage_path
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("version") != 1:
                raise WorkspaceValidationError("Unsupported project registry version")
            return {
                item["project_id"]: ProjectRecord.model_validate(item)
                for item in payload.get("projects", [])
            }
        except json.JSONDecodeError as exc:
            raise WorkspaceValidationError("Project registry is not valid JSON") from exc

    def _save(self, records: dict[str, ProjectRecord]) -> None:
        path = self.config.storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "projects": [record.storage_dict() for record in records.values()],
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(payload, temporary, sort_keys=True, separators=(",", ":"))
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
