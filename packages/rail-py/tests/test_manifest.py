from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.manifest import (
    ContractViolation,
    ManifestValidationError,
    boot_validate_project,
    load_and_validate_manifest,
    parse_manifest_content,
    validate_manifest_semantics,
    validate_repo_contract,
)


MINIMAL_RAIL_YAML = textwrap.dedent(
    """\
    version: 1

    project:
      name: "Test Project"
      slug: "test-project"
      default_branch: "main"

    paths:
      ontology_root: ".ontology"
      topics_root: "topics"
      specs_root: "specs"
      plan_root: "research_plan"
      agents_root: "agents"
      skills_root: "skills"
      artifacts_root: "artifacts"

    hydration:
      ontology_file: ".ontology/ontology.yaml"
      sources_dir: ".ontology/sources"
      pipelines_dir: ".ontology/pipelines"
      hydration_mode: "full"

    agents:
      roles_dir: "agents"
      default_runner: "codex_cli"
      sequential_execution: true
      planner_thread_mode: "project"
      default_planner_role: "planner"

    frontend:
      topic_index_mode: "filesystem"
      artifact_index_mode: "filesystem"
    """
)


def test_manifest_defaults_assisted_autonomy_and_integrity_policy():
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)

    assert manifest.autonomy.mode == "assisted"
    assert manifest.autonomy.require_human_for == []
    assert manifest.autonomy.allow_without_human == []
    assert manifest.autonomy.max_runtime_minutes is None
    assert manifest.integrity.allow_synthetic_data is False
    assert manifest.integrity.require_source_for_datasets is True
    assert manifest.integrity.require_lineage_for_final_artifacts is True
    assert manifest.integrity.require_evidence_for_report_claims is True
    assert manifest.integrity.stale_outputs_block_promotion is True


def test_manifest_parses_explicit_autonomy_and_integrity_sections():
    content = MINIMAL_RAIL_YAML + textwrap.dedent(
        """\

        autonomy:
          mode: "supervised_autopilot"
          require_human_for:
            - "publish_changes"
          allow_without_human:
            - "verification"
          max_runtime_minutes: 180
          max_cost_usd: 20
          max_retries_per_task: 3

        integrity:
          allow_synthetic_data: true
          require_source_for_datasets: false
          require_lineage_for_final_artifacts: false
          require_evidence_for_report_claims: false
          stale_outputs_block_promotion: false
        """
    )

    manifest = parse_manifest_content(content)

    assert manifest.autonomy.mode == "supervised_autopilot"
    assert manifest.autonomy.require_human_for == ["publish_changes"]
    assert manifest.autonomy.allow_without_human == ["verification"]
    assert manifest.autonomy.max_runtime_minutes == 180
    assert manifest.autonomy.max_cost_usd == 20
    assert manifest.autonomy.max_retries_per_task == 3
    assert manifest.integrity.allow_synthetic_data is True
    assert manifest.integrity.require_source_for_datasets is False
    assert manifest.integrity.require_lineage_for_final_artifacts is False
    assert manifest.integrity.require_evidence_for_report_claims is False
    assert manifest.integrity.stale_outputs_block_promotion is False


def test_manifest_rejects_invalid_autonomy_mode():
    content = MINIMAL_RAIL_YAML + textwrap.dedent(
        """\

        autonomy:
          mode: "hands_free"
        """
    )

    with pytest.raises(ValueError, match="autonomy.mode"):
        parse_manifest_content(content)


def test_manifest_preserves_legacy_write_approval_shorthand():
    content = MINIMAL_RAIL_YAML.replace(
        "  planner_thread_mode: \"project\"\n",
        "  approval_required_for_write_runs: true\n  planner_thread_mode: \"project\"\n",
    )

    manifest = parse_manifest_content(content)

    assert manifest.agents.approval_required_for_write_runs is True
    assert manifest.autonomy.mode == "assisted"


def test_manifest_defaults_new_contract_sections():
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)

    assert manifest.project.mode == "ontology_first"
    assert manifest.repo_contract.source_of_truth == "git"
    assert ".ontology" in manifest.repo_contract.required_paths
    assert manifest.research.brief_path == "topics/brief.md"
    assert manifest.planner.task_root == "research_plan/tasks"
    assert manifest.auditors.enabled is True
    assert manifest.verification.deterministic_command == "scripts/run-verification.sh"
    assert manifest.secrets.project_scope is True
    assert "hydrated" in manifest.lifecycle.phases
    assert "ontology_healthy" in manifest.lifecycle.phases


def test_manifest_rejects_ontology_first_without_required_phases():
    content = MINIMAL_RAIL_YAML + textwrap.dedent(
        """\

        lifecycle:
          phases:
            - "brief"
            - "scoped"
            - "closed"
        """
    )

    with pytest.raises(ValueError, match="ontology_first projects must include hydrated and ontology_healthy lifecycle phases"):
        parse_manifest_content(content)


def test_validate_repo_contract_passes_when_all_required_paths_exist(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    for rel in manifest.repo_contract.required_paths:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    violations = validate_repo_contract(manifest, tmp_path)

    assert violations == []


def test_validate_repo_contract_returns_violations_for_missing_paths(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    # create all required paths except "specs"
    for rel in manifest.repo_contract.required_paths:
        if rel != "specs":
            (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    violations = validate_repo_contract(manifest, tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "specs"
    assert "does not exist" in violations[0].reason


def test_validate_repo_contract_returns_all_missing_paths(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    # create nothing — all required paths are missing

    violations = validate_repo_contract(manifest, tmp_path)

    missing_paths = {v.path for v in violations}
    assert missing_paths == set(manifest.repo_contract.required_paths)


def test_load_and_validate_manifest_returns_manifest_and_violations(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    # write rail.yaml but leave required paths absent
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")

    loaded, violations = load_and_validate_manifest(tmp_path)

    assert loaded.project.slug == "test-project"
    assert len(violations) == len(manifest.repo_contract.required_paths)


def test_load_and_validate_manifest_no_violations_when_structure_complete(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    for rel in manifest.repo_contract.required_paths:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    _loaded, violations = load_and_validate_manifest(tmp_path)

    assert violations == []


def test_parse_manifest_content_reports_field_paths_for_invalid_values():
    content = MINIMAL_RAIL_YAML.replace('default_branch: "main"', 'default_branch: 123')

    with pytest.raises(ValueError, match="project.default_branch"):
        parse_manifest_content(content)


def test_boot_validate_project_raises_on_repo_contract_violations(tmp_path):
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")

    with pytest.raises(ManifestValidationError) as exc_info:
        boot_validate_project(tmp_path)

    assert exc_info.value.violations
    assert any(item.path == ".ontology" for item in exc_info.value.violations)


def test_boot_validate_project_returns_manifest_when_contract_is_valid(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    (tmp_path / "rail.yaml").write_text(MINIMAL_RAIL_YAML, encoding="utf-8")
    for rel in manifest.repo_contract.required_paths:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    loaded = boot_validate_project(tmp_path)

    assert loaded.project.slug == "test-project"


def test_validate_manifest_semantics_delegates_to_repo_contract(tmp_path):
    manifest = parse_manifest_content(MINIMAL_RAIL_YAML)
    violations = validate_manifest_semantics(manifest, tmp_path)

    assert {item.path for item in violations} == set(manifest.repo_contract.required_paths)
