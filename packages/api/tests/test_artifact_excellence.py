"""Tests for Milestone 8: Artifact Excellence — register lineage and write verification certificates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _init_integrity_state(tmp_path: Path) -> None:
    state_dir = tmp_path / "research_plan" / "state"
    state_dir.mkdir(parents=True)
    for name in ["sources.json", "claims.json", "artifact_lineage.json",
                 "verification_runs.json", "assumptions.json", "source_candidates.json",
                 "claim_candidates.json", "entity_candidates.json", "conflicts.json"]:
        path = state_dir / name
        if not path.exists():
            path.write_text("[]", encoding="utf-8")


# ---------------------------------------------------------------------------
# register_final_artifact
# ---------------------------------------------------------------------------

def test_register_final_artifact_creates_lineage_record(tmp_path):
    from app.services.integrity_service import register_final_artifact, load_integrity_indexes

    _init_integrity_state(tmp_path)
    # inputs/scripts are filtered to files that exist on disk
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "processed.csv").write_text("col1\n1\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "generate_report.py").write_text("# stub\n", encoding="utf-8")

    result = register_final_artifact(
        tmp_path,
        artifact_path="artifacts/report.md",
        artifact_type="report",
        title="Final Report",
        inputs=["data/processed.csv"],
        scripts=["scripts/generate_report.py"],
        verification_commands=["python scripts/run-verification.sh"],
    )

    assert result["artifact_path"] == "artifacts/report.md"
    assert result["artifact_type"] == "report"
    assert result["title"] == "Final Report"
    assert "data/processed.csv" in result["inputs"]
    assert "scripts/generate_report.py" in result["scripts"]

    indexes = load_integrity_indexes(tmp_path)
    stored = next((r for r in indexes.artifact_lineage if r.artifact_path == "artifacts/report.md"), None)
    assert stored is not None
    assert stored.title == "Final Report"


def test_register_final_artifact_upserts_existing_record(tmp_path):
    from app.services.integrity_service import register_final_artifact, load_integrity_indexes

    _init_integrity_state(tmp_path)

    register_final_artifact(
        tmp_path,
        artifact_path="artifacts/figure1.png",
        artifact_type="figure",
        title="Figure 1 — Initial",
        inputs=["data/raw.csv"],
        scripts=["scripts/plot.py"],
    )
    register_final_artifact(
        tmp_path,
        artifact_path="artifacts/figure1.png",
        artifact_type="figure",
        title="Figure 1 — Updated",
        inputs=["data/raw.csv"],
        scripts=["scripts/plot.py"],
        verification_commands=["python verify_figure.py"],
    )

    indexes = load_integrity_indexes(tmp_path)
    matches = [r for r in indexes.artifact_lineage if r.artifact_path == "artifacts/figure1.png"]
    assert len(matches) == 1
    assert matches[0].title == "Figure 1 — Updated"
    assert matches[0].verification_commands == ["python verify_figure.py"]


def test_register_final_artifact_minimal_call(tmp_path):
    from app.services.integrity_service import register_final_artifact

    _init_integrity_state(tmp_path)

    result = register_final_artifact(
        tmp_path,
        artifact_path="artifacts/dashboard.html",
        artifact_type="dashboard",
        title="Dashboard",
    )

    assert result["artifact_path"] == "artifacts/dashboard.html"
    assert result["inputs"] == []
    assert result["scripts"] == []


# ---------------------------------------------------------------------------
# write_verification_certificate
# ---------------------------------------------------------------------------

def test_write_verification_certificate_creates_markdown_file(tmp_path):
    from app.services.integrity_service import write_verification_certificate

    result = write_verification_certificate(
        tmp_path,
        "artifacts/report.md",
        run_id="run-2026-001",
        session_id="sess-abc",
        verified_at="2026-05-18T12:00:00Z",
    )

    assert "certificatePath" in result
    cert_path = Path(result["certificatePath"])
    assert cert_path.exists()
    content = cert_path.read_text(encoding="utf-8")
    assert "artifacts/report.md" in content
    assert "run-2026-001" in content
    assert "sess-abc" in content
    assert "2026-05-18T12:00:00Z" in content


def test_write_verification_certificate_default_directory(tmp_path):
    from app.services.integrity_service import write_verification_certificate

    result = write_verification_certificate(
        tmp_path,
        "artifacts/figure1.png",
        run_id="run-fig-001",
    )

    cert_path = Path(result["certificatePath"])
    assert "verification_certificates" in str(cert_path)
    assert cert_path.parent.is_dir()


def test_write_verification_certificate_includes_notes(tmp_path):
    from app.services.integrity_service import write_verification_certificate

    result = write_verification_certificate(
        tmp_path,
        "artifacts/paper.pdf",
        run_id="run-paper-001",
        notes="All regression tables reproduced exactly.",
    )

    assert "All regression tables reproduced exactly." in result["content"]


def test_write_verification_certificate_can_be_overwritten(tmp_path):
    from app.services.integrity_service import write_verification_certificate

    write_verification_certificate(tmp_path, "artifacts/fig.png", run_id="run-001", notes="First pass.")
    result2 = write_verification_certificate(tmp_path, "artifacts/fig.png", run_id="run-001", notes="Second pass.")

    assert "Second pass." in result2["content"]
