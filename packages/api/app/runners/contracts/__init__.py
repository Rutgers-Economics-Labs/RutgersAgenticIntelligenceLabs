"""Runner Protocol contracts (Phase 0 of docs/future-spec-runner-protocol.md).

These are the three typed contracts every runner must satisfy:

- WorkOrder        — typed dispatch record (planner -> runner)
- SessionResult    — required exit artifact (runner -> RAIL)
- RunnerProfile    — capability declaration (one per registered runner)

They live in their own subpackage because they're the protocol — the rest of
the runner code consumes them but should not define alternate shapes.
"""
from __future__ import annotations

from app.runners.contracts.runner_profile import (
    AdapterType,
    CapabilityState,
    CertificationStatus,
    ExecutionCapabilities,
    OutputContract,
    RunnerProfile,
    SteeringMode,
)
from app.runners.contracts.session_result import (
    Blocker,
    ClaimCandidate,
    DatasetRecord,
    DomainProgress,
    normalize_session_result_payload,
    parse_session_result,
    RecommendedTask,
    SessionResult,
    SessionStatus,
    SourceMaterializationState,
    SourceRecord,
    TrustChange,
    TrustState,
    VerificationRequest,
)
from app.runners.contracts.work_order import (
    Capability,
    ExpectedProgress,
    FailurePolicy,
    TaskType,
    TrustPolicy,
    WorkOrder,
)

__all__ = [
    # work_order
    "Capability",
    "ExpectedProgress",
    "FailurePolicy",
    "TaskType",
    "TrustPolicy",
    "WorkOrder",
    # session_result
    "Blocker",
    "ClaimCandidate",
    "DatasetRecord",
    "DomainProgress",
    "normalize_session_result_payload",
    "parse_session_result",
    "RecommendedTask",
    "SessionResult",
    "SessionStatus",
    "SourceMaterializationState",
    "SourceRecord",
    "TrustChange",
    "TrustState",
    "VerificationRequest",
    # runner_profile
    "AdapterType",
    "CapabilityState",
    "CertificationStatus",
    "ExecutionCapabilities",
    "OutputContract",
    "RunnerProfile",
    "SteeringMode",
]
