"""Tests for Stuck Detector and Report Generation (Track B).

Covers:
  1. Detection of repeated blockers.
  2. Detection of no-progress maintenance loops.
  3. Generation of Markdown diagnostic reports.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from app.services.stuck_detector import detect_stuck_state, write_stuck_report

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "research_plan" / "state").mkdir(parents=True)
    return tmp_path

class TestStuckDetector:
    def test_detect_repeated_blocker(self, project_root):
        ledger_path = project_root / "research_plan" / "state" / "progress_ledger.json"
        ledger = {
            "repeated_blockers": {"ontology_stale": 3},
            "consecutive_maintenance_sessions": 0
        }
        ledger_path.write_text(json.dumps(ledger))
        
        diagnosis = detect_stuck_state(project_root)
        assert diagnosis is not None
        assert diagnosis["stuck"] is True
        assert any(i["type"] == "repeated_blocker" for i in diagnosis["issues"])
        assert "Mark the blocker as a promotion-blocker" in diagnosis["recommended_escape"]

    def test_detect_maintenance_loop(self, project_root):
        ledger_path = project_root / "research_plan" / "state" / "progress_ledger.json"
        ledger = {
            "repeated_blockers": {},
            "consecutive_maintenance_sessions": 3
        }
        ledger_path.write_text(json.dumps(ledger))
        
        diagnosis = detect_stuck_state(project_root)
        assert diagnosis is not None
        assert any(i["type"] == "maintenance_loop" for i in diagnosis["issues"])
        assert "Force a synthesis/draft task" in diagnosis["recommended_escape"]

    def test_write_stuck_report(self, project_root):
        diagnosis = {
            "stuck": True,
            "issues": [{"type": "test_issue", "description": "something is wrong"}],
            "timestamp": "2026-05-22T00:00:00Z",
            "recommended_escape": "Try something else."
        }
        
        report_path = write_stuck_report(project_root, diagnosis)
        assert report_path.exists()
        assert report_path.suffix == ".md"
        content = report_path.read_text()
        assert "# RAIL Stuck Report" in content
        assert "something is wrong" in content
        assert "Try something else." in content
