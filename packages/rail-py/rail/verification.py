"""
verification.py — Deterministic verification hooks for RAIL agent task completion.

Each hook implements a check appropriate for a specific layer (config, path policy,
hydration, execution, artifact, health).  The completion gate (completion_gate.py)
wires these hooks into planner and runner completion paths.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""


@dataclass
class VerificationResult:
    hook: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def __bool__(self) -> bool:
        return self.passed


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class VerificationHook(ABC):
    """Abstract base for all deterministic verification hooks."""

    name: str = "base"

    @abstractmethod
    def run(self, context: dict[str, Any]) -> VerificationResult:
        """Execute the hook and return a VerificationResult."""


# ---------------------------------------------------------------------------
# 1. Config Verification
# ---------------------------------------------------------------------------

class ConfigVerificationHook(VerificationHook):
    """Verify that YAML config files parse and pass schema validation."""

    name = "config_verification"

    _REQUIRED_FIELDS: dict[str, list[str]] = {
        "rail.yaml": ["version", "project", "paths", "hydration", "agents"],
        "agent": ["role", "label", "purpose", "runner", "permissions", "completion"],
        "source": ["id", "connector"],
        "pipeline": ["slug", "ontology"],
    }

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - file_path: str — path to the YAML file
          - file_type: str — "rail.yaml" | "agent" | "source" | "pipeline" (default: inferred)
          - repo_root: str — project root for resolving relative paths
        """
        checks: list[CheckResult] = []
        file_path = Path(context.get("file_path", ""))
        file_type = context.get("file_type") or _infer_file_type(file_path)

        # Parse check
        try:
            raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            checks.append(CheckResult("parse_succeeds", True))
        except Exception as exc:
            checks.append(CheckResult("parse_succeeds", False, str(exc)))
            return VerificationResult(self.name, False, checks)

        if not isinstance(raw, dict):
            checks.append(CheckResult("is_mapping", False, "YAML root must be a mapping"))
            return VerificationResult(self.name, False, checks)
        checks.append(CheckResult("is_mapping", True))

        # Required fields
        required = self._REQUIRED_FIELDS.get(file_type, [])
        for f in required:
            present = f in raw
            checks.append(CheckResult(f"field_{f}", present, "" if present else f"missing required field: {f!r}"))

        # Path fields must be repo-relative
        repo_root = context.get("repo_root")
        if repo_root and isinstance(raw.get("paths"), dict):
            for k, v in raw["paths"].items():
                if isinstance(v, str):
                    ok = not PurePosixPath(v).is_absolute() and ".." not in PurePosixPath(v).parts
                    checks.append(CheckResult(f"path_relative_{k}", ok, "" if ok else f"path {v!r} is not repo-relative"))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# 2. Path Policy Verification
# ---------------------------------------------------------------------------

class PathPolicyVerificationHook(VerificationHook):
    """Verify that modified files comply with agent write-path policy."""

    name = "path_policy_verification"

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - modified_paths: list[str] — repo-relative paths the runner modified
          - allowed_write_roots: list[str] — from agent YAML permissions.write
          - denied_paths: list[str] — from agent YAML permissions.deny
        """
        checks: list[CheckResult] = []
        modified: list[str] = context.get("modified_paths") or []
        allowed_roots: list[str] = context.get("allowed_write_roots") or []
        denied: list[str] = context.get("denied_paths") or []

        for path in modified:
            p = PurePosixPath(path)

            # Denied path check (deny overrides allow)
            denied_hit = any(_path_under(p, PurePosixPath(d)) for d in denied)
            if denied_hit:
                checks.append(CheckResult(
                    f"not_denied:{path}", False,
                    f"{path!r} is in a denied directory"
                ))
                continue

            # Must be under at least one allowed root
            in_allowed = any(_path_under(p, PurePosixPath(r)) for r in allowed_roots)
            checks.append(CheckResult(
                f"in_allowed_root:{path}", in_allowed,
                "" if in_allowed else f"{path!r} is outside declared write roots {allowed_roots}"
            ))

        if not checks:
            checks.append(CheckResult("no_writes", True, "no modified paths to check"))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# 3. Hydration Verification
# ---------------------------------------------------------------------------

class HydrationVerificationHook(VerificationHook):
    """Verify that a hydration dry-run succeeds and expected artifacts exist."""

    name = "hydration_verification"

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - yaml_valid: bool — True if YAML already validated upstream
          - dry_run_passed: bool — True if the pipeline dry-run succeeded
          - expected_artifact_paths: list[str] — paths that must exist after hydration
        """
        checks: list[CheckResult] = []

        yaml_valid = context.get("yaml_valid", False)
        checks.append(CheckResult("yaml_valid", bool(yaml_valid), "" if yaml_valid else "YAML validation failed"))

        dry_run_passed = context.get("dry_run_passed", False)
        checks.append(CheckResult("dry_run_passed", bool(dry_run_passed), "" if dry_run_passed else "dry run failed"))

        for p in context.get("expected_artifact_paths") or []:
            exists = Path(p).exists()
            checks.append(CheckResult(f"artifact_exists:{p}", exists, "" if exists else f"missing artifact: {p!r}"))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# 4. Execution Verification
