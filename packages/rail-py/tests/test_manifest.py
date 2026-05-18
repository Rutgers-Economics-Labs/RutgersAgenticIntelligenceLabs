from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.manifest import parse_manifest_content


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
    assert manifest.auditors.enabled is False
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
