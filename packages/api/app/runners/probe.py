"""Runner probe — dynamic readiness checks layered on top of static profiles.

Cheap by design. Probes run on operator request and on autopilot startup;
they cannot make outbound API calls that cost money, and they cannot
block for more than a few seconds. If a check needs an expensive
verification (e.g. "really launch a session and verify it edits a file"),
that belongs in a separate certification flow, not the per-tick probe.

Checks in this pass:
  - installed: is the command on PATH (or for hosted runners, are the
    required credentials present)?
  - authenticated: does a trivial auth-required call succeed? Best-effort
    only; skipped if we can't verify cheaply.
  - version: best-effort string from `<cmd> --version` if available.

Future passes (Phase 2+) may add:
  - mcp_available: does the runner currently have a working MCP config?
  - trivial_session: can we spawn a session that edits one file?
  - structured_output: does the runner emit a parseable session_result?
"""
from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.runners.contracts import CertificationStatus, RunnerProfile
from app.runners.profile_loader import load_all_profiles, load_profile


# Hard ceiling for any individual subprocess probe. Operator-triggered or
# autopilot-tick probes must not stall the UI / event loop.
PROBE_SUBPROCESS_TIMEOUT_SECONDS = 3.0


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    """Couldn't check cheaply — not a failure, just inconclusive."""
    UNKNOWN = "unknown"


class ReadinessLevel(str, Enum):
    GREEN = "green"
    """Installed, authenticated, ready to dispatch."""
    YELLOW = "yellow"
    """Installed but needs operator setup (auth missing, MCP unconfigured,
    or runner is advisory_only by design)."""
    RED = "red"
    """Not installed or hard failure."""


class ProbeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CheckStatus
    detail: str | None = None


class ProbeResult(BaseModel):
    """One probe run for one runner. Includes both probe checks and a
    summarized readiness level the UI can render directly."""

    model_config = ConfigDict(extra="forbid")

    runner_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    installed: ProbeCheck
    authenticated: ProbeCheck
    version: str | None = None
    readiness: ReadinessLevel
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-runner probe strategies
# ---------------------------------------------------------------------------

