"""Tests for the on-disk runner profiles.

Two layers of coverage:
  1. Every profile YAML actually loads + validates against RunnerProfile.
     This catches typos and schema drift the moment they land.
  2. The full set of profiles matches what the factory registers, so a
     newly-registered runner without a profile fails CI loudly.
"""
from __future__ import annotations

import pytest

from app.runners.contracts import CertificationStatus
from app.runners.profile_loader import (
    PROFILES_DIR,
    load_all_profiles,
    load_profile,
    reset_cache,
)


# Reset the cache before every test so YAML edits between tests are picked up.
@pytest.fixture(autouse=True)
def _reset_profile_cache():
    reset_cache()
    yield
    reset_cache()


def test_profiles_directory_exists_and_has_yamls():
    assert PROFILES_DIR.is_dir(), f"profiles dir missing: {PROFILES_DIR}"
    yamls = list(PROFILES_DIR.glob("*.yaml"))
    assert len(yamls) >= 6, f"expected ≥6 profile YAMLs, found {len(yamls)}"


def test_every_profile_yaml_loads_cleanly():
    """If this fails, the message names the offending YAML — that's the point."""
    profiles = load_all_profiles()
    expected = {
        "jules",
        "claude_code",
        "codex_cli",
        "gemini_cli",
        "cursor_cli",
        "copilot_cli",
    }
    missing = expected - set(profiles.keys())
    assert not missing, f"missing runner profiles: {sorted(missing)}"


def test_profile_set_matches_factory_registry():
    """Catches the case where someone adds a new runner adapter but forgets
    the profile, or vice versa."""
    from app.runners.factory import RunnerFactory

    registered = {item["name"] for item in RunnerFactory.list_runners()}
    profiled = set(load_all_profiles().keys())

    unprofiled = registered - profiled
    unregistered = profiled - registered

    assert not unprofiled, (
        f"runners registered in factory but missing a profile YAML: {sorted(unprofiled)}"
    )
    assert not unregistered, (
        f"profile YAMLs exist for runners not in factory: {sorted(unregistered)}"
    )


def test_load_profile_by_name():
    profile = load_profile("claude_code")
    assert profile is not None
    assert profile.name == "claude_code"
    assert profile.default_command == "claude"


def test_load_profile_returns_none_for_unknown_name():
    assert load_profile("not_a_real_runner") is None


def test_copilot_profile_is_advisory_only():
    """Regression guard — if someone bumps copilot to certified by accident,
    routing changes silently and tasks start getting dispatched to a
    suggestion CLI. Make it loud."""
    profile = load_profile("copilot_cli")
    assert profile is not None
    assert profile.status == CertificationStatus.ADVISORY_ONLY
    assert profile.task_affinity == {}, (
        "copilot_cli must have empty task_affinity — non-empty would make it "
        "eligible for autonomous routing, which contradicts advisory_only"
    )


def test_jules_and_claude_code_are_certified():
    """The two reference runners for the protocol."""
    assert load_profile("jules").status == CertificationStatus.CERTIFIED
    assert load_profile("claude_code").status == CertificationStatus.CERTIFIED


def test_all_certified_profiles_have_some_task_affinity():
    """Empty task_affinity == ineligible for routing. A certified runner with
    no affinity is a profile bug."""
    for name, profile in load_all_profiles().items():
        if profile.status != CertificationStatus.CERTIFIED:
            continue
        assert profile.task_affinity, (
            f"certified runner {name!r} has empty task_affinity — would be "
            f"ineligible for autonomous routing"
        )
