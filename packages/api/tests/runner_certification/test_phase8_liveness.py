"""Track B — Liveness and Anti-Stuck tests.

Covers:
  1. No repeated maintenance sessions without domain progress.
  2. No repeated identical work orders (idempotency guard).
  3. Domain progress extracted correctly from session results.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from app.runners.contracts import SessionResult, TaskType, DomainProgress
from app.services.liveness_service import record_session_result, check_liveness

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "research_plan" / "state").mkdir(parents=True)
    return tmp_path

class TestLivenessGuards:
    def test_domain_progress_extraction(self, project_root):
        raw_result = {
            "session_id": "sess_1",
            "status": "completed",
            "summary": "did work",
            "task_type": "analysis",
            "runner_name": "claude",
            "domain_progress": {
                "new_claim_candidates": 2
            }
        }
        
        record_session_result(project_root, "sess_1", raw_result)
        
        ledger_path = project_root / "research_plan" / "state" / "progress_ledger.json"
        assert ledger_path.exists()
        
        ledger = json.loads(ledger_path.read_text())
        assert ledger["last_domain_progress_at"] is not None
        assert len(ledger["domain_progress_events"]) == 1
        assert ledger["consecutive_maintenance_sessions"] == 0

    def test_maintenance_limit_guard(self, project_root):
        raw_result = {
            "session_id": "sess_2",
            "status": "completed",
            "summary": "did audit",
            "task_type": "health_repair",
            "runner_name": "claude",
            "domain_progress": {}
        }
        
        record_session_result(project_root, "sess_2", raw_result)
        
        # Now try to launch another health repair
        check = check_liveness(project_root, "health_repair")
        assert check["allowed"] is False
        assert "Max consecutive maintenance sessions" in check["reason"]
        
        # But an analysis task should be allowed
        check_analysis = check_liveness(project_root, "analysis")
        assert check_analysis["allowed"] is True

    def test_idempotency_guard(self, project_root):
        # We need to simulate the work order existing
        wo_dir = project_root / "research_plan" / "work_orders"
        wo_dir.mkdir(parents=True, exist_ok=True)
        wo_dir.joinpath("wo_123.json").write_text(json.dumps({
            "idempotency_key": "ik_1",
            "input_hash": "hash_1"
        }))
        
        raw_result = {
            "session_id": "sess_3",
            "work_order_id": "wo_123",
            "status": "completed",
            "summary": "did analysis",
            "task_type": "analysis",
            "runner_name": "claude",
            "domain_progress": {}
        }
        
        record_session_result(project_root, "sess_3", raw_result)
        
        # Now try to launch the exact same task
        check = check_liveness(project_root, "analysis", idempotency_key="ik_1", input_hash="hash_1")
        assert check["allowed"] is False
        assert "already executed" in check["reason"]
        
        # Different hash should be allowed
        check_diff = check_liveness(project_root, "analysis", idempotency_key="ik_1", input_hash="hash_2")
        assert check_diff["allowed"] is True

    def test_legacy_session_result_updates_progress_ledger(self, project_root):
        raw_result = {
            "work_order_id": "wo_legacy_health",
            "agent_session_id": "sess_legacy_health",
            "status": "completed",
            "produced_domain_progress": False,
            "summary": "Reconciled stale control-plane state.",
            "artifacts_updated": [
                "research_plan/state/control_plane_audit.json",
                "research_plan/state/verification_runs.json",
            ],
            "blockers": [],
            "generated_at": "2026-05-24T23:59:00Z",
        }

        record_session_result(project_root, "sess_legacy_health", raw_result, role="health", runner_name="codex_cli")

        ledger = json.loads((project_root / "research_plan" / "state" / "progress_ledger.json").read_text())
        assert ledger["consecutive_maintenance_sessions"] == 1
        assert ledger["consecutive_no_progress_sessions"] == 1