async def _probe_subprocess_version(command: str, args: tuple[str, ...] = ("--version",)) -> tuple[CheckStatus, str | None]:
    """Run `command args` with a tight timeout, return (status, stdout_first_line).

    Used by every local_cli probe to verify the binary is responsive. Treats
    non-zero exits as fail; treats timeout as skip (the binary exists but we
    couldn't confirm liveness in time).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return CheckStatus.FAIL, None
    except Exception as exc:
        return CheckStatus.FAIL, str(exc)
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=PROBE_SUBPROCESS_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        return CheckStatus.SKIP, "probe timed out"
    if proc.returncode != 0:
        # Some CLIs print version to stderr — try that before declaring fail.
        stderr_line = (stderr_b.decode("utf-8", errors="replace").splitlines() or [""])[0].strip()
        if stderr_line:
            return CheckStatus.PASS, stderr_line
        return CheckStatus.FAIL, f"exit code {proc.returncode}"
    stdout_line = (stdout_b.decode("utf-8", errors="replace").splitlines() or [""])[0].strip()
    return CheckStatus.PASS, stdout_line or None


async def _probe_local_cli(profile: RunnerProfile) -> ProbeResult:
    """Probe a local_cli runner: command present? version reachable?

    Authentication is deliberately skipped here — most CLIs don't expose a
    cheap auth check, and we don't want to make API calls during probes.
    A "yellow" readiness level is used when the binary is present but we
    can't confirm auth, which is the truthful state.
    """
    command_str = profile.default_command or profile.name
    # Some commands are multi-word ("gh copilot suggest"); resolve the first
    # token for the PATH lookup but use the full string for invocation.
    first_token = command_str.split()[0]
    notes: list[str] = []

    binary_path = shutil.which(first_token)
    if binary_path is None:
        return ProbeResult(
            runner_name=profile.name,
            installed=ProbeCheck(status=CheckStatus.FAIL, detail=f"{first_token!r} not on PATH"),
            authenticated=ProbeCheck(status=CheckStatus.SKIP, detail="command not installed"),
            version=None,
            readiness=ReadinessLevel.RED,
            notes=[f"install {first_token} and put it on PATH"],
        )

    installed = ProbeCheck(status=CheckStatus.PASS, detail=binary_path)

    # `gh copilot suggest` is a subcommand chain, not a binary that responds
    # to --version. Probing `gh --version` is the safe equivalent.
    version_args: tuple[str, ...] = ("--version",)
    version_command = first_token

    version_status, version_line = await _probe_subprocess_version(version_command, version_args)
    version_string: str | None = None
    if version_status == CheckStatus.PASS:
        version_string = version_line
    elif version_status == CheckStatus.SKIP:
        notes.append("could not confirm version within probe timeout")
    else:
        notes.append(f"version check failed: {version_line}")

    # Authentication: we don't make API calls here. Mark as SKIP so the UI
    # surfaces the gap honestly rather than implying we verified it.
    authenticated = ProbeCheck(
        status=CheckStatus.SKIP,
        detail="auth not probed (avoids outbound API calls); verify with `<command> /auth` or equivalent",
    )

    # Readiness:
    #  - advisory_only profiles are always yellow regardless of install state
    #    (they're installed for advisory use, not autonomous dispatch)
    #  - installed + version PASS = green-ish, but we downgrade to yellow when
    #    we couldn't confirm auth, since "installed but not logged in" is the
    #    most common operator gap
    if profile.status == CertificationStatus.ADVISORY_ONLY:
        readiness = ReadinessLevel.YELLOW
        notes.append("advisory_only — not eligible for autonomous routing")
    elif version_status == CheckStatus.PASS:
        readiness = ReadinessLevel.YELLOW
        notes.append("installed and responsive; auth not verified in probe")
    elif version_status == CheckStatus.SKIP:
        readiness = ReadinessLevel.YELLOW
    else:
        readiness = ReadinessLevel.RED

    return ProbeResult(
        runner_name=profile.name,
        installed=installed,
        authenticated=authenticated,
        version=version_string,
        readiness=readiness,
        notes=notes,
    )


async def _probe_hosted_api(profile: RunnerProfile) -> ProbeResult:
    """Probe a hosted_api runner: are credentials in the environment?

    Only Jules at present. The credential env var is hardcoded here because
    it's well-known and the profile YAML doesn't yet have a `credentials`
    field — a future iteration could lift it into the profile.
    """
    notes: list[str] = []
    if profile.name == "jules":
        api_key = os.environ.get("JULES_API_KEY") or ""
        if api_key:
            return ProbeResult(
                runner_name=profile.name,
                installed=ProbeCheck(status=CheckStatus.PASS, detail="JULES_API_KEY present"),
                authenticated=ProbeCheck(
                    status=CheckStatus.SKIP,
                    detail="auth not probed (avoids outbound API calls); first dispatch will surface auth errors",
                ),
                version=None,
                readiness=ReadinessLevel.YELLOW,
                notes=["credentials present; auth verified on first dispatch"],
            )
        return ProbeResult(
            runner_name=profile.name,
            installed=ProbeCheck(status=CheckStatus.FAIL, detail="JULES_API_KEY not set"),
            authenticated=ProbeCheck(status=CheckStatus.SKIP, detail="no credentials to probe"),
            version=None,
            readiness=ReadinessLevel.RED,
            notes=["set JULES_API_KEY in environment to enable this runner"],
        )

    # Generic hosted_api with no specific credential check.
    return ProbeResult(
        runner_name=profile.name,
        installed=ProbeCheck(
            status=CheckStatus.UNKNOWN,
            detail="generic hosted_api probe; no credential check defined",
        ),
        authenticated=ProbeCheck(status=CheckStatus.SKIP),
        version=None,
        readiness=ReadinessLevel.YELLOW,
        notes=["no profile-specific credential check; add one in probe.py"],
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def probe_runner(name: str) -> ProbeResult | None:
    """Probe one runner by name. Returns None if no profile exists."""
    profile = load_profile(name)
    if profile is None:
        return None
    if profile.adapter.value == "local_cli":
        return await _probe_local_cli(profile)
    if profile.adapter.value == "hosted_api":
        return await _probe_hosted_api(profile)
    # attached_ide or any new adapter type — treat as not-probable-yet.
    return ProbeResult(
        runner_name=profile.name,
        installed=ProbeCheck(
            status=CheckStatus.UNKNOWN,
            detail=f"no probe strategy for adapter type {profile.adapter.value!r}",
        ),
        authenticated=ProbeCheck(status=CheckStatus.SKIP),
        version=None,
        readiness=ReadinessLevel.YELLOW,
        notes=[f"add a probe strategy for adapter type {profile.adapter.value!r}"],
    )


async def probe_all() -> dict[str, ProbeResult]:
    """Probe every runner that has a profile. Concurrent."""
    profiles = load_all_profiles()
    if not profiles:
        return {}
    names = list(profiles.keys())
    results = await asyncio.gather(*[probe_runner(name) for name in names])
    return {name: result for name, result in zip(names, results) if result is not None}
