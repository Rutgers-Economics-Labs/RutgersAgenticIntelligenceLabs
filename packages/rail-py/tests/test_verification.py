"""
Tests for WO-F8.3 — Deterministic verification hooks.

Covers all six hooks:
  - ConfigVerificationHook
  - PathPolicyVerificationHook
  - HydrationVerificationHook
  - ExecutionVerificationHook
  - ArtifactVerificationHook
  - HealthVerificationHook

And internal helpers:
  - _infer_file_type
  - _path_under
"""
from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

import pytest

from rail.verification import (
    ArtifactVerificationHook,
    CheckResult,
    ConfigVerificationHook,
    ExecutionVerificationHook,
    HealthVerificationHook,
    HydrationVerificationHook,
    PathPolicyVerificationHook,
    VerificationResult,
    _infer_file_type,
    _path_under,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_RAIL_YAML = textwrap.dedent("""\
    version: 1
    project:
      name: Test
      slug: test
    paths:
      ontology_root: ".ontology"
      topics_root: "topics"
    hydration:
      ontology_file: ".ontology/ontology.yaml"
      sources_dir: ".ontology/sources"
      pipelines_dir: ".ontology/pipelines"
    agents:
      roles_dir: "agents"
""")

VALID_AGENT_YAML = textwrap.dedent("""\
    role: data
    label: Data Agent
    purpose: Hydrate the ontology
    runner: jules
    permissions:
      write: ["artifacts"]
    completion:
      required_hooks: [hydration_verification]
""")


@pytest.fixture
def tmp_rail_yaml(tmp_path: Path) -> Path:
    f = tmp_path / "rail.yaml"
    f.write_text(VALID_RAIL_YAML, encoding="utf-8")
    return f


@pytest.fixture
def tmp_agent_yaml(tmp_path: Path) -> Path:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    f = agents_dir / "data.yaml"
    f.write_text(VALID_AGENT_YAML, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _infer_file_type
# ---------------------------------------------------------------------------

class TestInferFileType:
    def test_rail_yaml(self):
        assert _infer_file_type(Path("some/path/rail.yaml")) == "rail.yaml"

    def test_agents_directory(self):
        assert _infer_file_type(Path("agents/data.yaml")) == "agent"

    def test_sources_directory(self):
        assert _infer_file_type(Path("sources/census.yaml")) == "source"

    def test_pipelines_directory(self):
        assert _infer_file_type(Path("pipelines/main.yaml")) == "pipeline"

    def test_generic_fallback(self):
        assert _infer_file_type(Path("config/something.yaml")) == "generic"


# ---------------------------------------------------------------------------
# _path_under
# ---------------------------------------------------------------------------

class TestPathUnder:
    def test_exact_match(self):
        assert _path_under(PurePosixPath("artifacts"), PurePosixPath("artifacts"))

    def test_child_path(self):
        assert _path_under(PurePosixPath("artifacts/report.md"), PurePosixPath("artifacts"))

    def test_nested_child(self):
        assert _path_under(PurePosixPath("artifacts/sub/deep/file.pdf"), PurePosixPath("artifacts"))

    def test_not_under_sibling(self):
        assert not _path_under(PurePosixPath("outputs/file.md"), PurePosixPath("artifacts"))

    def test_not_under_partial_prefix(self):
        # "artifacts_extra" should NOT be under "artifacts"
        assert not _path_under(PurePosixPath("artifacts_extra/file.md"), PurePosixPath("artifacts"))


# ---------------------------------------------------------------------------
# VerificationResult helpers
# ---------------------------------------------------------------------------

class TestVerificationResult:
    def test_failures_property(self):
        checks = [
            CheckResult("a", True),
            CheckResult("b", False, "bad"),
            CheckResult("c", True),
        ]
        result = VerificationResult("hook", False, checks)
        assert len(result.failures) == 1
        assert result.failures[0].name == "b"

    def test_bool_true(self):
        r = VerificationResult("h", True)
        assert bool(r) is True

    def test_bool_false(self):
        r = VerificationResult("h", False)
        assert bool(r) is False


# ---------------------------------------------------------------------------
# ConfigVerificationHook
# ---------------------------------------------------------------------------

class TestConfigVerificationHook:
    hook = ConfigVerificationHook()

    def test_valid_rail_yaml_passes(self, tmp_rail_yaml):
        result = self.hook.run({"file_path": str(tmp_rail_yaml), "file_type": "rail.yaml"})
        assert result.passed, result.failures

    def test_valid_agent_yaml_passes(self, tmp_agent_yaml):
        result = self.hook.run({"file_path": str(tmp_agent_yaml), "file_type": "agent"})
        assert result.passed, result.failures

    def test_missing_file_fails(self, tmp_path):
        result = self.hook.run({"file_path": str(tmp_path / "nonexistent.yaml")})
        assert not result.passed
        assert any(not c.passed and c.name == "parse_succeeds" for c in result.checks)

    def test_non_mapping_root_fails(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        result = self.hook.run({"file_path": str(bad), "file_type": "rail.yaml"})
        assert not result.passed

    def test_missing_required_field_fails(self, tmp_path):
        # rail.yaml missing "agents" field
        content = VALID_RAIL_YAML.replace("agents:\n  roles_dir: agents\n", "")
        f = tmp_path / "rail.yaml"
        f.write_text(content, encoding="utf-8")
        result = self.hook.run({"file_path": str(f), "file_type": "rail.yaml"})
        assert not result.passed
        assert any("agents" in c.name and not c.passed for c in result.checks)

    def test_absolute_path_in_paths_fails(self, tmp_path):
        content = VALID_RAIL_YAML.replace(
            'ontology_root: ".ontology"', 'ontology_root: "/absolute/path"'
        )
        f = tmp_path / "rail.yaml"
        f.write_text(content, encoding="utf-8")
        result = self.hook.run({
            "file_path": str(f),
            "file_type": "rail.yaml",
            "repo_root": str(tmp_path),
        })
        assert not result.passed
        assert any("path_relative" in c.name and not c.passed for c in result.checks)

    def test_relative_paths_pass(self, tmp_rail_yaml, tmp_path):
        result = self.hook.run({
            "file_path": str(tmp_rail_yaml),
            "file_type": "rail.yaml",
            "repo_root": str(tmp_path),
        })
        assert result.passed, result.failures

    def test_inferred_file_type_rail_yaml(self, tmp_path):
        f = tmp_path / "rail.yaml"
        f.write_text(VALID_RAIL_YAML, encoding="utf-8")
        result = self.hook.run({"file_path": str(f)})  # no file_type — inferred
        assert result.passed, result.failures


# ---------------------------------------------------------------------------
# PathPolicyVerificationHook
# ---------------------------------------------------------------------------

class TestPathPolicyVerificationHook:
    hook = PathPolicyVerificationHook()

    def test_empty_modified_paths_passes(self):
        result = self.hook.run({
            "modified_paths": [],
            "allowed_write_roots": ["artifacts"],
        })
        assert result.passed

    def test_path_in_allowed_root_passes(self):
        result = self.hook.run({
            "modified_paths": ["artifacts/report.md"],
            "allowed_write_roots": ["artifacts"],
        })
        assert result.passed, result.failures

    def test_path_outside_allowed_root_fails(self):
        result = self.hook.run({
            "modified_paths": ["src/main.py"],
            "allowed_write_roots": ["artifacts"],
        })
        assert not result.passed

    def test_denied_path_fails_even_if_in_allowed(self):
        result = self.hook.run({
            "modified_paths": ["artifacts/secrets/key.txt"],
            "allowed_write_roots": ["artifacts"],
            "denied_paths": ["artifacts/secrets"],
        })
        assert not result.passed
        assert any("not_denied" in c.name for c in result.checks)

    def test_multiple_paths_partial_failure(self):
        result = self.hook.run({
            "modified_paths": ["artifacts/report.md", "src/core.py"],
            "allowed_write_roots": ["artifacts"],
        })
        assert not result.passed
        passed_checks = [c for c in result.checks if c.passed]
        failed_checks = [c for c in result.checks if not c.passed]
        assert len(passed_checks) == 1
        assert len(failed_checks) == 1

    def test_multiple_allowed_roots(self):
        result = self.hook.run({
            "modified_paths": ["artifacts/a.md", "research_plan/plan.md"],
            "allowed_write_roots": ["artifacts", "research_plan"],
        })
        assert result.passed, result.failures

    def test_no_context_passes_with_no_writes_note(self):
        result = self.hook.run({})
        assert result.passed
        assert any(c.name == "no_writes" for c in result.checks)


# ---------------------------------------------------------------------------
# HydrationVerificationHook
# ---------------------------------------------------------------------------

class TestHydrationVerificationHook:
    hook = HydrationVerificationHook()

    def test_all_conditions_pass(self):
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
        })
        assert result.passed, result.failures

    def test_yaml_invalid_fails(self):
        result = self.hook.run({"yaml_valid": False, "dry_run_passed": True})
        assert not result.passed

    def test_dry_run_failed_fails(self):
        result = self.hook.run({"yaml_valid": True, "dry_run_passed": False})
        assert not result.passed

    def test_missing_artifact_path_fails(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.db")
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
            "expected_artifact_paths": [missing],
        })
        assert not result.passed
        assert any(f"artifact_exists:{missing}" == c.name for c in result.checks)

    def test_existing_artifact_path_passes(self, tmp_path):
        artifact = tmp_path / "onto.db"
        artifact.write_bytes(b"")
        result = self.hook.run({
            "yaml_valid": True,
            "dry_run_passed": True,
            "expected_artifact_paths": [str(artifact)],
        })
        assert result.passed, result.failures


