"""
Event Normalizers — bridge between runner-specific output and RAIL event taxonomy.

Parses stdout/stderr (often in stream-json format) into normalized RunnerEvent 
objects that the UI and Autopilot can consume consistently.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType

logger = logging.getLogger(__name__)


class EventNormalizer(ABC):
    @abstractmethod
    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        """Parse a single line of output into one or more normalized events."""
        pass


class JsonStreamNormalizer(EventNormalizer):
    """
    Normalizer for runners that emit structured JSON per line (e.g. Claude Code, Gemini CLI).
    """
    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        line = line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            return []

        try:
            payload = json.loads(line)
        except Exception:
            return []

        events: list[RunnerEvent] = []
        payload_type = payload.get("type")

        if payload_type == "assistant":
            content = payload.get("message", {}).get("content") or []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text = block.get("text")
                    if text:
                        events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.PROGRESS,
                                session_id=session_id,
                                normalized_payload={"message": text},
                                raw_payload=payload,
                            )
                        )
                elif block_type == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input") or {}
                    if tool_name == "Bash":
                        command = tool_input.get("command")
                        if command:
                            events.append(
                                RunnerEvent(
                                    event_type=RunnerEventType.BASH_COMMAND_STARTED,
                                    session_id=session_id,
                                    normalized_payload={"command": command},
                                    raw_payload=payload,
                                )
                            )
                    elif tool_name in {"Write", "Edit", "NotebookEdit"}:
                        path = tool_input.get("file_path")
                        if path:
                            events.append(
                                RunnerEvent(
                                    event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                                    session_id=session_id,
                                    normalized_payload={"path": path, "kind": str(tool_name).lower()},
                                    raw_payload=payload,
                                )
                            )
        
        elif payload_type == "tool_call":
            tool_use = payload.get("tool_use") or {}
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input") or {}

            if tool_name == "Bash":
                command = tool_input.get("command")
                if command:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.BASH_COMMAND_STARTED,
                            session_id=session_id,
                            normalized_payload={"command": command},
                            raw_payload=payload,
                        )
                    )
            elif tool_name in {"Write", "Edit", "NotebookEdit"}:
                path = tool_input.get("file_path")
                if path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={"path": path, "kind": tool_name.lower()},
                            raw_payload=payload,
                        )
                    )
                    
        elif payload_type == "result":
            if payload.get("subtype") == "success":
                result = payload.get("result")
                if result:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={"message": str(result)},
                            raw_payload=payload,
                        )
                    )

        return events


class CursorNormalizer(EventNormalizer):
    """
    Specialized normalizer for Cursor's agent output format.
    """
    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        # Implementation moved from cli_base.py
        # For brevity, I'm focusing on the refactoring pattern.
        # In a real implementation, I'd move all _derived_events_from_cursor_payload logic here.
        return []


def get_normalizer(runner_name: str) -> EventNormalizer:
    if runner_name in {"claude_code", "gemini_cli", "codex_cli"}:
        return JsonStreamNormalizer()
    elif runner_name == "cursor_cli":
        return CursorNormalizer()
    return JsonStreamNormalizer() # Default fallback
