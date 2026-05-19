"""Tests for HTML dashboard generation (Milestone 8)."""

from __future__ import annotations

from pathlib import Path


def test_write_dashboard_artifact_creates_html(tmp_path: Path):
    from app.services.artifact_dashboard_service import write_dashboard_artifact

    path = write_dashboard_artifact(
        tmp_path,
        db_stats={
            "hpi": {"start": "2015-Q1", "end": "2025-Q1", "first": 100.0, "last": 199.0, "pct_change": 99.0, "count": 40},
            "cpi": {"start": "2015-01", "end": "2025-01", "first": 200.0, "last": 300.0, "pct_change": 50.0, "count": 120},
        },
        title="NJ Housing Dashboard",
    )

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "NJ Housing Dashboard" in text
    assert "NJSTHPI" in text or "House Price" in text
