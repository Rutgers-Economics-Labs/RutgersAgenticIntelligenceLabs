"""Tests for Milestone 4: Ontology Audit Plane — health check and state classification."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# classify_hydration_state
# ---------------------------------------------------------------------------

def test_classify_hydration_state_ready_states():
    from app.services.auditor_service import classify_hydration_state
    assert classify_hydration_state("hydrated_on_this_device") == "ready"
    assert classify_hydration_state("hydrated_on_another_device") == "ready"


def test_classify_hydration_state_in_progress():
    from app.services.auditor_service import classify_hydration_state
    assert classify_hydration_state("hydrating") == "in_progress"


def test_classify_hydration_state_stale():
    from app.services.auditor_service import classify_hydration_state
    assert classify_hydration_state("stale_on_this_device") == "stale"


def test_classify_hydration_state_not_started():
    from app.services.auditor_service import classify_hydration_state
    assert classify_hydration_state("not_hydrated") == "not_started"


def test_classify_hydration_state_unknown_falls_back_to_unavailable():
    from app.services.auditor_service import classify_hydration_state
    assert classify_hydration_state("some_future_state") == "unavailable"
    assert classify_hydration_state("") == "unavailable"


# ---------------------------------------------------------------------------
# audit_ontology_health — non-ontology project
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_ontology_health_not_applicable_for_non_ontology_project(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    result = await audit_ontology_health(project)

    assert result["healthy"] is True
    assert result["stateClassification"] == "not_applicable"
    assert result["blockers"] == []


# ---------------------------------------------------------------------------
# audit_ontology_health — ontology project, various states
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_ontology_health_blocked_when_not_hydrated(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    (tmp_path / ".ontology").mkdir()
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}

    with patch(
        "app.services.auditor_service.get_hydration_status",
        new_callable=AsyncMock,
        return_value={"state": "not_hydrated"},
    ):
        result = await audit_ontology_health(project)

    assert result["healthy"] is False
    assert result["stateClassification"] == "not_started"
    assert any("not_hydrated" in b for b in result["blockers"])


@pytest.mark.asyncio
async def test_audit_ontology_health_blocked_when_duckdb_empty(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    (tmp_path / ".ontology").mkdir()
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    duckdb_path = str(tmp_path / "ontology.duckdb")

    with (
        patch(
            "app.services.auditor_service.get_hydration_status",
            new_callable=AsyncMock,
            return_value={
                "state": "hydrated_on_this_device",
                "reusableArtifact": {"duckdbArtifactPath": duckdb_path},
                "currentDeviceArtifacts": [],
            },
        ),
        patch("app.services.auditor_service._duckdb_has_populated_rows", return_value=False),
    ):
        result = await audit_ontology_health(project)

    assert result["healthy"] is False
    assert any("populated rows" in b for b in result["blockers"])


@pytest.mark.asyncio
async def test_audit_ontology_health_healthy_when_hydrated_and_rows_present(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    (tmp_path / ".ontology").mkdir()
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    duckdb_path = str(tmp_path / "ontology.duckdb")

    with (
        patch(
            "app.services.auditor_service.get_hydration_status",
            new_callable=AsyncMock,
            return_value={
                "state": "hydrated_on_this_device",
                "reusableArtifact": {"duckdbArtifactPath": duckdb_path},
                "currentDeviceArtifacts": [],
            },
        ),
        patch("app.services.auditor_service._duckdb_has_populated_rows", return_value=True),
    ):
        result = await audit_ontology_health(project)

    assert result["healthy"] is True
    assert result["stateClassification"] == "ready"
    assert result["duckdbPath"] == duckdb_path
    assert result["blockers"] == []


@pytest.mark.asyncio
async def test_audit_ontology_health_blocked_by_drift(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    (tmp_path / ".ontology").mkdir()
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}
    duckdb_path = str(tmp_path / "ontology.duckdb")
    drift = {"hasDrift": True, "reason": "active_ontology_pointer_out_of_date"}

    with (
        patch(
            "app.services.auditor_service.get_hydration_status",
            new_callable=AsyncMock,
            return_value={
                "state": "hydrated_on_this_device",
                "reusableArtifact": {"duckdbArtifactPath": duckdb_path},
                "currentDeviceArtifacts": [],
            },
        ),
        patch("app.services.auditor_service._duckdb_has_populated_rows", return_value=True),
    ):
        result = await audit_ontology_health(project, ontology_artifact_drift=drift)

    assert result["healthy"] is False
    assert result["driftReason"] == "active_ontology_pointer_out_of_date"
    assert any("drift" in b for b in result["blockers"])


@pytest.mark.asyncio
async def test_audit_ontology_health_blocked_when_hydration_raises(tmp_path):
    from app.services.auditor_service import audit_ontology_health

    (tmp_path / ".ontology").mkdir()
    project = {"_id": "proj1", "localRepoPath": str(tmp_path)}

    with patch(
        "app.services.auditor_service.get_hydration_status",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB unreachable"),
    ):
        result = await audit_ontology_health(project)

    assert result["healthy"] is False
    assert any("Could not read" in b for b in result["blockers"])
