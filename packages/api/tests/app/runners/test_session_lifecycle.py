import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from app.runners.session_lifecycle import create_runner_session, get_runner_session, ingest_session_events, append_session_command
from app.runners.base import RunnerEvent, RunnerEventType

@pytest.fixture
def mock_convex():
    with patch("app.runners.session_lifecycle.convex", new_callable=AsyncMock) as mock:
        mock.query.return_value = {"_id": "proj_1", "slug": "test-slug", "localRepoPath": "/tmp"}
        yield mock

@pytest.fixture
def mock_running_agent_service():
    with patch("app.runners.session_lifecycle.running_agent_service", new_callable=AsyncMock) as mock:
        mock.find_active_worker.return_value = None
        mock.create_running_agent.return_value = "session_id_1"
        mock.get_running_agent.return_value = {
            "projectId": "proj_1",
            "sessionPath": "/tmp/research_plan/sessions/data/session_id_1",
            "externalSessionId": "ext_1",
            "runner": "jules",
            "role": "data",
            "taskId": "task_1"
        }
        yield mock

@pytest.fixture
def mock_session_files():
    with patch("app.runners.session_lifecycle.session_files") as mock:
        mock.ensure_session_root.return_value = Path("/tmp/research_plan/sessions/data/session_id_1")
        mock.list_events.return_value = []
        mock.append_event.return_value = {}
        mock.append_command.return_value = {"id": 1, "processed": False}
        mock.read_state.return_value = {"status": "running"}
        yield mock

@pytest.fixture
def mock_runner_factory():
    with patch("app.runners.session_lifecycle.resolve_runner_for_project") as mock:
        runner_mock = AsyncMock()
        runner_mock.create_session.return_value = {"session_id": "ext_1", "status": "IN_PROGRESS", "url": "http://jules"}
        runner_mock.get_session.return_value = {"session_id": "ext_1", "status": "COMPLETED", "normalized_status": "completed"}
        runner_mock.list_events.return_value = [
            RunnerEvent(event_type=RunnerEventType.FILE_CHANGE_DETECTED, session_id="ext_1", normalized_payload={"path": "test.txt"})
        ]
        mock.return_value = runner_mock
        yield mock, runner_mock

@pytest.fixture
def mock_jules_api_key():
    with patch("app.runners.session_lifecycle.resolve_jules_api_key", new_callable=AsyncMock) as mock:
        mock.return_value = "test-api-key"
        yield mock

@pytest.fixture
def mock_relay_events():
    with patch("app.runners.session_lifecycle._relay_runner_event", new_callable=AsyncMock) as mock:
        yield mock

@pytest.mark.asyncio
async def test_create_runner_session(mock_convex, mock_running_agent_service, mock_session_files, mock_runner_factory, mock_jules_api_key):
    _, runner_mock = mock_runner_factory

    res = await create_runner_session(
        project_id="proj_1",
        project_slug="test-slug",
        task_id="task_1",
        runner_name="jules",
        role="data",
        task_description="do some task",
        repo_url="http://r",
        branch="main"
    )

    assert res["convex_session_id"] == "session_id_1"
    assert res["external_session_id"] == "ext_1"
    assert res["status"] == "IN_PROGRESS"

    runner_mock.create_session.assert_called_once()
    mock_running_agent_service.create_running_agent.assert_called_once()
    mock_running_agent_service.update_running_agent.assert_called()

@pytest.mark.asyncio
async def test_get_runner_session(mock_convex, mock_running_agent_service, mock_session_files, mock_runner_factory, mock_jules_api_key):
    _, runner_mock = mock_runner_factory

    with patch("app.runners.session_lifecycle.Path.exists", return_value=True):
        res = await get_runner_session("session_id_1", sync_from_runner=True)

    assert res["status"] == "completed"
    assert res["runnerInfo"]["normalized_status"] == "completed"
    runner_mock.get_session.assert_called_once_with("ext_1")

@pytest.mark.asyncio
async def test_ingest_session_events(mock_convex, mock_running_agent_service, mock_session_files, mock_runner_factory, mock_jules_api_key, mock_relay_events):
    _, runner_mock = mock_runner_factory

    with patch("app.runners.session_lifecycle.Path.exists", return_value=True):
        ingested = await ingest_session_events("session_id_1")

    assert len(ingested) == 1
    assert ingested[0]["event_type"] == "file_change_detected"

    mock_session_files.append_event.assert_called_once()
    mock_relay_events.assert_called_once()
