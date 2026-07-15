"""Safe argv command execution with an explicit OS-enforcement boundary."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol, Sequence

from .errors import PermissionDeniedError, SandboxRequiredError
from .models import PermissionProfile

_MAX_CAPTURED_OUTPUT = 1_000_000


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


class ExecutionSandbox(Protocol):
    """A runtime that actually enforces filesystem/network policy at the OS boundary."""
    def run(self, argv: Sequence[str], *, cwd: Path, environment: dict[str, str], profile: PermissionProfile,
            shell: bool, cancel: Event | None) -> CommandResult: ...


class CommandExecutor:
    def __init__(self, sandbox: ExecutionSandbox | None = None) -> None:
        self.sandbox = sandbox

    @staticmethod
    def _environment(profile: PermissionProfile, supplied: dict[str, str] | None) -> dict[str, str]:
        # PATH is not special: it is passed only if the profile explicitly permits it.
        source = os.environ if supplied is None else supplied
        return {key: value for key, value in source.items()
                if key in profile.environment_allowlist or "*" in profile.environment_allowlist}

    @staticmethod
    def _validate_id(value: str, *, label: str) -> None:
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise PermissionDeniedError(f"Invalid {label}")

    def _validate(self, argv: Sequence[str], cwd: Path, profile: PermissionProfile, shell: bool) -> None:
        if not argv or not all(isinstance(value, str) and value for value in argv):
            raise PermissionDeniedError("Command argv cannot be empty")
        if not profile.process_enabled:
            raise PermissionDeniedError("Process execution is disabled")
        if shell and not profile.shell_enabled:
            raise PermissionDeniedError("Shell execution is disabled")
        executable = Path(argv[0])
        # A restricted profile must authorize an exact, resolved executable path.
        if "*" not in profile.allowed_commands:
            if not executable.is_absolute() or str(executable.resolve()) not in profile.allowed_commands:
                raise PermissionDeniedError("Restricted profiles require an exact allowed executable path")
        if str(executable.resolve()) in profile.denied_commands or "*" in profile.denied_commands:
            raise PermissionDeniedError(f"Command denied: {executable}")
        resolved = cwd.resolve()
        if not any(resolved.is_relative_to(root.resolve()) for root in profile.filesystem_roots):
            raise PermissionDeniedError(f"Working directory is outside permitted roots: {resolved}")

    @staticmethod
    def _trim(output: str) -> str:
        return output if len(output) <= _MAX_CAPTURED_OUTPUT else output[:_MAX_CAPTURED_OUTPUT] + "\n[output truncated]"

    def _raw_run(self, argv: Sequence[str], *, cwd: Path, environment: dict[str, str], profile: PermissionProfile,
                 shell: bool, cancel: Event | None) -> CommandResult:
        process = subprocess.Popen(list(argv) if not shell else " ".join(argv), cwd=cwd, env=environment,
            shell=shell, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        deadline = time.monotonic() + profile.timeout_seconds
        def stop(force: bool) -> tuple[str, str]:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
            try: return process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); return process.communicate()
        try:
            while True:
                if cancel and cancel.is_set():
                    out, err = stop(False); return CommandResult(process.returncode, self._trim(out), self._trim(err), cancelled=True)
                if time.monotonic() >= deadline:
                    out, err = stop(True); return CommandResult(process.returncode, self._trim(out), self._trim(err), timed_out=True)
                try:
                    out, err = process.communicate(timeout=0.05)
                    return CommandResult(process.returncode, self._trim(out), self._trim(err))
                except subprocess.TimeoutExpired: pass
        except Exception:
            if process.poll() is None: stop(True)
            raise

    def run(self, argv: Sequence[str], *, cwd: Path, profile: PermissionProfile, env: dict[str, str] | None = None,
            shell: bool = False, cancel: Event | None = None) -> CommandResult:
        self._validate(argv, cwd, profile, shell)
        environment = self._environment(profile, env)
        if self.sandbox:
            return self.sandbox.run(argv, cwd=cwd.resolve(), environment=environment, profile=profile, shell=shell, cancel=cancel)
        if profile.name != "full-access":
            raise SandboxRequiredError("Restricted filesystem or network execution requires an enforcing sandbox")
        return self._raw_run(argv, cwd=cwd.resolve(), environment=environment, profile=profile, shell=shell, cancel=cancel)
