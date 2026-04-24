from rail.bootstrap import bootstrap_future_project
from pathlib import Path
import yaml

def test_bootstrap_future_project(tmp_path):
    root = bootstrap_future_project(tmp_path, name="Test Project", slug="test-project")

    assert (root / "rail.yaml").exists()
    assert (root / ".ontology/ontology.yaml").exists()
    assert (root / "research_plan/current_plan.md").exists()
    assert (root / "agents/prompts/planner.md").exists()
    assert (root / "skills/repo-contract.md").exists()
    assert (root / "topics").is_dir()

    # check rail.yaml
    rail_data = yaml.safe_load((root / "rail.yaml").read_text())
    assert rail_data["project"]["name"] == "Test Project"

    # Check planner prompt is markdown
    planner_prompt = (root / "agents/prompts/planner.md").read_text()
    assert "# RAIL Planner Prompt" in planner_prompt
