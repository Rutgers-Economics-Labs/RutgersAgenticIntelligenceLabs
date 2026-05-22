"""
Event Normalizers — bridge between runner-specific output and RAIL event taxonomy.

Parses stdout/stderr (often in stream-json format) into normalized RunnerEvent
objects that the UI and Autopilot can consume consistently.

Each CLI emits a different shape; routing happens in get_normalizer() below.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from app.runners.base import RunnerEvent, RunnerEventType

logger = logging.getLogger(__name__)


def _try_parse_json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        return json.loads(line)
    except Exception:
        return None


class EventNormalizer(ABC):
    @abstractmethod
    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        """Parse a single line of output into one or more normalized events."""
        pass


class ClaudeCodeNormalizer(EventNormalizer):
    """Claude Code stream-json format.

    Tool calls arrive as `tool_use` blocks inside `assistant.message.content`.
    A separate top-level `tool_call` shape is also tolerated for forward compat.
    """

    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        payload = _try_parse_json(line)
        if payload is None:
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
                    events.extend(
                        _claude_tool_use_events(session_id, block, payload)
                    )

        elif payload_type == "tool_call":
            events.extend(
                _claude_tool_use_events(session_id, payload.get("tool_use") or {}, payload)
            )

        elif payload_type == "result" and payload.get("subtype") == "success":
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


def _claude_tool_use_events(
    session_id: str, block: dict[str, Any], payload: dict[str, Any]
) -> list[RunnerEvent]:
    tool_name = block.get("name")
    tool_input = block.get("input") or {}
    events: list[RunnerEvent] = []
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
    return events


class CodexCliNormalizer(EventNormalizer):
    """Codex CLI (`codex exec --json`) emits item/turn events.

    Notable shapes:
      - item.completed + item.type=file_change → FILE_CHANGE_DETECTED (one per change)
      - item.completed + item.type=command_execution → BASH_COMMAND_COMPLETED
      - turn.completed → COMPLETED with usage carried through
    """

    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        payload = _try_parse_json(line)
        if payload is None:
            return []

        events: list[RunnerEvent] = []
        payload_type = payload.get("type")

        if payload_type == "item.completed":
            item = payload.get("item") or {}
            item_type = item.get("type")
            if item_type == "file_change":
                for change in item.get("changes") or []:
                    if not isinstance(change, dict):
                        continue
                    path = change.get("path")
                    if not path:
                        continue
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={
                                "path": path,
                                "kind": str(change.get("kind") or "change").lower(),
                            },
                            raw_payload=payload,
                        )
                    )
            elif item_type == "command_execution":
                command = item.get("command")
                if command:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.BASH_COMMAND_COMPLETED,
                            session_id=session_id,
                            normalized_payload={
                                "command": command,
                                "output": item.get("aggregated_output") or "",
                                "exit_code": item.get("exit_code"),
                            },
                            raw_payload=payload,
                        )
                    )
            elif item_type == "agent_message":
                text = item.get("text")
                if text:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={"message": text},
                            raw_payload=payload,
                        )
                    )

        elif payload_type == "turn.completed":
            events.append(
                RunnerEvent(
                    event_type=RunnerEventType.COMPLETED,
                    session_id=session_id,
                    normalized_payload={
                        "status": "completed",
                        "usage": payload.get("usage") or {},
                    },
                    raw_payload=payload,
                )
            )

        return events


class GeminiCliNormalizer(EventNormalizer):
    """Gemini CLI emits top-level `tool_use` with `tool_name` and `parameters`.

    - tool_name=write_file → FILE_CHANGE_DETECTED on parameters.file_path
    - tool_name=run_shell_command → BASH_COMMAND_STARTED on parameters.command
    - any other tool_use → PROGRESS surfacing the summary or tool name
    """

    _FILE_TOOLS = {"write_file", "edit_file", "create_file"}
    _BASH_TOOLS = {"run_shell_command", "execute_shell"}

    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        payload = _try_parse_json(line)
        if payload is None:
            return []

        payload_type = payload.get("type")

        if payload_type == "message" and payload.get("role") == "assistant":
            content = payload.get("content")
            if isinstance(content, str) and content:
                return [
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": content},
                        raw_payload=payload,
                    )
                ]
            return []

        if payload_type == "result":
            status = str(payload.get("status") or "completed").lower()
            return [
                RunnerEvent(
                    event_type=RunnerEventType.COMPLETED,
                    session_id=session_id,
                    normalized_payload={
                        "status": status,
                        "stats": payload.get("stats") or {},
                    },
                    raw_payload=payload,
                )
            ]

        if payload_type != "tool_use":
            return []

        events: list[RunnerEvent] = []
        tool_name = payload.get("tool_name")
        params = payload.get("parameters") or {}

        if tool_name in self._FILE_TOOLS:
            path = params.get("file_path") or params.get("path")
            if path:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                        session_id=session_id,
                        normalized_payload={"path": path, "kind": tool_name},
                        raw_payload=payload,
                    )
                )
        elif tool_name in self._BASH_TOOLS:
            command = params.get("command")
            if command:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.BASH_COMMAND_STARTED,
                        session_id=session_id,
                        normalized_payload={"command": command},
                        raw_payload=payload,
                    )
                )
        else:
            # Generic tool_use — surface the summary (or fall back to tool name)
            # as progress so the UI shows the agent is doing something.
            message = params.get("summary") or params.get("text") or tool_name
            if message:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": str(message)},
                        raw_payload=payload,
                    )
                )

        return events


class CursorCliNormalizer(EventNormalizer):
    """Cursor agent stream-json format.

    Cursor emits:
      - assistant text blocks like Claude (`assistant.message.content[].text`)
      - tool_call envelopes whose payload is keyed by tool kind, e.g.
        `tool_call.editToolCall.args.path` for file edits.
    """

    _FILE_TOOL_KEYS = {"editToolCall", "writeToolCall", "createFileToolCall"}

    def normalize_line(self, session_id: str, line: str) -> list[RunnerEvent]:
        payload = _try_parse_json(line)
        if payload is None:
            return []

        events: list[RunnerEvent] = []
        payload_type = payload.get("type")
        subtype = payload.get("subtype")

        if payload_type == "assistant":
            content = payload.get("message", {}).get("content") or []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
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

        elif payload_type == "thinking" and subtype == "delta":
            text = payload.get("text")
            if text:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": text, "kind": "thinking"},
                        raw_payload=payload,
                    )
                )

        elif payload_type == "tool_call":
            # Cursor emits the same tool_call envelope twice (started + completed);
            # only surface the completed one to avoid duplicate FILE_CHANGE events.
            # Treat envelopes without a subtype as completed for forward compat
            # with the previous test fixture shape.
            if subtype not in (None, "completed"):
                return events
            tool_call = payload.get("tool_call") or {}
            for key in self._FILE_TOOL_KEYS:
                envelope = tool_call.get(key)
                if not isinstance(envelope, dict):
                    continue
                args = envelope.get("args") or {}
                path = args.get("path") or args.get("file_path")
                if path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={"path": path, "kind": key},
                            raw_payload=payload,
                        )
                    )
                    break

        elif payload_type == "result":
            status = "completed" if not payload.get("is_error") else "failed"
            events.append(
                RunnerEvent(
                    event_type=RunnerEventType.COMPLETED,
                    session_id=session_id,
                    normalized_payload={
                        "status": status,
                        "usage": payload.get("usage") or {},
                    },
                    raw_payload=payload,
                )
            )

        return events


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_NORMALIZERS: dict[str, type[EventNormalizer]] = {
    "claude_code": ClaudeCodeNormalizer,
    "codex_cli": CodexCliNormalizer,
    "gemini_cli": GeminiCliNormalizer,
    "cursor_cli": CursorCliNormalizer,
}


def get_normalizer(runner_name: str) -> EventNormalizer:
    cls = _NORMALIZERS.get(runner_name, ClaudeCodeNormalizer)
    return cls()


# Backwards-compat alias kept for callers that imported the old name.
JsonStreamNormalizer = ClaudeCodeNormalizer
CursorNormalizer = CursorCliNormalizer
