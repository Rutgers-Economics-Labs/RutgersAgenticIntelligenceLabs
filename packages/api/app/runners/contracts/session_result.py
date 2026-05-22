"""SessionResult — required exit artifact every runner must emit.

Written by the agent at session end to
research_plan/sessions/<id>/session_result.json.

If absent at finalization, the session is `complete_unverified` and not
eligible for promotion regardless of any other signals. This is the
forcing function that pulls all six runners onto a shared output contract
instead of letting RAIL parse free-form stdout.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.runners.contracts.work_order import TaskType, WorkOrderId


class SessionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    NEEDS_FOLLOWUP = "needs_followup"


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
    status: str = "candidate"
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
