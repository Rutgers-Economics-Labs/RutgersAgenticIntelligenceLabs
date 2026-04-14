"""
app.runners — vendor-agnostic runner abstraction layer.

Public surface:
    BaseRunner      — abstract interface all adapters implement
    RunnerEvent     — normalized event emitted by any runner
    RunnerEventType — canonical event type enum
    TaskPayload     — structured task payload sent to a runner
    JulesRunner     — Jules (jules.googleapis.com) adapter
    RunnerFactory   — resolves runner instances by name
"""
from app.runners.base import BaseRunner, RunnerEvent, RunnerEventType, TaskPayload
from app.runners.jules import JulesRunner
from app.runners.factory import RunnerFactory

__all__ = [
    "BaseRunner",
    "RunnerEvent",
    "RunnerEventType",
    "TaskPayload",
    "JulesRunner",
    "RunnerFactory",
]
