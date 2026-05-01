"""Tests for future project bootstrapping."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

RAIL_PY_ROOT = Path(__file__).parents[1]
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))

from rail.bootstrap import bootstrap_future_project


def test_bootstrap_future_project_creates_workspace_scaffold(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Test Project", slug="test-project")

    assert (root / "rail.yaml").exists()
    assert (root / ".ontology/ontology.yaml").exists()
    assert (root / "research_plan/current_plan.md").exists()
    assert (root / "research_plan/assumptions.md").exists()
    assert (root / "research_plan/decisions.md").exists()
    assert (root / "research_plan/methodology.md").exists()
    assert (root / "research_plan/provenance.md").exists()
    assert (root / "research_plan/claim_evidence.md").exists()
    assert (root / "research_plan/open_questions.md").exists()
    assert (root / "research_plan/rerun_options.md").exists()
    assert (root / "research_plan/verification_summary.md").exists()
    assert (root / "research_plan/state/assumptions.json").exists()
    assert (root / "research_plan/state/sources.json").exists()
    assert (root / "research_plan/state/claims.json").exists()
    assert (root / "research_plan/state/artifact_lineage.json").exists()
    assert (root / "research_plan/state/verification_runs.json").exists()
    assert (root / "agents/prompts/planner.md").exists()
    assert (root / "skills/repo-contract.md").exists()
    assert (root / "skills/web-research.md").exists()
    assert (root / "skills/source-inventory.md").exists()
    assert (root / "skills/literature-review.md").exists()
    assert (root / "skills/econometric-design.md").exists()
    assert (root / "topics").is_dir()
    assert (root / "scripts/setup-workspace.sh").exists()
    assert (root / "scripts/run-verification.sh").exists()
    assert (root / "scripts/archive-workspace.sh").exists()

    rail_data = yaml.safe_load((root / "rail.yaml").read_text(encoding="utf-8"))
    assert rail_data["project"]["name"] == "Test Project"
    assert rail_data["autonomy"]["mode"] == "assisted"
    assert rail_data["autonomy"]["max_retries_per_task"] == 3
    assert rail_data["integrity"]["require_evidence_for_report_claims"] is True
    assert rail_data["workspaces"]["mode"] == "isolated"
    assert rail_data["workspaces"]["setup_script"] == "scripts/setup-workspace.sh"

    assert yaml.safe_load((root / "research_plan/state/assumptions.json").read_text(encoding="utf-8")) == []
    assert yaml.safe_load((root / "research_plan/state/verification_runs.json").read_text(encoding="utf-8")) == []

    planner_prompt = (root / "agents/prompts/planner.md").read_text(encoding="utf-8")
    assert "# RAIL Planner Prompt" in planner_prompt

    research_cfg = yaml.safe_load((root / "agents/research.yaml").read_text(encoding="utf-8"))
    assert research_cfg["skills"]["allow_use"] is True
    assert research_cfg["skills"]["root"] == "skills"
    assert "web_research" in research_cfg["tools"]["allow"]

    research_prompt = (root / "agents/prompts/research.md").read_text(encoding="utf-8")
    assert "Do not treat web snippets as evidence" in research_prompt
