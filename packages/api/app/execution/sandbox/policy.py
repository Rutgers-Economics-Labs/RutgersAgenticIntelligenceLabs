"""Sandbox profile generation for the macOS Seatbelt backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..models import FilesystemMode, PermissionProfile
from .errors import SandboxPolicyError


@dataclass(frozen=True)
class SandboxPolicy:
    """Rendered Seatbelt profile and an audit-friendly capability note."""

    source: str
    allowed_roots: tuple[Path, ...]
    runtime_read_roots: tuple[Path, ...]
    deprecation_note: str


_NOTE = (
    "sandbox-exec is deprecated by Apple and retained only as a local macOS compatibility backend; "
    "it is not a Linux/container portability claim."
)


def _quoted(path: Path) -> str:
    # Reject controls rather than trying to maintain a second SBPL string
    # parser.  Newlines could otherwise terminate a generated policy form.
    value = str(path)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SandboxPolicyError("Filesystem paths cannot contain control characters")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unique_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(path.resolve() for path in paths))


def runtime_read_roots(executable: Path) -> tuple[Path, ...]:
    """Minimal conventional runtime trees required for a macOS executable to load.

    These are explicit launcher dependencies, not user data roots.  The
    executable's own containing directory is included because Python/other
    runtimes commonly load adjacent framework files.
    """
    executable = executable.resolve()
    roots = [Path("/System"), Path("/usr/lib"), Path("/usr/share"), executable.parent]
    # A Homebrew formula or Conda environment has a self-contained prefix one
    # level above ``bin``.  Grant that prefix, never the whole package manager
    # tree (/opt/homebrew or /usr/local), so Python can load stdlib and dylibs.
    if executable.parent.name == "bin" and executable.is_relative_to(Path("/opt/homebrew")):
        roots.append(executable.parent.parent)
    if executable.parent.name == "bin" and executable.is_relative_to(Path("/usr/local")):
        roots.append(executable.parent.parent)
    return _unique_paths(roots)


def build_macos_policy(*, executable: Path, cwd: Path, profile: PermissionProfile) -> SandboxPolicy:
    """Build a deny-by-default Seatbelt policy for one restricted invocation."""
    if profile.name == "full-access":
        raise SandboxPolicyError("full-access must use the raw runner, not a restricted sandbox policy")
    _quoted(executable)
    _quoted(cwd)
    for root in profile.filesystem_roots:
        _quoted(root)
    launch_path = executable.absolute()
    executable = executable.resolve()
    cwd = cwd.resolve()
    roots = _unique_paths(profile.filesystem_roots)
    if not roots:
        raise SandboxPolicyError("Restricted sandbox profiles require explicit filesystem roots")
    if not any(cwd.is_relative_to(root) for root in roots):
        raise SandboxPolicyError("Working directory is outside permitted filesystem roots")

    runtime_roots = runtime_read_roots(executable)
    # ``system.sb`` grants narrowly scoped macOS loader/runtime IPC and device
    # access (including System, /usr/lib and /dev/urandom).  It does not grant
    # project-data roots; those remain the explicit rules below.  Importing it
    # is necessary for current CPython runtimes, which otherwise abort during
    # Objective-C/mach bootstrap before user code starts.
    lines = ["(version 1)", '(import "system.sb")', "(deny default)"]
    # Needed for the direct argv launch and ordinary interpreter child handling.
    lines.extend(["(allow process-exec)", "(allow process-fork)"])
    for root in runtime_roots:
        lines.append(f"(allow file-read* (subpath {_quoted(root)}))")
        lines.append(f"(allow file-map-executable (subpath {_quoted(root)}))")
    # Permit exact executable read even if its parent is not an approved runtime tree.
    lines.append(f"(allow file-read* (literal {_quoted(executable)}))")
    lines.append(f"(allow file-map-executable (literal {_quoted(executable)}))")
    if launch_path != executable:
        # execvp checks the path supplied in argv before following a venv shim.
        lines.append(f"(allow file-read* (literal {_quoted(launch_path)}))")
        lines.append(f"(allow file-map-executable (literal {_quoted(launch_path)}))")
        # Seatbelt also needs to inspect the venv shim directory while walking
        # the supplied argv path.  Metadata only avoids granting venv contents.
        lines.append(f"(allow file-read-metadata (subpath {_quoted(launch_path.parent)}))")
    for root in roots:
        lines.append(f"(allow file-read* (subpath {_quoted(root)}))")
        if profile.filesystem_mode is FilesystemMode.READ_WRITE:
            lines.append(f"(allow file-write* (subpath {_quoted(root)}))")
    if profile.network_enabled:
        lines.extend(["(allow network-outbound)", "(allow network-inbound)", "(allow network-bind)"])
    # Do not add any network rule when disabled: deny-default blocks it.
    return SandboxPolicy("\n".join(lines) + "\n", roots, runtime_roots, _NOTE)
