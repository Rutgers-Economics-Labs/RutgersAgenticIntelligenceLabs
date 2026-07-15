from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path

import pytest

from app.krail_runtime import ApprovalDecision, FindQuery, GraphQuery, ProjectRef, RunRequest
from app.krail_runtime.errors import KrailProjectNotFoundError, KrailValidationError


def test_uses_the_published_krail_distribution(runtime) -> None:
    assert importlib.metadata.version("krail") == "0.2.2"
    rail = runtime._rail()
    distribution_root = Path(importlib.metadata.distribution("krail").locate_file("rail")).resolve()
    assert Path(rail.__file__).resolve().is_relative_to(distribution_root)


def test_doctor_and_manifest_contract(runtime, fixture_project) -> None:
    health = runtime.doctor(fixture_project)
    manifest = runtime.manifest(fixture_project)

    assert health.ok is True
    assert health.krail_version == "0.2.2"
    assert manifest.slug == "krail-adapter-fixture"
    assert manifest.paths["topics_root"] == "topics"


def test_find_and_graph_contract(runtime, fixture_project) -> None:
    found = runtime.find(fixture_project, FindQuery(text="fixture evidence", explain=True))
    graph = runtime.graph(fixture_project, GraphQuery(entity_type="Policy"))

    assert found.total >= 1
    assert any(item.path == "topics/evidence.md" for item in found.items)
    assert any(node.label == "Transit Affordability" for node in graph.nodes)
    assert any(document.path == "topics/evidence.md" for document in graph.documents)


def test_sources_contract_is_read_only(runtime, fixture_project) -> None:
    inventory = runtime.sources(fixture_project)
    before = fixture_project.path / "research_plan/state/source_snapshots.json"
    checked = runtime.check_sources(fixture_project)
    affected = runtime.affected_sources(fixture_project, ["local:fixture-evidence"])

    assert [source.id for source in inventory.sources] == ["local:fixture-evidence"]
    assert checked.status == "checked"
    assert not before.exists()
    assert affected.documents == ["topics/evidence.md"]


def test_integrity_contract_does_not_load_legacy_rail_services(runtime, fixture_project) -> None:
    summary = runtime.integrity(fixture_project)

    assert summary.status == "available"
    assert summary.sources == summary.claims == summary.assumptions == 0
    assert not any(name.startswith("app.services") for name in sys.modules)


def test_workflow_contract_and_dry_run(runtime, fixture_project) -> None:
    inventory = runtime.workflows(fixture_project)
    run = runtime.execute_workflow(fixture_project, RunRequest(workflow_id="fixture-review", dry_run=True))

    assert [(workflow.id, workflow.valid) for workflow in inventory.workflows] == [("fixture-review", True)]
    assert run.workflow_id == "fixture-review"
    assert run.status == "dry_run"
    assert run.run_id


def test_approval_contract(runtime, fixture_project) -> None:
    approvals = runtime.approvals(fixture_project)
    approval = runtime.approval(fixture_project, "fixture-approval")
    decided = runtime.decide_approval(
        fixture_project,
        "fixture-approval",
        ApprovalDecision(decision="approved", comment="fixture contract"),
    )

    assert [item.id for item in approvals.approvals] == ["fixture-approval"]
    assert approval.status == "pending"
    assert decided.status == "approved"


def test_missing_or_invalid_projects_have_typed_errors(runtime, tmp_path) -> None:
    missing = ProjectRef(path=tmp_path / "missing")
    with pytest.raises(KrailProjectNotFoundError):
        runtime.doctor(missing)

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "rail.yaml").write_text("version: 1\n", encoding="utf-8")
    invalid_ref = ProjectRef(path=invalid)
    with pytest.raises(KrailValidationError):
        runtime.manifest(invalid_ref)
