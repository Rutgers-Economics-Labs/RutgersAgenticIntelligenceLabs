import asyncio
from pathlib import Path
import pytest
from app.services import session_files
from app.runners import session_lifecycle

@pytest.mark.asyncio
async def test_planner_flushes_to_file(tmp_path: Path):
    """
    Mocks a running planner and verifies that emitted events correctly append to session.ndjson.
    """
    # 1. Setup session root
    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-live-1")
    
    # 2. Mock a live event stream (simulate planner)
    class MockPlanner:
        def __init__(self):
            self.events_emitted = 0
            
        async def run(self, session_root_path: Path):
            # Emulate an event being emitted by the planner
            session_files.append_event(
                session_root_path,
                "assistant_message",
                role="assistant",
                content="Live planning in progress...",
                status="running"
            )
            self.events_emitted += 1
            
    planner = MockPlanner()
    await planner.run(session_root)
    
    # 3. Verify event is appended and accessible
    events = session_files.list_events(session_root)
    assert len(events) == 1
    assert events[0]["content"] == "Live planning in progress..."
    
    # 4. In a real scenario, this would verify the integration layer,
    # expecting the runner lifecycle to handle this automatically.
    # We assert that the integration layer exists on session_lifecycle.
    assert hasattr(session_lifecycle, "flush_live_events"), "Integration logic 'flush_live_events' is missing!"

@pytest.mark.asyncio
async def test_commands_are_acknowledged(tmp_path: Path):
    """
    Injects a command into commands.ndjson and verifies the runner picks it up, 
    acts on it, and marks it as processed exactly once.
    """
    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-live-2")
    
    # 1. Inject a command
    command = session_files.append_command(
        session_root,
        "inject_message",
        content="Please stop planning."
    )
    
    assert command["processed"] is False
    
    # 2. Runner processes command
    # Expecting an integration method on session_lifecycle to handle this
    assert hasattr(session_lifecycle, "process_pending_commands"), "Integration logic 'process_pending_commands' is missing!"
    
    # (The test fails here intentionally as the method does not exist yet)
    await session_lifecycle.process_pending_commands(session_root)
    
    # 3. Verify it was marked
    commands = session_files.list_commands(session_root)
    assert len(commands) == 1
    assert commands[0]["processed"] is True
