"""
Tests for rail.verification — WO-F8.4

Covers all six deterministic verification hooks:
  - CheckResult / VerificationResult data types
  - ConfigVerificationHook
  - PathPolicyVerificationHook
  - HydrationVerificationHook
  - ExecutionVerificationHook
  - ArtifactVerificationHook
  - HealthVerificationHook
  - Internal helpers: _infer_file_type, _path_under
"""
from __future__ import annotations

import pytest
from pathlib import Path, PurePosixPath

import yaml

from rail.verification import (
    CheckResult,
    VerificationResult,
    ConfigVerificationHook,
    PathPolicyVerificationHook,
    HydrationVerificationHook,
    ExecutionVerificationHook,
    ArtifactVerificationHook,
    HealthVerificationHook,
    _infer_file_type,
    _path_under,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TestCheckResult:
    def test_passed_check(self):
        c = CheckResult("parse_succeeds", True)
        assert c.passed is True
        assert c.name == "parse_succeeds"

    def test_failed_check_with_message(self):
        c = CheckResult("field_version", False, "missing required field: 'version'")
        assert c.passed is False
        assert "version" in c.message


class TestVerificationResult:
    def test_bool_true_when_passed(self):
        vr = VerificationResult("hook", True)
        assert bool(vr) is True

    def test_bool_false_when_failed(self):
        vr = VerificationResult("hook", False)
        assert bool(vr) is False

    def test_failures_returns_only_failed_checks(self):
        vr = VerificationResult("hook", False, [
            CheckResult("ok", True),
            CheckResult("bad", False, "oops"),
        ])
        failures = vr.failures
        assert len(failures) == 1
        assert failures[0].name == "bad"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestInferFileType:
    def test_rail_yaml(self):
        assert _infer_file_type(Path("rail.yaml")) == "rail.yaml"

    def test_agents_dir(self):
        assert _infer_file_type(Path("agents/worker.yaml")) == "agent"

    def test_sources_dir(self):
        assert _infer_file_type(Path("sources/bls.yaml")) == "source"

    def test_pipelines_dir(self):
        assert _infer_file_type(Path("pipelines/unemployment.yaml")) == "pipeline"

    def test_unknown(self):
        assert _infer_file_type(Path("foo.yaml")) == "generic"


class TestPathUnder:
    def test_exact_root_match(self):
        assert _path_under(PurePosixPath("artifacts"), PurePosixPath("artifacts")) is True

    def test_child_path(self):
        assert _path_under(PurePosixPath("artifacts/report.md"), PurePosixPath("artifacts")) is True

    def test_sibling_not_under(self):
        assert _path_under(PurePosixPath("research_plan/x.md"), PurePosixPath("artifacts")) is False

    def test_nested_child(self):
        assert _path_under(PurePosixPath("a/b/c/d.txt"), PurePosixPath("a/b")) is True


# ---------------------------------------------------------------------------
# ConfigVerificationHook
# ---------------------------------------------------------------------------

class TestConfigVerificationHook:
    hook = ConfigVerificationHook()

    def test_valid_rail_yaml_passes(self, tmp_path):
        config = {
            "version": "1",
            "project": "my-project",
            "paths": {"data": "data/", "artifacts": "artifacts/"},
            "hydration": {"schedule": "weekly"},
            "agents": [{"role": "planner"}],
        }
        p = tmp_path / "rail.yaml"
        p.write_text(yaml.dump(config))
        result = self.hook.run({"file_path": str(p), "file_type": "rail.yaml"})
        assert result.passed, [c.message for c in result.failures]

    def test_missing_required_field_fails(self, tmp_path):
        config = {"version": "1"}  # missing project, paths, hydration, agents
        p = tmp_path / "rail.yaml"
        p.write_text(yaml.dump(config))
        result = self.hook.run({"file_path": str(p), "file_type": "rail.yaml"})
        assert not result.passed
        failure_names = [c.name for c in result.failures]
        assert "field_project" in failure_names

    def test_invalid_yaml_fails(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(": invalid: yaml: [\n")
        result = self.hook.run({"file_path": str(p), "file_type": "rail.yaml"})
        assert not result.passed
        assert any(c.name == "parse_succeeds" for c in result.failures)

    def test_absolute_path_in_paths_fails(self, tmp_path):
        config = {
            "version": "1",
            "project": "x",
            "paths": {"data": "/absolute/path"},
            "hydration": {},
            "agents": [],
        }
        p = tmp_path / "rail.yaml"
        p.write_text(yaml.dump(config))
        result = self.hook.run({
            "file_path": str(p),
            "file_type": "rail.yaml",
            "repo_root": str(tmp_path),
        })
        assert not result.passed
        assert any("path_relative_data" in c.name for c in result.failures)

    def test_agent_yaml_required_fields(self, tmp_path):
        agent = {
            "role": "data",
            "label": "Data Agent",
            "purpose": "Ingest data",
            "runner": "codex_cli",
            "permissions": {"write": ["artifacts/"]},
            "completion": {"criteria": []},
        }
        p = tmp_path / "agents" / "data_agent.yaml"
        p.parent.mkdir(parents=True)
        p.write_text(yaml.dump(agent))
        result = self.hook.run({"file_path": str(p), "file_type": "agent"})
        assert result.passed, [c.message for c in result.failures]

    def test_non_mapping_root_fails(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- foo\n- bar\n")
        result = self.hook.run({"file_path": str(p)})
        assert not result.passed
        assert any(c.name == "is_mapping" for c in result.failures)

    def test_valid_source_config_passes(self, tmp_path):
        p = tmp_path / "sources" / "source.yaml"
        p.parent.mkdir(parents=True)
        p.write_text(yaml.dump({
            "name": "qcew",
            "type": "csv",
            "path": "topics/data/raw/qcew/file.csv",
            "description": "Public source",
            "fields": [{"source": "area_fips", "alias": "county_fips"}],
        }))
        result = self.hook.run({"file_path": str(p)})
        assert result.passed, [c.message for c in result.failures]

    def test_placeholder_source_config_fails(self, tmp_path):
        p = tmp_path / "sources" / "source.yaml"
        p.parent.mkdir(parents=True)
        p.write_text(yaml.dump({
            "name": "placeholder",
            "type": "api",
            "url": "https://example.com/review-required",
            "description": "Draft source for review\nReadiness: missing_auth_or_manual",
            "fields": [{"source": "id", "alias": "id"}],
        }))
        result = self.hook.run({"file_path": str(p)})
        assert not result.passed
        failure_names = [c.name for c in result.failures]
        assert "source_not_placeholder_url" in failure_names
        assert "source_not_review_required" in failure_names


# ---------------------------------------------------------------------------
# PathPolicyVerificationHook
# ---------------------------------------------------------------------------

class TestPathPolicyVerificationHook:
    hook = PathPolicyVerificationHook()

    def test_all_paths_in_allowed_roots_passes(self):
        result = self.hook.run({
            "modified_paths": ["artifacts/report.md", "research_plan/x.md"],
            "allowed_write_roots": ["artifacts", "research_plan"],
            "denied_paths": [],
        })
        assert result.passed, [c.message for c in result.failures]

    def test_path_outside_allowed_roots_fails(self):
        result = self.hook.run({
            "modified_paths": ["packages/api/secret.py"],
            "allowed_write_roots": ["artifacts"],
            "denied_paths": [],
        })
        assert not result.passed

    def test_denied_path_fails(self):
        result = self.hook.run({
            "modified_paths": ["packages/api/config.py"],
            "allowed_write_roots": ["packages"],
            "denied_paths": ["packages/api"],
        })
        assert not result.passed
        assert any("denied" in c.message for c in result.failures)

    def test_empty_modified_paths_passes(self):
        result = self.hook.run({
            "modified_paths": [],
            "allowed_write_roots": ["artifacts"],
            "denied_paths": [],
        })
        assert result.passed

    def test_no_allowed_roots_fails_on_any_write(self):
        result = self.hook.run({
            "modified_paths": ["foo.md"],
            "allowed_write_roots": [],
            "denied_paths": [],
        })
        assert not result.passed


# ---------------------------------------------------------------------------
# HydrationVerificationHook
# ---------------------------------------------------------------------------

class TestHydrationVerificationHook:
    hook = HydrationVerificationHook()

    def test_all_passing_context(self, tmp_path):
        artifact = tmp_path / "output.db"
        artifact.write_text("data")
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
            "expected_artifact_paths": [str(artifact)],
        })
        assert result.passed, [c.message for c in result.failures]

    def test_yaml_invalid_fails(self, tmp_path):
        result = self.hook.run({
            "yaml_valid": False,
            "dry_run_passed": True,
            "expected_artifact_paths": [],
        })
        assert not result.passed
        assert any(c.name == "yaml_valid" for c in result.failures)

    def test_dry_run_failed_fails(self):
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": False,
            "expected_artifact_paths": [],
        })
        assert not result.passed
        assert any(c.name == "dry_run_passed" for c in result.failures)

    def test_missing_artifact_fails(self, tmp_path):
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
            "expected_artifact_paths": [str(tmp_path / "missing.db")],
        })
        assert not result.passed

    def test_no_expected_artifacts_passes_if_yaml_and_dry_run_ok(self):
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
            "expected_artifact_paths": [],
        })
        assert result.passed


