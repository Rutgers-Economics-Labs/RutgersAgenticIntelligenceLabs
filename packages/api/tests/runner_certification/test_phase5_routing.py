"""Phase 5 — Capability Router tests.

Covers:
  1. Capability-based filtering of runners.
  2. Project-level policy (allowed/preferred runners).
  3. Ranking logic (affinity + bonus).
  4. Decision logging to research_plan/dispatch_log/.
  5. Explicit runner override.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.runners.contracts import (
    Capability,
    TaskType,
    RunnerProfile,
    ExecutionCapabilities,
    AdapterType,
    CertificationStatus,
    CapabilityState,
    SteeringMode,
)
from app.services.capability_router import route_task

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "research_plan").mkdir()
    return tmp_path

@pytest.fixture
def mock_planner_service(project_root):
    with patch("app.services.capability_router.planner_service") as mock:
        mock.get_project_by_slug = AsyncMock(return_value={"slug": "test-proj", "localRepoPath": str(project_root)})
        mock.project_root_from_record.return_value = project_root
        
        # Mock manifest
        manifest = MagicMock()
        manifest.agents = MagicMock()
        manifest.agents.runner_policy = MagicMock()
        manifest.agents.runner_policy.allowed = []
        manifest.agents.runner_policy.preferred = []
        mock.load_validated_manifest.return_value = manifest
        
        yield mock

@pytest.fixture
def mock_profiles():
    claude = RunnerProfile(
        name="claude_code",
        adapter=AdapterType.LOCAL_CLI,
        status=CertificationStatus.CERTIFIED,
        execution=ExecutionCapabilities(mode=AdapterType.LOCAL_CLI, steering_mode=SteeringMode.RELAUNCH_ONLY),
        capabilities={
            Capability.EDIT_FILES: CapabilityState.YES,
            Capability.RUN_SHELL: CapabilityState.YES,
            Capability.WRITE_LONG_ARTIFACTS: CapabilityState.YES
        },
        task_affinity={TaskType.ANALYSIS: 0.9}
    )
    gemini = RunnerProfile(
        name="gemini_cli",
        adapter=AdapterType.LOCAL_CLI,
        status=CertificationStatus.CERTIFIED,
        execution=ExecutionCapabilities(mode=AdapterType.LOCAL_CLI, steering_mode=SteeringMode.RELAUNCH_ONLY),
        capabilities={
            Capability.EDIT_FILES: CapabilityState.YES,
            Capability.RUN_SHELL: CapabilityState.YES,
            Capability.WRITE_LONG_ARTIFACTS: CapabilityState.NO
        },
        task_affinity={TaskType.ANALYSIS: 0.8}
    )
    
    profiles = {
        "claude_code": claude,
        "gemini_cli": gemini
    }
    with patch("app.services.capability_router.load_all_profiles", return_value=profiles):
        yield profiles

class TestCapabilityRouting:
    @pytest.mark.asyncio
    async def test_routes_by_capability(self, mock_planner_service, mock_profiles, project_root):
        # Requires write_long_artifacts
        reqs = [Capability.EDIT_FILES, Capability.WRITE_LONG_ARTIFACTS]
        
        runner = await route_task("test-proj", "wo-1", reqs, TaskType.ANALYSIS)
        
        assert runner == "claude_code" # Only one that has both
        
        # Verify log
        log_path = project_root / "research_plan" / "dispatch_log" / "wo-1.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert log["selected_runner"] == "claude_code"

    @pytest.mark.asyncio
    async def test_routes_by_affinity_when_multiple_eligible(self, mock_planner_service, mock_profiles, project_root):
        # Both have edit_files
        reqs = [Capability.EDIT_FILES]
        
        runner = await route_task("test-proj", "wo-2", reqs, TaskType.ANALYSIS)
        
        assert runner == "claude_code" # 0.9 affinity vs 0.8

    @pytest.mark.asyncio
    async def test_respects_preferred_bonus(self, mock_planner_service, mock_profiles, project_root):
        reqs = [Capability.EDIT_FILES]
        # Make gemini preferred
        mock_planner_service.load_validated_manifest.return_value.agents.runner_policy.preferred = ["gemini_cli"]
        
        runner = await route_task("test-proj", "wo-3", reqs, TaskType.ANALYSIS)
        
        # gemini: 0.8 + 0.2 = 1.0
        # claude: 0.9 + 0.0 = 0.9
        assert runner == "gemini_cli"

    @pytest.mark.asyncio
    async def test_respects_allow_list(self, mock_planner_service, mock_profiles, project_root):
        reqs = [Capability.EDIT_FILES]
        # Only gemini allowed
        mock_planner_service.load_validated_manifest.return_value.agents.runner_policy.allowed = ["gemini_cli"]
        
        runner = await route_task("test-proj", "wo-4", reqs, TaskType.ANALYSIS)
        
        assert runner == "gemini_cli"

    @pytest.mark.asyncio
    async def test_explicit_runner_override(self, mock_planner_service, mock_profiles, project_root):
        reqs = [Capability.WRITE_LONG_ARTIFACTS]
        
        # Override to gemini even though it doesn't have the capability
        runner = await route_task("test-proj", "wo-5", reqs, TaskType.ANALYSIS, explicit_runner="gemini_cli")
        
        assert runner == "gemini_cli"
        log = json.loads((project_root / "research_plan" / "dispatch_log" / "wo-5.json").read_text())
        assert log["override"] is True
