"""SessionResult — required exit artifact every runner must emit.

Written by the agent at session end to
research_plan/sessions/<id>/session_result.json.

If absent at finalization, the session is `complete_unverified` and not
eligible for promotion regardless of any other signals. This is the
forcing function that pulls all six runners onto a shared output contract
instead of letting RAIL parse free-form stdout.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.runners.contracts.work_order import TaskType, WorkOrderId


class SessionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    NEEDS_FOLLOWUP = "needs_followup"


class TrustState(str, Enum):
    """Granular trust levels for research artifacts (Track B)."""
    DRAFT = "draft"
    CANDIDATE = "candidate"
    ANALYSIS_READY = "analysis_ready"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"
    REJECTED = "rejected"
    BLOCKED_FOR_PROMOTION = "blocked_for_promotion"
    SUPERSEDED = "superseded"


class SourceMaterializationState(str, Enum):
    """Granular source states (Track B)."""
    CANDIDATE = "candidate"
    ADMISSIBLE = "admissible"
    CONFIGURED = "configured"
    FETCHABLE = "fetchable"
    FETCHED = "fetched_extract"
    NORMALIZED = "normalized_dataset"
    HYDRATED = "hydrated_dataset"
    ANALYSIS_READY = "analysis_ready_dataset"
    TRUSTED = "trusted_evidence_source"


class ClaimCandidate(BaseModel):
    """A claim the agent surfaced during the session.

    Always emitted in candidate state — the promotion lane decides whether
    to upgrade to verified/rejected. Evidence refs are loose strings on
    purpose: they may point to datasets, source records, prior claims, or
    analyses, and the integrity service resolves them later.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    status: TrustState = TrustState.CANDIDATE
    evidence_refs: list[str] = Field(default_factory=list)
    verification_status: str = "pending"
    confidence: float | None = None
    notes: str | None = None


class SourceRecord(BaseModel):
    """A source the agent identified or materialized.

    Distinct from claim evidence: this records WHAT was used, not WHAT was
    concluded. Admissibility is evaluated by the integrity service against
    project policy.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    name: str
    provider: str | None = None
    access_url: str | None = None
    access_method: str | None = None
    """fetched | manual_ingest | scraped | api_call | local_file"""
    admissibility: str = "unverified"
    """unverified | admissible | inadmissible | pending_review"""
    materialization_state: SourceMaterializationState = SourceMaterializationState.CANDIDATE
    materialized_path: str | None = None
    notes: str | None = None


class DatasetRecord(BaseModel):
    """A dataset the agent produced or modified.

    Linked back to source records via source_ids so the lineage stays
    traceable. file_path is the canonical location relative to project root.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    file_path: str
    source_ids: list[str] = Field(default_factory=list)
    row_count: int | None = None
    schema_summary: str | None = None
    """One-line description of columns/shape for the next agent to read."""


class Blocker(BaseModel):
    """Something that prevented the agent from completing the work order.

    category drives downstream routing (data_gap -> source discovery,
    methodology_choice -> Q&A, runtime_error -> repair). Recommended
    follow-up lets the agent suggest a fix instead of just complaining.
    """

    model_config = ConfigDict(extra="forbid")

    blocker_id: str | None = None
    category: str
    """data_gap | methodology_choice | runtime_error | permission_denied |
    out_of_scope | needs_human | unknown | source_admissibility"""
    summary: str
    detail: str | None = None
    recommended_followup: str | None = None
    """One-line suggestion for what task to spawn next."""

    # Track B: Liveness & Anti-Stuck fields
    severity: str | None = None
    """e.g. promotion_blocking, research_blocking"""
    blocks: list[str] = Field(default_factory=list)
    does_not_block: list[str] = Field(default_factory=list)
    owner_lane: str | None = None
    allowed_resolutions: list[str] = Field(default_factory=list)
    max_repair_attempts: int | None = None
    next_action: str | None = None