# ---------------------------------------------------------------------------
# ExecutionVerificationHook
# ---------------------------------------------------------------------------

class TestExecutionVerificationHook:
    hook = ExecutionVerificationHook()

    def test_success_with_output_in_allowed_root(self, tmp_path):
        output = tmp_path / "artifacts" / "result.csv"
        output.parent.mkdir()
        output.write_text("a,b\n1,2\n")
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [str(output)],
            "allowed_write_roots": [str(tmp_path / "artifacts")],
        })
        assert result.passed, [c.message for c in result.failures]

    def test_execution_failed_fails(self, tmp_path):
        result = self.hook.run({
            "execution_succeeded": False,
            "expected_output_paths": [],
            "allowed_write_roots": [],
        })
        assert not result.passed
        assert any(c.name == "execution_succeeded" for c in result.failures)

    def test_missing_output_fails(self, tmp_path):
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [str(tmp_path / "missing.csv")],
            "allowed_write_roots": [],
        })
        assert not result.passed

    def test_no_expected_outputs_with_failed_execution_fails(self):
        """With no outputs and failed execution, hook fails on execution_succeeded."""
        result = self.hook.run({
            "execution_succeeded": False,
            "expected_output_paths": [],
            "allowed_write_roots": [],
        })
        assert not result.passed
        assert any(c.name == "execution_succeeded" for c in result.failures)

    def test_empty_outputs_with_success_fails_no_outputs_declared(self):
        """Coding tasks must declare their outputs. A successful execution
        with no expected_output_paths is treated as a fabrication risk
        (the agent claimed success but didn't say what it produced) — the
        hook records a `no_outputs_declared` failure. This matches the
        rail-py-side test_no_outputs_declared_fails."""
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [],
            "allowed_write_roots": [],
        })
        assert not result.passed
        assert any(c.name == "no_outputs_declared" for c in result.checks)

    def test_output_outside_allowed_root_fails(self, tmp_path):
        output = tmp_path / "secret.py"
        output.write_text("code")
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [str(output)],
            "allowed_write_roots": [str(tmp_path / "artifacts")],
        })
        assert not result.passed
        assert any("outside declared write roots" in c.message for c in result.failures)