# ---------------------------------------------------------------------------
# ExecutionVerificationHook
# ---------------------------------------------------------------------------

class TestExecutionVerificationHook:
    hook = ExecutionVerificationHook()

    def test_no_outputs_declared_fails(self):
        result = self.hook.run({"execution_succeeded": True})
        assert not result.passed
        assert any(c.name == "no_outputs_declared" for c in result.checks)

    def test_execution_failed_fails(self, tmp_path):
        output = tmp_path / "out.csv"
        output.write_bytes(b"data")
        result = self.hook.run({
            "execution_succeeded": False,
            "expected_output_paths": [str(output)],
        })
        assert not result.passed

    def test_output_exists_and_in_allowed_root_passes(self, tmp_path):
        output = tmp_path / "artifacts" / "result.csv"
        output.parent.mkdir()
        output.write_bytes(b"a,b\n1,2")
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [str(output)],
            "allowed_write_roots": [str(tmp_path / "artifacts")],
        })
        assert result.passed, result.failures

    def test_output_outside_allowed_root_fails(self, tmp_path):
        output = tmp_path / "artifacts" / "result.csv"
        output.parent.mkdir()
        output.write_bytes(b"data")
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [str(output)],
            "allowed_write_roots": [str(tmp_path / "src")],
        })
        assert not result.passed

    def test_missing_output_fails(self, tmp_path):
        missing = str(tmp_path / "not_there.csv")
        result = self.hook.run({
            "execution_succeeded": True,
            "expected_output_paths": [missing],
        })
        assert not result.passed