class VerificationRequest(BaseModel):
    """How RAIL should verify the outputs from this session.

    Wired into the existing _run_workspace_verification path: command is
    invoked, expected_outputs are checked to exist + non-empty. claims_to_verify
    is the new field — claim-level verification (Phase 6+).
    """

    model_config = ConfigDict(extra="forbid")

    command: str
    """Shell command to run, relative to project root."""
    expected_outputs: list[str] = Field(default_factory=list)
    claims_to_verify: list[str] = Field(default_factory=list)
    """claim_ids whose evidence chain should be re-validated."""


class RecommendedTask(BaseModel):
    """The agent's suggestion for what to do next.

    Planner is free to ignore — these are advisory, not commands. But
    surfacing them lets the agent express "I noticed something out of
    scope" without silently abandoning the lead.
    """

    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    reason: str
    capabilities_hint: list[str] = Field(default_factory=list)


class DomainProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_sources: int = 0
    new_datasets: int = 0
    new_claim_candidates: int = 0
    new_analysis_artifacts: int = 0
    new_verified_claims: int = 0


class TrustChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: str
    object_id: str
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")


class SessionResult(BaseModel):
    """The required exit artifact for every session, every runner, every time.

    Absence at finalization == complete_unverified status, regardless of
    what the session's git diff shows. This is intentional: without
    structured output, RAIL has no way to validate the work, link claims
    to evidence, or measure runner quality on the scoreboard.

    Conservative migration: existing sessions that don't yet emit
    session_result.json continue to land with `complete_unverified`
    instead of failing. Only new dispatches via WorkOrder require it.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    work_order_id: WorkOrderId | None = None

    status: SessionStatus
    summary: str
    task_type: TaskType
    runner_name: str

    files_changed: list[str] = Field(default_factory=list)
    claims: list[ClaimCandidate] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    datasets: list[DatasetRecord] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)

    # Track B: Liveness
    domain_progress: DomainProgress = Field(default_factory=DomainProgress)
    trust_changes: list[TrustChange] = Field(default_factory=list)
    promotion_blockers: list[str] = Field(default_factory=list)
    research_blockers: list[str] = Field(default_factory=list)

    # Q&A linkage (Phase 4)
    questions_asked: list[str] = Field(default_factory=list)
    """question_ids of questions raised via rail.ask during this session."""

    verification: VerificationRequest | None = None
    next_recommended_tasks: list[RecommendedTask] = Field(default_factory=list)

    # Cost / time accounting (Phase 5 / scoreboard)
    cost_recorded_usd: float | None = None
    duration_seconds: float | None = None

    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


_LEGACY_ROLE_TO_TASK_TYPE: dict[str, TaskType] = {
    "data": TaskType.DATA_INGESTION,
    "research": TaskType.ANALYSIS,
    "analysis": TaskType.ANALYSIS,
    "artifact": TaskType.ARTIFACT_WRITING,
    "health": TaskType.HEALTH_REPAIR,
    "coding": TaskType.ANALYSIS,
    "planner": TaskType.ANALYSIS,
    "verification": TaskType.VERIFICATION,
    "source_discovery": TaskType.SOURCE_DISCOVERY,
    "claim": TaskType.CLAIM_EXTRACTION,
}


def _normalize_legacy_blockers(raw_blockers: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_blockers, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, blocker in enumerate(raw_blockers):
        if isinstance(blocker, dict):
            normalized.append(blocker)
            continue
        summary = str(blocker or "").strip()
        if not summary:
            continue
        normalized.append(
            {
                "blocker_id": f"legacy-blocker-{index + 1}",
                "category": "unknown",
                "summary": summary,
            }
        )
    return normalized


def _normalize_legacy_task_type(value: Any, role: str | None) -> str:
    task_type = str(value or "").strip().lower()
    valid_values = {item.value for item in TaskType}
    if task_type in valid_values:
        return task_type
    inferred = _LEGACY_ROLE_TO_TASK_TYPE.get(str(role or "").strip().lower())
    if inferred is not None:
        return inferred.value
    return TaskType.ANALYSIS.value


def normalize_session_result_payload(
    raw_result: dict[str, Any],
    *,
    session_id: str | None = None,
    role: str | None = None,
    runner_name: str | None = None,
    task_type: str | TaskType | None = None,
) -> dict[str, Any]:
    """Coerce older runner outputs into the current SessionResult contract."""
    normalized = deepcopy(raw_result)

    normalized.setdefault("session_id", normalized.get("agent_session_id") or session_id or "")
    normalized.setdefault("summary", str(normalized.get("summary") or "").strip() or "Legacy session result")
    if not normalized.get("runner_name") and normalized.get("runner"):
        normalized["runner_name"] = normalized.get("runner")
    if not role and normalized.get("assigned_role"):
        role = str(normalized.get("assigned_role") or "").strip().lower() or role

    legacy_status = str(normalized.get("status") or "").strip().lower()
    if legacy_status == "completed_with_blockers":
        normalized["status"] = (
            SessionStatus.NEEDS_FOLLOWUP.value
            if normalized.get("blockers")
            else SessionStatus.COMPLETED.value
        )

    task_type_hint = task_type.value if isinstance(task_type, TaskType) else task_type
    normalized["task_type"] = _normalize_legacy_task_type(
        normalized.get("task_type") or task_type_hint,
        role,
    )
    normalized["runner_name"] = (
        str(normalized.get("runner_name") or runner_name or role or "unknown").strip() or "unknown"
    )

    file_paths: list[str] = []
    for key in ("files_changed", "updated_paths", "artifacts_updated"):
        values = normalized.get(key)
        if isinstance(values, list):
            file_paths.extend(str(item).strip() for item in values if str(item).strip())
    artifact_entries = normalized.get("artifacts")
    if isinstance(artifact_entries, list):
        for item in artifact_entries:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path:
                file_paths.append(path)
    outputs = normalized.get("outputs")
    if isinstance(outputs, dict):
        for value in outputs.values():
            if isinstance(value, str) and value.strip():
                file_paths.append(value.strip())
            elif isinstance(value, list):
                file_paths.extend(str(item).strip() for item in value if str(item).strip())
    evidence = normalized.get("evidence")
    if isinstance(evidence, list):
        file_paths.extend(str(item).strip() for item in evidence if str(item).strip())
    normalized["files_changed"] = sorted(dict.fromkeys(file_paths))

    normalized["blockers"] = _normalize_legacy_blockers(normalized.get("blockers"))

    verification = normalized.get("verification")
    if isinstance(verification, dict):
        if "command" not in verification:
            normalized.pop("verification", None)
        else:
            normalized["verification"] = {
                "command": verification.get("command"),
                "expected_outputs": verification.get("expected_outputs") or [],
                "claims_to_verify": verification.get("claims_to_verify") or [],
            }
    else:
        normalized.pop("verification", None)

    if not isinstance(normalized.get("domain_progress"), dict):
        normalized["domain_progress"] = {}
    normalized["domain_progress"].pop("produced", None)
    normalized["domain_progress"].pop("summary", None)
    if normalized.pop("produced_domain_progress", False) and not any(normalized["domain_progress"].values()):
        artifact_count = len(normalized["files_changed"]) or 1
        normalized["domain_progress"]["new_analysis_artifacts"] = max(
            int(normalized["domain_progress"].get("new_analysis_artifacts") or 0),
            artifact_count,
        )

    completed_at = normalized.get("completed_at") or normalized.get("timestamp_utc") or normalized.get("generated_at")
    if completed_at:
        normalized["completed_at"] = completed_at

    for key in (
        "agent_session_id",
        "artifacts",
        "artifacts_updated",
        "checks",
        "generated_at",
        "metrics",
        "produced_domain_progress",
        "started_at",
        "task_id",
        "timestamp_utc",
        "updated_paths",
        "assigned_role",
        "created_at",
        "evidence",
        "outputs",
        "runner",
        "updated_at",
    ):
        normalized.pop(key, None)

    return normalized


def parse_session_result(
    raw_result: dict[str, Any],
    *,
    session_id: str | None = None,
    role: str | None = None,
    runner_name: str | None = None,
    task_type: str | TaskType | None = None,
) -> SessionResult:
    normalized = normalize_session_result_payload(
        raw_result,
        session_id=session_id,
        role=role,
        runner_name=runner_name,
        task_type=task_type,
    )
    return SessionResult.model_validate(normalized)
