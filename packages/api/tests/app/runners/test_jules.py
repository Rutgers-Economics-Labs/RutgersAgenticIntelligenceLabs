import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.runners.base import RunnerEventType, TaskPayload
from app.runners.jules import JulesRunner

@pytest.fixture
def runner():
    return JulesRunner(
        api_key="test-api-key",
        api_url="https://api.test/v1alpha",
        source="test-source"
    )

@pytest.fixture
def mock_httpx_post():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "sess-1", "name": "sessions/sess-1", "state": "IN_PROGRESS", "url": "http://test"}
        mock_post.return_value = mock_resp
        yield mock_post

@pytest.fixture
def mock_httpx_get():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "sess-1", "name": "sessions/sess-1", "state": "COMPLETED"}
        mock_get.return_value = mock_resp
        yield mock_get

@pytest.mark.asyncio
async def test_create_session(runner, mock_httpx_post):
    payload = TaskPayload(
        project_slug="p1",
        role="test-role",
        task_id="t1",
        repo_url="http://r",
        branch="main",
        task_description="do work",
        allowed_paths=["path/1"],
        acceptance_criteria=["crit1"]
    )
    result = await runner.create_session(payload)
    assert result["session_id"] == "sess-1"
    assert result["status"] == "IN_PROGRESS"

@pytest.mark.asyncio
async def test_get_session(runner, mock_httpx_get):
    result = await runner.get_session("sess-1")
    assert result["session_id"] == "sess-1"
    assert result["status"] == "COMPLETED"
    assert result["normalized_status"] == RunnerEventType.COMPLETED.value

@pytest.mark.asyncio
async def test_list_events(runner):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp1 = MagicMock()
        mock_resp1.json.return_value = {"name": "sessions/sess-1"}
        mock_resp2 = MagicMock()
        mock_resp2.json.return_value = {"activities": [{"fileChanged": {"path": "test.txt"}}]}
        mock_get.side_effect = [mock_resp1, mock_resp2]

        events = await runner.list_events("sess-1")
        assert len(events) == 1
        assert events[0].event_type == RunnerEventType.FILE_CHANGE_DETECTED
        assert events[0].normalized_payload["path"] == "test.txt"
        assert events[0].debug_visibility is True # fileChanged is not in the set of False flags

@pytest.mark.asyncio
async def test_approve(runner):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get_resp = MagicMock()
        mock_get_resp.json.return_value = {"name": "sessions/sess-1"}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post.return_value = mock_post_resp

        await runner.approve("sess-1", {"message": "good to go"})
        # Called once for sending the message
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "sessions/sess-1:sendMessage" in args[0]
        assert kwargs["json"]["prompt"] == "good to go"