# ---------------------------------------------------------------------------
# ArtifactVerificationHook
# ---------------------------------------------------------------------------

class TestArtifactVerificationHook:
    hook = ArtifactVerificationHook()

    def test_no_artifact_paths_declared_fails(self):
        result = self.hook.run({})
        assert not result.passed
        assert any(c.name == "no_artifacts_declared" for c in result.checks)

    def test_existing_renderable_artifact_passes(self, tmp_path):
        artifact = tmp_path / "report.md"
        artifact.write_text("# Report\nContent.", encoding="utf-8")
        result = self.hook.run({
            "artifact_paths": [str(artifact)],
            "manifest_updated": True,
        })
        assert result.passed, result.failures

    def test_missing_artifact_fails(self, tmp_path):
        result = self.hook.run({
            "artifact_paths": [str(tmp_path / "missing.pdf")],
            "manifest_updated": True,
        })
        assert not result.passed

    def test_non_renderable_suffix_fails(self, tmp_path):
        artifact = tmp_path / "data.pkl"
        artifact.write_bytes(b"\x80\x04\x95")
        result = self.hook.run({
            "artifact_paths": [str(artifact)],
            "manifest_updated": True,
        })
        assert not result.passed
        assert any("artifact_renderable" in c.name for c in result.checks)

    def test_manifest_not_updated_fails(self, tmp_path):
        artifact = tmp_path / "chart.png"
        artifact.write_bytes(b"\x89PNG")
        result = self.hook.run({
            "artifact_paths": [str(artifact)],
            "manifest_updated": False,
        })
        assert not result.passed
        assert any(c.name == "manifest_updated" and not c.passed for c in result.checks)

    def test_artifact_outside_allowed_root_fails(self, tmp_path):
        artifact = tmp_path / "report.md"
        artifact.write_text("content")
        result = self.hook.run({
            "artifact_paths": [str(artifact)],
            "allowed_write_roots": ["artifacts"],
            "manifest_updated": True,
        })
        assert not result.passed

    @pytest.mark.parametrize("suffix", [".md", ".html", ".pdf", ".png", ".jpg", ".svg", ".json", ".csv"])
    def test_all_renderable_suffixes_accepted(self, tmp_path, suffix):
        artifact = tmp_path / f"output{suffix}"
        artifact.write_bytes(b"content")
        result = self.hook.run({
            "artifact_paths": [str(artifact)],
            "manifest_updated": True,
        })
        # only check renderable check specifically
        renderable_checks = [c for c in result.checks if "renderable" in c.name]
        assert all(c.passed for c in renderable_checks), result.failures


