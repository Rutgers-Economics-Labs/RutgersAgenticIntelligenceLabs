"""Load RunnerProfile YAMLs from packages/api/app/runners/profiles/.

Convention over registration: every *.yaml in the profiles/ directory is
loaded and validated. Adding a new runner profile = drop a YAML in the
folder; no Python changes needed.

Loaded profiles are cached at module level — they're effectively static
declarations, and reloading on every API request is wasteful. Tests
that need to reset the cache can call `reset_cache()`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.runners.contracts import RunnerProfile


PROFILES_DIR = Path(__file__).parent / "profiles"


class ProfileLoadError(Exception):
    """A YAML failed to parse or validate. Includes the path for grep-ability."""

    def __init__(self, path: Path, original: Exception):
        super().__init__(f"failed to load runner profile {path}: {original}")
        self.path = path
        self.original = original


def _load_one(path: Path) -> RunnerProfile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileLoadError(path, exc) from exc
    if not isinstance(raw, dict):
        raise ProfileLoadError(path, ValueError(f"top-level YAML is not a mapping: {type(raw).__name__}"))
    try:
        return RunnerProfile.model_validate(raw)
    except ValidationError as exc:
        raise ProfileLoadError(path, exc) from exc


@lru_cache(maxsize=1)
def load_all_profiles() -> dict[str, RunnerProfile]:
    """Return {runner_name: RunnerProfile} for every YAML in PROFILES_DIR.

    Cached for the process lifetime. Call `reset_cache()` in tests that
    need to swap profiles, or rely on `load_profile(name, fresh=True)`.
    """
    profiles: dict[str, RunnerProfile] = {}
    if not PROFILES_DIR.is_dir():
        return profiles
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        profile = _load_one(path)
        if profile.name in profiles:
            raise ProfileLoadError(
                path,
                ValueError(f"duplicate runner name {profile.name!r}; already loaded from a prior YAML"),
            )
        profiles[profile.name] = profile
    return profiles


def load_profile(name: str, *, fresh: bool = False) -> RunnerProfile | None:
    """Look up a profile by runner name. Returns None if not present.

    `fresh=True` skips the cache for this single call (still doesn't
    invalidate it). Useful in tests that want a guaranteed-current
    read after editing a YAML on disk.
    """
    if fresh:
        path = PROFILES_DIR / f"{name}.yaml"
        if not path.is_file():
            return None
        return _load_one(path)
    return load_all_profiles().get(name)


def reset_cache() -> None:
    """Drop the cached profile map. Tests only."""
    load_all_profiles.cache_clear()
