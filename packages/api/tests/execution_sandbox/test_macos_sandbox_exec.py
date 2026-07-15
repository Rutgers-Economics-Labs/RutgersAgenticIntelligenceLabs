from __future__ import annotations

import platform
import socket
import sys
from pathlib import Path
from threading import Event

import pytest

from app.execution import CommandExecutor, FilesystemMode, PermissionProfile
from app.execution.sandbox import MacOSSandboxExec, SandboxPolicyError, SandboxUnavailableError, build_macos_policy, detect_capability, select_sandbox


def _profile(root: Path, **changes) -> PermissionProfile:
    values = {
        "name": "local-restricted",
        "allowed_commands": frozenset({str(Path(sys.executable).resolve())}),
        "filesystem_roots": (root,),
        "filesystem_mode": FilesystemMode.READ_WRITE,
        "environment_allowlist": frozenset({"SAFE"}),
        "process_enabled": True,
        "timeout_seconds": 0.25,
    }
    values.update(changes)
    return PermissionProfile(**values)


@pytest.fixture
def sandbox() -> MacOSSandboxExec:
    capability = detect_capability()
    if not capability.available:
        pytest.skip(f"sandbox-exec local enforcement backend unavailable: {capability.reason}")
    return MacOSSandboxExec()


def _run(sandbox: MacOSSandboxExec, root: Path, code: str, **profile_changes):
    return CommandExecutor(sandbox).run(
        [sys.executable, "-c", code], cwd=root, profile=_profile(root, **profile_changes), env={"SAFE": "kept", "SECRET": "dropped"},
    )


def test_local_macos_capability_is_explicitly_not_portable(sandbox: MacOSSandboxExec) -> None:
    assert platform.system() == "Darwin"
    assert sandbox.capability.filesystem_enforcement and sandbox.capability.network_enforcement
    assert "deprecated" in (sandbox.capability.portability_note or "")
    assert isinstance(select_sandbox(), MacOSSandboxExec)


def test_allowed_write_succeeds_and_environment_is_filtered(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    # Deliberately preserve the venv shim in argv[0], rather than resolving it.
    assert Path(sys.executable).is_symlink()
    result = _run(sandbox, tmp_path, "import json, os, pathlib, ssl; pathlib.Path('allowed.txt').write_text(os.environ['SAFE']); print(os.getenv('SECRET'))")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "allowed.txt").read_text() == "kept"
    assert result.stdout.strip() == "None"


def test_write_outside_allowed_root_fails(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    outside = tmp_path.parent / "sandbox-outside.txt"
    outside.unlink(missing_ok=True)
    result = _run(sandbox, tmp_path, f"from pathlib import Path; Path({str(outside)!r}).write_text('no')")
    assert result.returncode != 0
    assert not outside.exists()


def test_read_only_profile_denies_write(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    result = _run(sandbox, tmp_path, "from pathlib import Path; Path('nope.txt').write_text('no')", filesystem_mode=FilesystemMode.READ_ONLY)
    assert result.returncode != 0
    assert not (tmp_path / "nope.txt").exists()


def test_read_outside_allowed_root_fails(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    result = _run(sandbox, tmp_path, "from pathlib import Path; print(Path('/etc/hosts').read_text())")
    assert result.returncode != 0


def test_network_disabled_blocks_local_bind_without_external_service(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    result = _run(sandbox, tmp_path, "import socket; s=socket.socket(); s.bind(('127.0.0.1', 0))")
    assert result.returncode != 0


def test_network_disabled_returns_eperm_for_outbound_localhost(sandbox: MacOSSandboxExec, tmp_path: Path) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        result = _run(sandbox, tmp_path, (
            "import errno, socket; s=socket.socket(); "
            f"\ntry: s.connect(('127.0.0.1', {port}))\n"
            "except OSError as error: raise SystemExit(0 if error.errno == errno.EPERM else 2)\n"
            "raise SystemExit(3)"
        ))
    finally:
        listener.close()
    assert result.returncode == 0, result.stderr


def test_timeout_and_cancellation_clean_up_the_sandbox_process_group(sandbox: MacOSSandboxExec, tmp_path: Path, monkeypatch) -> None:
    timed_out = _run(sandbox, tmp_path, "import time; time.sleep(5)")
    assert timed_out.timed_out
    cancelled = Event(); cancelled.set()
    monkeypatch.setattr("app.execution.sandbox.macos.subprocess.Popen", lambda *args, **kwargs: pytest.fail("must not launch"))
    result = CommandExecutor(sandbox).run([sys.executable, "-c", "print('never')"], cwd=tmp_path,
        profile=_profile(tmp_path), env={"SAFE": "kept"}, cancel=cancelled)
    assert result.cancelled


@pytest.mark.parametrize("path", [Path("bad\n(allow network-outbound)"), Path("bad\r(allow network-outbound)")])
def test_policy_rejects_control_characters_in_operator_paths(tmp_path: Path, path: Path) -> None:
    with pytest.raises(SandboxPolicyError, match="control characters"):
        build_macos_policy(executable=path, cwd=tmp_path, profile=_profile(tmp_path))
    with pytest.raises(SandboxPolicyError, match="control characters"):
        build_macos_policy(executable=Path(sys.executable), cwd=tmp_path,
            profile=_profile(tmp_path, filesystem_roots=(path,)))


def test_selection_fails_closed_when_backend_is_not_available(monkeypatch) -> None:
    from app.execution.sandbox import provider
    from app.execution.sandbox.capabilities import SandboxCapability

    monkeypatch.setattr(provider, "detect_capability", lambda: SandboxCapability("none", False, "test unavailable"))
    with pytest.raises(SandboxUnavailableError, match="test unavailable"):
        provider.select_sandbox()
