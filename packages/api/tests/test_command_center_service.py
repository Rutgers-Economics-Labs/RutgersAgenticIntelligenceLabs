from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIL_PY_ROOT = Path(__file__).parents[2] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(root: Path) -> dict:
    return {
        "_id": "project-id",
        "name": "Grid Study",
        "slug": "grid-study",
        "status": "ready",
        "localRepoPath": str(root),
        "defaultBranch": "main",
    }


def test_skills_sources_and_artifacts_read_repo_files(tmp_path: Path):
    from app.services import command_center_service

    _write(tmp_path / "agents" / "research.yaml", "role: research\nskills:\n  allow_use: true\n")
    _write(tmp_path / "skills" / "web-research.md", "# Web Research\n\nFind primary sources.\n")
    _write(
        tmp_path / "research_plan" / "graph" / "sources.yaml",
        """
sources:
  - slug: pjm
    name: PJM Data Miner
    provider: PJM
    readiness: ready
    reason: Historical load and LMP data.
""",
    )
    _write(tmp_path / ".ontology" / "sources" / "noaa.yaml", "name: NOAA CDO\ntype: api\n")
    _write(tmp_path / "artifacts" / "summary.md", "# Summary\n\nResult.\n")
    project = _project(tmp_path)

    skills = command_center_service.list_project_skills(project)
    sources = command_center_service.list_project_sources(project)
    artifacts = command_center_service.list_project_artifacts(project)

    assert skills["summary"]["count"] == 1
    assert skills["skills"][0]["usedBy"] == ["research"]
    assert sources["summary"]["count"] == 2
    assert {row["id"] for row in sources["sources"]} == {"pjm", "noaa"}
    assert artifacts["summary"]["count"] == 1
    assert artifacts["artifacts"][0]["preview"]["content"].startswith("# Summary")


def test_launch_preview_and_approval_create_repo_tasks(tmp_path: Path):
    from app.services import command_center_service

    project = _project(tmp_path)
    payload = {
        "researchQuestion": "How do data centers affect grid costs?",
        "workflowPresets": ["feasibility_memo", "econometric_model"],
        "approvalBeforeWrites": True,
    }

    preview = command_center_service.build_launch_preview(project, payload)
    result = asyncio.run(command_center_service.approve_launch_preview(project, payload))

    assert preview["skillsToUse"]
    assert len(result["tasks"]) == 2
    assert (tmp_path / "research_plan" / "tasks").is_dir()
    assert (tmp_path / "research_plan" / "approvals").is_dir()
