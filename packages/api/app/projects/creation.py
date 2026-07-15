"""Managed KRAIL workspace creation through the published CLI fallback.

KRAIL 0.2.2 has no Python project-initialization API.  This module is the
small, explicit subprocess boundary for that missing capability; it never
creates KRAIL project files itself.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess

from app.projects.errors import ProjectConflictError, WorkspaceValidationError
from app.projects.models import ProjectRecord, WorkspaceMode
from app.projects.registry import ProjectRegistry
from app.projects.runtime import KrailRuntime


CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _run_command(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a fixed executable argv without a shell or inherited project cwd."""
    try:
        return subprocess.run(
            arguments,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceValidationError("KRAIL project initialization could not start") from exc


class ManagedProjectCreator:
    """Creates one server-derived directory below the configured managed root."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or _run_command

    @staticmethod
    def _destination(registry: ProjectRegistry, slug: str) -> tuple[Path, Path]:
        root = registry.config.managed_workspace_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        destination = root / slug
        # The DTO constrains slug, but preserve this invariant here because this
        # is the final authority before filesystem mutation.
        if destination.parent != root or not destination.is_relative_to(root):
            raise WorkspaceValidationError("Managed project destination is invalid")
        return root, destination

    @staticmethod
    def _cleanup(destination: Path, root: Path) -> None:
        """Delete only the exact child created for this request; never follow links."""
        if destination.parent != root or not destination.exists() and not destination.is_symlink():
            return
        if destination.is_symlink():
            destination.unlink()
        else:
            shutil.rmtree(destination)

    def create(
        self,
        *,
        registry: ProjectRegistry,
        runtime: KrailRuntime,
        project_id: str,
        display_name: str,
        name: str,
        slug: str,
        pack: str,
        mode: str,
        knowledge_mode: str,
    ) -> ProjectRecord:
        if project_id in {record.project_id for record in registry.list()}:
            raise ProjectConflictError(f"Project ID '{project_id}' is already registered")
        root, destination = self._destination(registry, slug)
        if destination.exists() or destination.is_symlink():
            raise ProjectConflictError("Managed project destination already exists")

        created = False
        try:
            result = self._runner(
                [
                    "krail", "init", str(destination), "--name", name, "--slug", slug,
                    "--pack", pack, "--mode", mode, "--knowledge-mode", knowledge_mode,
                ],
                root,
            )
            created = destination.exists() or destination.is_symlink()
            if result.returncode != 0:
                raise WorkspaceValidationError("KRAIL project initialization failed")
            if not destination.is_dir() or destination.is_symlink():
                raise WorkspaceValidationError("KRAIL did not create a managed project directory")
            self._ensure_git_baseline(destination)
            # register() invokes canonical runtime.doctor() before persisting the
            # managed operational record.
            return registry.register(
                project_id=project_id,
                display_name=display_name,
                path=destination,
                workspace_mode=WorkspaceMode.MANAGED,
                runtime=runtime,
            )
        except Exception:
            # The destination was verified absent before the CLI was invoked;
            # any exact child present now belongs to this failed attempt.
            if created or destination.exists() or destination.is_symlink():
                self._cleanup(destination, root)
            raise

    def _ensure_git_baseline(self, destination: Path) -> None:
        check = self._runner(["git", "-C", str(destination), "rev-parse", "--is-inside-work-tree"], destination)
        if check.returncode != 0 or check.stdout.strip() != "true":
            initialized = self._runner(["git", "init", "-b", "main", str(destination)], destination.parent)
            if initialized.returncode != 0:
                raise WorkspaceValidationError("Could not initialize Git for the managed project")
        head = self._runner(["git", "-C", str(destination), "rev-parse", "HEAD"], destination)
        if head.returncode == 0 and head.stdout.strip():
            return
        added = self._runner(["git", "-C", str(destination), "add", "-A"], destination)
        committed = self._runner(
            [
                "git", "-C", str(destination), "-c", "user.name=RAIL", "-c", "user.email=rail@localhost",
                "commit", "-m", "Initialize KRAIL project",
            ],
            destination,
        )
        if added.returncode != 0 or committed.returncode != 0:
            raise WorkspaceValidationError("Could not create a Git baseline for the managed project")
