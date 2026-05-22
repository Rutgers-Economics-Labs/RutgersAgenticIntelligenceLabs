"""Phase 6 — Context Compilers and Event Normalizers tests.

Covers:
  1. Context compilation for different task types.
  2. JSON stream event normalization (Claude/Gemini format).
"""
from __future__ import annotations

import json
import pytest
from app.runners.base import TaskPayload, RunnerEventType
from app.runners.contracts import TaskType
from app.runners.context_compilers.base import get_compiler
from app.runners.event_normalizers.base import JsonStreamNormalizer

class TestContextCompilers:
    def test_analysis_compiler_framing(self):
        payload = TaskPayload(
            project_slug="test",
            role="research",
            task_id="task-1",
            repo_url="url",
            task_description="Analyze data",
            branch="main"
        )
        compiler = get_compiler(TaskType.ANALYSIS)
        prompt = compiler.compile(payload)
        
        assert "Senior Research Analyst" in prompt
        assert "## Task" in prompt
        assert "Analyze data" in prompt

    def test_data_ingestion_compiler_framing(self):
        payload = TaskPayload(
            project_slug="test",
            role="data",
            task_id="task-1",
            repo_url="url",
            task_description="Fetch data",
            branch="main"
        )
        compiler = get_compiler(TaskType.DATA_INGESTION)
        prompt = compiler.compile(payload)
        
        assert "Data Engineering Specialist" in prompt
        assert "Fetch data" in prompt

class TestEventNormalizers:
    def test_json_stream_normalizer_assistant_message(self):
        normalizer = JsonStreamNormalizer()
        line = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]}
        })
        
        events = normalizer.normalize_line("sess-1", line)
        assert len(events) == 1
        assert events[0].event_type == RunnerEventType.PROGRESS
        assert events[0].normalized_payload["message"] == "Hello world"

    def test_json_stream_normalizer_tool_call(self):
        normalizer = JsonStreamNormalizer()
        line = json.dumps({
            "type": "tool_call",
            "tool_use": {
                "name": "Bash",
                "input": {"command": "ls -la"}
            }
        })
        
        events = normalizer.normalize_line("sess-1", line)
        assert len(events) == 1
        assert events[0].event_type == RunnerEventType.BASH_COMMAND_STARTED
        assert events[0].normalized_payload["command"] == "ls -la"