# ---------------------------------------------------------------------------
# HealthVerificationHook
# ---------------------------------------------------------------------------

class TestHealthVerificationHook:
    hook = HealthVerificationHook()

    def test_all_conditions_pass(self, tmp_path):
        report = tmp_path / "verification_report.md"
        report.write_text("# Report")
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("done")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
        })
        assert result.passed, result.failures

    def test_missing_report_fails(self, tmp_path):
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("done")
        result = self.hook.run({
            "verification_report_path": str(tmp_path / "nonexistent.md"),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
        })
        assert not result.passed

    def test_missing_cleanup_log_fails(self, tmp_path):
        report = tmp_path / "verification_report.md"
        report.write_text("# Report")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(tmp_path / "nonexistent.log"),
            "skill_review_recorded": True,
        })
        assert not result.passed

    def test_skill_review_not_recorded_fails(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("x")
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("x")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": False,
        })
        assert not result.passed
        assert any(c.name == "skill_review_recorded" and not c.passed for c in result.checks)

    def test_disallowed_write_paths_fail(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("x")
        cleanup = tmp_path / "cleanup.log"
        cleanup.write_text("x")
        result = self.hook.run({
            "verification_report_path": str(report),
            "cleanup_log_path": str(cleanup),
            "skill_review_recorded": True,
            "disallowed_write_paths": ["src/core.py"],
        })
        assert not result.passed
        assert any("disallowed_path_clean:src/core.py" == c.name for c in result.checks)

    def test_missing_paths_not_provided_fails(self):
        result = self.hook.run({"skill_review_recorded": True})
        assert not result.passed
        # Both path checks should fail
        path_checks = [c for c in result.checks if "exists" in c.name]
        assert all(not c.passed for c in path_checks)
