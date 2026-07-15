"""Safe argv command execution with profile enforcement."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Sequence

from .errors import PermissionDeniedError
from .models import PermissionProfile


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


class CommandExecutor:
    def _validate(self, argv: Sequence[str], cwd: Path, profile: PermissionProfile, shell: bool) -> None:
        if not argv:
            raise PermissionDeniedError("Command argv cannot be empty")
        if not profile.process_enabled:
            raise PermissionDeniedError("Process execution is disabled")
        if shell and not profile.shell_enabled:
            raise PermissionDeniedError("Shell execution is disabled")
        command = Path(argv[0]).name
        if command in profile.denied_commands or "*" in profile.denied_commands:
            raise PermissionDeniedError(f"Command denied: {command}")
        if command not in profile.allowed_commands and "*" not in profile.allowed_commands:
            raise PermissionDeniedError(f"Command is not allowed: {command}")
        resolved = cwd.resolve()
        if not any(resolved.is_relative_to(root.resolve()) for root in profile.filesystem_roots):
            raise PermissionDeniedError(f"Working directory is outside permitted roots: {resolved}")

    def run(self, argv: Sequence[str], *, cwd: Path, profile: PermissionProfile, env: dict[str, str] | None = None,
            shell: bool = False, cancel: Event | None = None) -> CommandResult:
        self._validate(argv, cwd, profile, shell)
        clean_env = {key: value for key, value in (env or {}).items()
                     if key in profile.environment_allowlist or "*" in profile.environment_allowlist}
        # shell=False is the default: argv is never interpolated into a shell command.
        process = subprocess.Popen(list(argv) if not shell else " ".join(argv), cwd=cwd, env=clean_env or None,
                                   shell=shell, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + profile.timeout_seconds
        try:
            while True:
                if cancel and cancel.is_set():
                    process.terminate()
                    out, err = process.communicate(timeout=2)
                    return CommandResult(process.returncode, out, err, cancelled=True)
                if time.monotonic() >= deadline:
                    process.kill()
                    out, err = process.communicate()
                    return CommandResult(process.returncode, out, err, timed_out=True)
                try:
                    out, err = process.communicate(timeout=0.05)
                    return CommandResult(process.returncode, out, err)
                except subprocess.TimeoutExpired:
                    if process.poll() is not None:
                        out, err = process.communicate()
                        return CommandResult(process.returncode, out, err)
        except Exception:
            process.kill()
            process.communicate()
            raise
