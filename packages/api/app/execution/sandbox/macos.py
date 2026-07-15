"""macOS ``sandbox-exec`` implementation of the execution sandbox protocol."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from threading import Event
from typing import Sequence

from ..commands import CommandResult
from ..models import PermissionProfile
from .capabilities import detect_capability
from .errors import SandboxUnavailableError
from .policy import build_macos_policy

_MAX_CAPTURED_OUTPUT = 1_000_000


class MacOSSandboxExec:
    """A local, deny-by-default Seatbelt backend.

    Apple has deprecated ``sandbox-exec``.  Its capability object deliberately
    exposes that limitation so callers do not mistake it for a portable hosted
    sandbox.
    """

    def __init__(self, executable: str | Path = "/usr/bin/sandbox-exec") -> None:
        self.executable = Path(executable)
        capability = detect_capability()
        if not capability.available or not self.executable.is_file():
            raise SandboxUnavailableError(capability.reason or "sandbox-exec backend is unavailable")
        self.capability = capability

    @staticmethod
    def _read_limited(handle) -> str:
        handle.seek(0)
        value = handle.read(_MAX_CAPTURED_OUTPUT + 1).decode(errors="replace")
        return value if len(value) <= _MAX_CAPTURED_OUTPUT else value[:_MAX_CAPTURED_OUTPUT] + "\n[output truncated]"

    @staticmethod
    def _stop(process: subprocess.Popen, *, force: bool) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    def run(self, argv: Sequence[str], *, cwd: Path, environment: dict[str, str], profile: PermissionProfile,
            shell: bool, cancel: Event | None) -> CommandResult:
        if shell:
            # The command executor may authorize shells for full access, but this
            # backend intentionally preserves argv semantics for restricted runs.
            raise SandboxUnavailableError("Restricted sandbox execution does not support shell command strings")
        policy = build_macos_policy(executable=Path(argv[0]), cwd=cwd, profile=profile)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".sb") as policy_file, \
             tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            policy_file.write(policy.source)
            policy_file.flush()
            process = subprocess.Popen(
                [str(self.executable), "-f", policy_file.name, "--", *argv], cwd=cwd,
                env=environment, stdout=stdout, stderr=stderr, start_new_session=True,
            )
            deadline = time.monotonic() + profile.timeout_seconds
            try:
                while process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        self._stop(process, force=False)
                        return CommandResult(process.returncode, self._read_limited(stdout), self._read_limited(stderr), cancelled=True)
                    if time.monotonic() >= deadline:
                        self._stop(process, force=True)
                        return CommandResult(process.returncode, self._read_limited(stdout), self._read_limited(stderr), timed_out=True)
                    time.sleep(0.05)
                return CommandResult(process.returncode, self._read_limited(stdout), self._read_limited(stderr))
            except Exception:
                self._stop(process, force=True)
                raise
