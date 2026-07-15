"""Server-owned immutable execution permission profiles.

Request payloads select a profile name only; they can never supply capability fields.
"""
from __future__ import annotations

from pathlib import Path

from .models import FilesystemMode, PermissionProfile


class PermissionProfileRegistry:
    def __init__(self, profiles: tuple[PermissionProfile, ...] | None = None, *, full_access_enabled: bool = False) -> None:
        default = PermissionProfile(
            name="restricted-dry-run", allowed_commands=frozenset(), filesystem_roots=(),
            filesystem_mode=FilesystemMode.READ_ONLY, environment_allowlist=frozenset(),
            process_enabled=False, shell_enabled=False, network_enabled=False,
        )
        full = PermissionProfile.full_access()
        selected = profiles or (default, full)
        self._profiles = {profile.name: profile for profile in selected}
        if len(self._profiles) != len(selected):
            raise ValueError("Permission profile names must be unique")
        self.full_access_enabled = full_access_enabled

    def select(self, name: str | None, *, dry_run: bool) -> PermissionProfile:
        selected = name or "restricted-dry-run"
        try:
            profile = self._profiles[selected]
        except KeyError as exc:
            raise PermissionError("Requested permission profile is not registered") from exc
        if not dry_run and (profile.name != "full-access" or not self.full_access_enabled):
            raise PermissionError("Non-dry-run execution requires operator-enabled full-access")
        return profile
