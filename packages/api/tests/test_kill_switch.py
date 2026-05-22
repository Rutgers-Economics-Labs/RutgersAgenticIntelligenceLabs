"""Kill switch — emergency stop for autopilots and runner sessions."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_state_file(tmp_path, monkeypatch):
    """Point the kill switch at a tmp file so tests don't touch real state."""
    state_path = tmp_path / "kill_switch.json"
    monkeypatch.setenv("RAIL_KILL_SWITCH_PATH", str(state_path))
    # Reload to make sure the test fixture is what gets used; the module
    # reads the env var at every call so no further setup is needed.
    yield state_path


def test_status_is_released_by_default(_isolate_state_file):
    from app.services import kill_switch_service
    assert kill_switch_service.is_globally_killed() is False
    assert kill_switch_service.is_project_killed("any-slug") is False
    assert kill_switch_service.is_killed("any-slug") is False
    s = kill_switch_service.status()
    assert s["global"]["engaged"] is False
    assert s["projects"] == {}


def test_engage_global_persists_and_blocks_all_projects(_isolate_state_file):
    from app.services import kill_switch_service

    async def _go():
        await kill_switch_service.engage_global(reason="testing", engaged_by="pytest")

    asyncio.run(_go())

    state = json.loads(Path(_isolate_state_file).read_text())
    assert state["global"]["engaged"] is True
    assert state["global"]["reason"] == "testing"
    assert state["global"]["engaged_by"] == "pytest"
    assert state["global"]["engaged_at"] is not None

    # Both global and per-slug queries should now say "killed"
    assert kill_switch_service.is_globally_killed() is True
    assert kill_switch_service.is_killed("any-slug") is True
    assert kill_switch_service.is_killed("another-slug") is True


def test_release_global_clears_only_global_not_per_project(_isolate_state_file):
    from app.services import kill_switch_service

    async def _go():
        await kill_switch_service.engage_global(reason="g")
        await kill_switch_service.engage_project("alpha", reason="p")
        await kill_switch_service.release_global()

    asyncio.run(_go())
    assert kill_switch_service.is_globally_killed() is False
    # Per-project kill should still be engaged
    assert kill_switch_service.is_project_killed("alpha") is True
    assert kill_switch_service.is_killed("alpha") is True
    assert kill_switch_service.is_killed("beta") is False


def test_engage_project_only_kills_that_project(_isolate_state_file):
    from app.services import kill_switch_service

    async def _go():
        await kill_switch_service.engage_project("alpha", reason="bad-state")

    asyncio.run(_go())
    assert kill_switch_service.is_project_killed("alpha") is True
    assert kill_switch_service.is_project_killed("beta") is False
    assert kill_switch_service.is_killed("alpha") is True
    assert kill_switch_service.is_killed("beta") is False


def test_release_project_removes_entry(_isolate_state_file):
    from app.services import kill_switch_service

    async def _go():
        await kill_switch_service.engage_project("alpha", reason="r")
        await kill_switch_service.release_project("alpha")

    asyncio.run(_go())
    assert kill_switch_service.is_project_killed("alpha") is False
    state = json.loads(Path(_isolate_state_file).read_text())
    assert "alpha" not in state["projects"]


def test_engage_global_signals_active_autopilots_to_stop(_isolate_state_file):
    """The global engage must flip _active_autopilots[slug]=False for every
    project the autopilot service is tracking, so loops break on next tick."""
    from app.services import kill_switch_service, autopilot_service

    autopilot_service._active_autopilots.clear()
    autopilot_service._autopilot_configs.clear()
    autopilot_service._active_autopilots["alpha"] = True
    autopilot_service._active_autopilots["beta"] = True

    async def _go():
        # Stub planner_service and running_agent_service so we don't hit Convex.
        with (
            patch("app.services.planner_service.get_project_by_slug", side_effect=AsyncMockReturnNone),
        ):
            return await kill_switch_service.engage_global(reason="test")

    result = asyncio.run(_go())
    assert result["engaged"] is True
    assert result["autopilots_signaled"] == 2
    assert autopilot_service._active_autopilots["alpha"] is False
    assert autopilot_service._active_autopilots["beta"] is False


async def AsyncMockReturnNone(*args, **kwargs):
    return None


def test_start_autopilot_refuses_when_killed(_isolate_state_file):
    """start_autopilot should bail out if the kill switch is engaged."""
    from app.services import kill_switch_service, autopilot_service

    autopilot_service._active_autopilots.clear()
    autopilot_service._autopilot_configs.clear()

    async def _go():
        await kill_switch_service.engage_global(reason="test")
        await autopilot_service.start_autopilot("alpha", auto_approve=True)

    asyncio.run(_go())
    # Loop must NOT have been entered.
    assert autopilot_service._active_autopilots.get("alpha") is not True


def test_status_returns_full_snapshot(_isolate_state_file):
    from app.services import kill_switch_service

    async def _go():
        await kill_switch_service.engage_global(reason="g-reason")
        await kill_switch_service.engage_project("alpha", reason="a-reason")
        await kill_switch_service.engage_project("beta", reason="b-reason")

    asyncio.run(_go())
    s = kill_switch_service.status()
    assert s["global"]["engaged"] is True
    assert s["global"]["reason"] == "g-reason"
    assert set(s["projects"].keys()) == {"alpha", "beta"}
    assert s["projects"]["alpha"]["reason"] == "a-reason"
