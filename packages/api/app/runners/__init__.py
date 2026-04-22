"""
app.runners — vendor-agnostic runner abstraction layer.

Public surface:
    BaseRunner      — abstract interface all adapters implement
    RunnerEvent     — normalized event emitted by any runner
    RunnerEventType — canonical event type enum
    TaskPayload     — structured task payload sent to a runner
    JulesRunner     — Jules (jules.googleapis.com) adapter
    ClaudeCodeRunner / GeminiCliRunner / CursorCliRunner — local CLI adapters
    RunnerFactory   — resolves runner instances by name
"""
from app.runners.base import BaseRunner, RunnerEvent, RunnerEventType, TaskPayload
from app.runners.claude_code import ClaudeCodeRunner
from app.runners.cursor_cli import CursorCliRunner
from app.runners.gemini_cli import GeminiCliRunner
from app.runners.jules import JulesRunner
from app.runners.factory import RunnerFactory

__all__ = [
    "BaseRunner",
    "RunnerEvent",
    "RunnerEventType",
    "TaskPayload",
    "JulesRunner",
    "ClaudeCodeRunner",
    "GeminiCliRunner",
    "CursorCliRunner",
    "RunnerFactory",
]