# ---------------------------------------------------------------------------
# ArtifactVerificationHook
# ---------------------------------------------------------------------------

class TestArtifactVerificationHook:
    hook = ArtifactVerificationHook()

    def test_existing_renderable_artifact_passes(self, tmp_path):
        art = tmp_path / "artifacts" / "report.md"
        art.parent.mkdir()
        art.write_text("# Report")
        result = self.hook.run({
            "artifact_paths": [str(art)],
            "allowed_write_roots": [str(tmp_path / "artifacts")],
            "manifest_updated": True,
        })
        assert result.passed, [c.message for c in result.failures]

    def test_missing_artifact_fails(self, tmp_path):
        result = self.hook.run({
            "artifact_paths": [str(tmp_path / "missing.md")],
            "allowed_write_roots": [],
            "manifest_updated": True,
        })
        assert not result.passed

    def test_unrenderable_format_fails(self, tmp_path):
        art = tmp_path / "data.bin"
        art.write_bytes(b"\x00\x01\x02")
        result = self.hook.run({
            "artifact_paths": [str(art)],
            "allowed_write_roots": [],
            "manifest_updated": True,
        })
        assert not result.passed
        assert any("unrecognised artifact format" in c.message for c in result.failures)

    def test_manifest_not_updated_fails(self, tmp_path):
        art = tmp_path / "report.md"
        art.write_text("# x")
        result = self.hook.run({
            "artifact_paths": [str(art)],
            "allowed_write_roots": [],
            "manifest_updated": False,
        })
        assert not result.passed
        assert any(c.name == "manifest_updated" for c in result.failures)

    def test_no_artifacts_with_manifest_updated_fails_no_artifacts_declared(self):
        """Artifact tasks must declare their artifacts. Updating the manifest
        without actually listing what was produced is treated as a fabrication
        risk — the hook records a `no_artifacts_declared` failure. The
        manifest_updated check still passes individually, but the overall
        hook fails. This matches the strict anti-fabrication contract."""
        result = self.hook.run({
            "artifact_paths": [],
            "allowed_write_roots": [],
            "manifest_updated": True,
        })
        assert not result.passed
        assert any(c.name == "no_artifacts_declared" for c in result.checks)
        assert any(c.name == "manifest_updated" and c.passed for c in result.checks)

    def test_no_artifacts_with_manifest_not_updated_fails(self):
        """When artifact_paths is empty and manifest not updated, hook fails."""
        result = self.hook.run({
            "artifact_paths": [],
            "allowed_write_roots": [],
            "manifest_updated": False,
        })
        assert not result.passed
        assert any(c.name == "manifest_updated" for c in result.failures)

    def test_renderable_formats(self, tmp_path):
        for suffix in [".md", ".html", ".pdf", ".png", ".jpg", ".svg", ".json", ".csv"]:
            art = tmp_path / f"file{suffix}"
            art.write_bytes(b"data")
            result = self.hook.run({
                "artifact_paths": [str(art)],
                "allowed_write_roots": [],
                "manifest_updated": True,
            })
            renderable_checks = [c for c in result.checks if "renderable" in c.name]
            assert renderable_checks[0].passed, f"Expected {suffix} to be renderable"