# ---------------------------------------------------------------------------

class ExecutionVerificationHook(VerificationHook):
    """Verify coding-agent script execution: no fatal errors, outputs present."""

    name = "execution_verification"

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - execution_succeeded: bool — True if script ran without fatal errors
          - expected_output_paths: list[str] — output files that must exist
          - allowed_write_roots: list[str] — outputs must land here
        """
        checks: list[CheckResult] = []

        ok = context.get("execution_succeeded", False)
        checks.append(CheckResult("execution_succeeded", bool(ok), "" if ok else "execution had a fatal error"))

        allowed_roots: list[str] = context.get("allowed_write_roots") or []
        for p in context.get("expected_output_paths") or []:
            exists = Path(p).exists()
            checks.append(CheckResult(f"output_exists:{p}", exists, "" if exists else f"missing output: {p!r}"))
            if exists and allowed_roots:
                pp = PurePosixPath(p)
                in_allowed = any(_path_under(pp, PurePosixPath(r)) for r in allowed_roots)
                checks.append(CheckResult(
                    f"output_in_allowed_root:{p}", in_allowed,
                    "" if in_allowed else f"{p!r} is outside declared write roots"
                ))

        if not checks:
            checks.append(CheckResult("no_outputs_declared", False, "no expected_output_paths declared — required for coding tasks"))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# 5. Artifact Verification
# ---------------------------------------------------------------------------

class ArtifactVerificationHook(VerificationHook):
    """Verify that artifact outputs exist, are renderable, and follow path policy."""

    name = "artifact_verification"

    _RENDERABLE_SUFFIXES: frozenset[str] = frozenset(
        [".md", ".html", ".pdf", ".png", ".jpg", ".svg", ".json", ".csv"]
    )

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - artifact_paths: list[str] — declared artifact output paths
          - allowed_write_roots: list[str] — e.g. ["artifacts"]
          - manifest_updated: bool — True if index metadata was updated
        """
        checks: list[CheckResult] = []

        allowed_roots: list[str] = context.get("allowed_write_roots") or []
        for p in context.get("artifact_paths") or []:
            path = Path(p)
            exists = path.exists()
            checks.append(CheckResult(f"artifact_exists:{p}", exists, "" if exists else f"missing artifact: {p!r}"))

            if exists:
                renderable = path.suffix.lower() in self._RENDERABLE_SUFFIXES
                checks.append(CheckResult(
                    f"artifact_renderable:{p}", renderable,
                    "" if renderable else f"unrecognised artifact format: {path.suffix!r}"
                ))

            if allowed_roots:
                pp = PurePosixPath(p)
                in_allowed = any(_path_under(pp, PurePosixPath(r)) for r in allowed_roots)
                checks.append(CheckResult(
                    f"artifact_in_allowed_root:{p}", in_allowed,
                    "" if in_allowed else f"{p!r} is outside declared artifact roots"
                ))

        manifest_updated = context.get("manifest_updated", True)
        checks.append(CheckResult(
            "manifest_updated", bool(manifest_updated),
            "" if manifest_updated else "artifact index/manifest was not updated"
        ))

        if not checks:
            checks.append(CheckResult("no_artifacts_declared", False, "no artifact_paths declared — required for artifact tasks"))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# 6. Health Verification
# ---------------------------------------------------------------------------

class HealthVerificationHook(VerificationHook):
    """Verify health-agent runs: report exists, cleanup log exists, no unsafe writes."""

    name = "health_verification"

    def run(self, context: dict[str, Any]) -> VerificationResult:
        """
        context keys:
          - verification_report_path: str
          - cleanup_log_path: str
          - skill_review_recorded: bool
          - disallowed_write_paths: list[str] — paths that should NOT have been touched
        """
        checks: list[CheckResult] = []

        for key, label in [
            ("verification_report_path", "verification_report_exists"),
            ("cleanup_log_path", "cleanup_log_exists"),
        ]:
            p = context.get(key)
            if p:
                exists = Path(p).exists()
                checks.append(CheckResult(label, exists, "" if exists else f"missing: {p!r}"))
            else:
                checks.append(CheckResult(label, False, f"{key} not provided"))

        skill_review = context.get("skill_review_recorded", True)
        checks.append(CheckResult(
            "skill_review_recorded", bool(skill_review),
            "" if skill_review else "skill review actions were not recorded"
        ))

        for p in context.get("disallowed_write_paths") or []:
            checks.append(CheckResult(
                f"disallowed_path_clean:{p}", False,
                f"health agent modified a disallowed path: {p!r}"
            ))

        passed = all(c.passed for c in checks)
        return VerificationResult(self.name, passed, checks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_file_type(path: Path) -> str:
    name = path.name
    if name == "rail.yaml":
        return "rail.yaml"
    parts = path.parts
    if "agents" in parts:
        return "agent"
    if "sources" in parts:
        return "source"
    if "pipelines" in parts:
        return "pipeline"
    return "generic"


def _path_under(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return True if *path* is *root* or descends from it."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
