from app.services.brief_project_service import build_preview, render_repo_files


import pytest


@pytest.mark.asyncio
async def test_build_preview_returns_repo_backed_assets():
    brief = """
    Assessing the impact of data centers on grid costs in New Jersey.
    Objective: estimate how load growth affects congestion and prices.
    Methods: econometric modeling, difference-in-differences, spatial analysis.
    Data sources: PJM, NOAA, ACS, FERC.
    Deliverables: technical report, dashboard.
    """

    preview = await build_preview(brief, model=None)

    assert preview["project"]["slug"]
    assert "researchGraph" in preview
    assert any(file["path"] == "specs/research_question.yaml" for file in preview["repoFiles"])
    assert any(file["path"] == "research_plan/graph/summary.yaml" for file in preview["repoFiles"])
    assert preview["ontology"]["slug"].endswith("-ontology")
    assert preview["pipeline"]["slug"].endswith("-pipeline")


def test_render_repo_files_includes_graph_and_topics():
    project = {"name": "Grid Costs", "slug": "grid-costs"}
    graph = {
        "title": "Grid Costs",
        "summary": "Research kickoff",
        "audience": "Regulators",
        "objective": "Understand drivers of cost",
        "causal_questions": ["How do data centers affect prices?"],
        "outcomes": ["Price"],
        "units_of_analysis": ["Load Zone"],
        "geographies": ["New Jersey"],
        "time_windows": ["2015-2025"],
        "methods": ["difference-in-differences"],
        "deliverables": ["technical report"],
        "controls": ["weather"],
        "entities": ["Data Center"],
        "measures": ["LMP"],
        "source_hints": ["PJM"],
    }
    sources = [{
        "slug": "grid-costs-pjm",
        "name": "PJM",
        "provider": "manual",
        "externalId": None,
        "description": "Manual source",
        "readiness": "draft_for_review",
        "reason": "Needs review",
        "configKind": "api",
        "content": "name: grid-costs-pjm\ntype: api\nurl: https://example.com\nresponse_format: json\nfields:\n  - source: id\n    alias: id\n",
    }]
    ontology = {"slug": "grid-costs-ontology", "content": "uri: http://example\nclasses: []\ndata_properties: []\nobject_properties: []\n"}
    pipeline = {"slug": "grid-costs-pipeline", "content": "name: grid-costs-pipeline\nontology: grid-costs-ontology\nsteps: []\n"}

    files = render_repo_files(project, graph, sources, ontology, pipeline)
    paths = {file["path"] for file in files}
    assert "topics/brief.md" in paths
    assert "topics/source_notes.md" in paths
    assert "research_plan/graph/sources.yaml" in paths