# ---------------------------------------------------------------------------
# HealthVerificationHook
# ---------------------------------------------------------------------------

class TestHealthVerificationHook:
    hook = HealthVerificationHook()

    def test_all_checks_present_passes(self, tmp_path):
        report = tmp_path / "verification_report.md"
        report.write_text("# Report")
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("cleaned")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
            "disallowed_write_paths": [],
        })
        assert result.passed, [c.message for c in result.failures]

    def test_missing_verification_report_fails(self, tmp_path):
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("cleaned")
        result = self.hook.run({
            "verification_report_path": str(tmp_path / "missing.md"),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
            "disallowed_write_paths": [],
        })
        assert not result.passed
        assert any(c.name == "verification_report_exists" for c in result.failures)

    def test_missing_cleanup_log_fails(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("x")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(tmp_path / "missing.log"),
            "skill_review_recorded": True,
            "disallowed_write_paths": [],
        })
        assert not result.passed

    def test_skill_review_not_recorded_fails(self, tmp_path):
        report = tmp_path / "r.md"
        report.write_text("x")
        cleanup = tmp_path / "c.log"
        cleanup.write_text("x")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": False,
            "disallowed_write_paths": [],
        })
        assert not result.passed
        assert any(c.name == "skill_review_recorded" for c in result.failures)

    def test_disallowed_write_path_fails(self, tmp_path):
        report = tmp_path / "r.md"
        report.write_text("x")
        cleanup = tmp_path / "c.log"
        cleanup.write_text("x")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
            "disallowed_write_paths": ["packages/api/secret.py"],
        })
        assert not result.passed
        assert any("disallowed path" in c.message for c in result.failures)

    def test_no_paths_provided_fails(self):
        result = self.hook.run({
            "skill_review_recorded": True,
            "disallowed_write_paths": [],
        })
        assert not result.passed
