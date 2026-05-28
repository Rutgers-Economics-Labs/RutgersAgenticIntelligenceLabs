import asyncio
import logging
import time
import yaml
import subprocess
import os
import platform
from typing import Any

logger = logging.getLogger(__name__)
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, BackgroundTasks, Path as FPath
from pydantic import BaseModel
from rail.bootstrap import bootstrap_future_project
from rail.local import LocalEngine
from rail.manifest import ManifestValidationError, load_manifest

from app.services.convex_client import convex
from app.services import ontology_service, sql_service
from app.services import hydration_worker
from app.services.project_artifacts_service import find_latest_success_job_with_outputs
from app.services import planner_runtime, planner_service
from app.services import running_agent_service
from app.services import session_files
from app.services import command_center_service
from app.services import goal_service
from app.services import reconciliation_service
from app.services.auditor_service import build_auditor_statuses
from app.services.device_service import get_device_metadata
from app.services.hydration_registry_service import (
    get_hydration_status as get_project_hydration_status,
    promote_project_hydration_artifact,
    register_hydration_artifact,
    resolve_pipeline_slug,
)
from app.services.repo_contract_service import (
    ensure_project_boot,
    infer_github_repo,
    manifest_validation_http_detail,
    render_rail_manifest,
)
from app.services.github_service import GitHubService
from app.services.brief_project_service import (
    READY,
    DRAFT,
    MISSING,
    build_preview,
    default_repo_target,
    render_repo_files,
    slugify,
    write_repo_files,
)
from app.services.safe_publish_service import (
    MANIFEST_BACKED_FIELDS,
    publish_manifest,
    publish_config_files,
    record_publish_failure,
    record_publish_success,
    rollback_project_update,
    should_auto_publish,
)
from app.services.secret_service import decrypt_secret_value, encrypt_secret_value, mask_secret_value
from app.services.integrity_service import (
    ALLOWED_PROMOTION_TRANSITIONS,
    apply_source_freshness_policy,
    apply_reproducibility_rerun,
    build_batch_rerun_plan,
    build_rerun_plan,
    evaluate_default_integrity_benchmark_corpus,
    get_artifact_detail,
    list_claim_summaries,
    list_source_summaries,
    get_source_detail,
    get_integrity_dependency_graph,
    get_integrity_repo,
    get_claim_detail,
    get_stale_dependency_graph,
    hybrid_retrieve,
    promote_artifact,
    update_source_and_mark_stale,
    update_assumption_and_mark_stale,
)
from app.services.hypothesis_service import run_critic_review, run_research_burst
from app.services.role_runtime_service import ROLE_ALIASES, load_role_runtime_config
from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy, is_write_capable

router = APIRouter(prefix="/projects", tags=["projects"])


async def _ontology_auditor_status(project: dict[str, Any]) -> dict[str, Any]:
    projection = command_center_service.load_control_plane_summary(project)
    cached = (projection.get("summary") or {}).get("auditors") or {}
    ontology_status = cached.get("ontology")
    if isinstance(ontology_status, dict):
        return ontology_status
    auditors = await build_auditor_statuses(project)
    return (auditors.get("ontology") or {}) if isinstance(auditors, dict) else {}


def _resolve_session_path(project: dict, session: dict) -> str | None:
    session_path = session.get("sessionPath")
    if session_path:
        return session_path
    project_root = project.get("localRepoPath")
    session_id = session.get("_id") or session.get("sessionId")
    role = session.get("role")
    if not project_root or not session_id:
        return None
    if role:
        candidate = session_files.session_root(project_root, role, session_id)
        if candidate.exists():
            return str(candidate)
    sessions_root = Path(project_root) / "research_plan" / "sessions"
    if sessions_root.exists():
        for candidate in sessions_root.glob(f"*/{session_id}"):
            if candidate.exists():
                return str(candidate)
    return None

class RegisterArtifactsBody(BaseModel):
    """Optional explicit paths when job discovery fails (e.g. paths only on disk)."""

    output_db_path: str | None = None
    output_owl_path: str | None = None


class CreateProjectRequest(BaseModel):
    name: str
    slug: str
    description: str = ""
    approach: str = "data-first"
    gitRepoUrl: str | None = None
    localRepoPath: str | None = None
    manifestPath: str | None = "rail.yaml"
    ontologyConfigSlug: str | None = None
    apiConfigSlugs: list[str] = []
    pipelineConfigSlug: str | None = None
    ontologyTemplates: list[str] | None = None


class BootstrapFutureProjectRequest(BaseModel):
    name: str
    slug: str | None = None
    targetDir: str
    defaultBranch: str = "main"
    description: str = ""
    gitRepoUrl: str | None = None


class PlannerMessageRequest(BaseModel):
    role: str
    content: str
    messageType: str = "chat"
    sessionId: str | None = None


class PlannerChatRequest(BaseModel):
    message: str
    model: str | None = None
    history: list[dict] = []


class PlannerTaskRequest(BaseModel):
    title: str
    description: str
    status: str = "backlog"
    agentRole: str
    repoPaths: list[str] = []
    acceptanceCriteria: list[str] = []
    dependsOnTaskIds: list[str] = []
    sessionId: str | None = None
    priority: str | None = None
    runner: str | None = None
    approvalState: str | None = None

class AutopilotRequest(BaseModel):
    enabled: bool
    autoApprove: bool = False
    dispatchApprovalRequired: bool = False


class GoalSpendRequest(BaseModel):
    timeMinutes: int | None = None
    tokens: int | None = None
    apiCostUsd: float | None = None
    retries: int | None = None


class GoalContractRequest(BaseModel):
    objective: str
    successCriteria: list[str]
    requiredEvidence: list[str] = []
    forbiddenShortcuts: list[str] = []
    escalationPolicy: list[str] = []
    allowedSpend: GoalSpendRequest = GoalSpendRequest()
    launchAutopilot: bool = False

class WorkerUpdateRequest(BaseModel):
    message: str
    role: str = "agent"


class PlannerTaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    runner: str | None = None
    repoPaths: list[str] | None = None
    acceptanceCriteria: list[str] | None = None
    approvalState: str | None = None


class DeviceHeartbeatRequest(BaseModel):
    label: str | None = None
    hostname: str | None = None
    platform: str | None = None


class RegisterHydrationArtifactRequest(BaseModel):
    pipelineSlug: str | None = None
    hydrationMode: str = "full"
    ontologyArtifactPath: str | None = None
    duckdbArtifactPath: str | None = None
    status: str = "valid"


class ProjectSecretUpsertRequest(BaseModel):
    keyName: str
    plaintextValue: str


class AgentSecretPolicyUpsertRequest(BaseModel):
    agentRole: str
    allowedSecretNames: list[str]


class ApprovalCreateRequest(BaseModel):
    taskId: str | None = None
    agentSessionId: str | None = None
    approvalType: str
    status: str = "pending"
    requestedByRole: str
    grantedByUserId: str | None = None


class ApprovalResolveRequest(BaseModel):
    status: str
    grantedByUserId: str | None = None
    resolutionNote: str | None = None


class ProjectMetadataSyncRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    gitRepoUrl: str | None = None
    manifestPath: str | None = None
    defaultBranch: str | None = None
    githubSyncMode: str | None = None
    ontologyConfigSlug: str | None = None
    apiConfigSlugs: list[str] | None = None
    pipelineConfigSlug: str | None = None
    agentModel: str | None = None


class ResearchBriefInput(BaseModel):
    brief: str
    model: str | None = None


class CreateProjectFromBriefRequest(BaseModel):
    brief: str
    targetDir: str | None = None
    gitRepoUrl: str | None = None
    defaultBranch: str = "main"
    model: str | None = None
    githubSyncMode: str | None = None


class ProjectRunnerSessionCreateRequest(BaseModel):
    taskId: str | None = None
    role: str
    taskDescription: str
    repoUrl: str | None = None
    branch: str | None = None
    allowedPaths: list[str] = []
    acceptanceCriteria: list[str] = []
    runnerName: str = "default"
    agentRoleForSecrets: str | None = None


class ProjectRunnerCommandRequest(BaseModel):
    commandType: str
    content: str | None = None
    payload: dict | None = None
    idempotencyKey: str | None = None


class ResearchLaunchRequest(BaseModel):
    researchQuestion: str = ""
    audience: str = "project stakeholders"
    deliverables: list[str] = []
    dataConstraints: str = ""
    publicOnly: bool = True
    citationStrictness: str = "strict"
    approvalBeforeWrites: bool = True
    useSubAgents: bool = True
    preferredAgentRoles: list[str] = []
    workflowPresets: list[str] = []
    notes: str = ""


class CatalogProjectActionRequest(BaseModel):
    clone: bool = False
    targetDir: str | None = None


class HydrationRerunRequest(BaseModel):
    pipelineSlug: str | None = None


class IntegrityAssumptionUpdateRequest(BaseModel):
    title: str | None = None
    value: str | None = None
    status: str | None = None
    notes: str | None = None
    affectedPaths: list[str] | None = None


class OntologyFollowUpTaskRequest(BaseModel):
    title: str
    classification: str
    affectedPaths: list[str] | None = None


class IntegritySourceUpdateRequest(BaseModel):
    title: str | None = None
    sourceType: str | None = None
    url: str | None = None
    urlOrPath: str | None = None
    publisher: str | None = None
    origin: str | None = None
    accessDate: str | None = None
    acquiredAt: str | None = None
    accessMethod: str | None = None
    freshnessStatus: str | None = None
    impactLevel: str | None = None
    qualityStatus: str | None = None
    admissibilityStatus: str | None = None
    provenance: dict | None = None
    qualityNotes: str | None = None
    notes: str | None = None


class IntegrityRerunPlanRequest(BaseModel):
    assumptionKey: str


class IntegrityBatchRerunPlanRequest(BaseModel):
    assumptionKeys: list[str]


class IntegrityRecordAssumptionRequest(BaseModel):
    assumptionKey: str
    title: str
    value: str
    status: str = "active"
    notes: str = ""
    affectedPaths: list[str] = []


class IntegrityRecordSourceRequest(BaseModel):
    sourceKey: str
    sourceType: str = "document"
    title: str
    url: str | None = None
    urlOrPath: str | None = None
    publisher: str | None = None
    origin: str | None = None
    accessDate: str | None = None
    acquiredAt: str | None = None
    accessMethod: str | None = None
    freshnessStatus: str = "unknown"
    impactLevel: str = "normal"
    qualityStatus: str = "candidate"
    admissibilityStatus: str | None = None
    provenance: dict = {}
    qualityNotes: str | None = None
    notes: str = ""


class IntegrityRecordClaimRequest(BaseModel):
    claimKey: str
    statement: str
    artifactPath: str | None = None
    status: str = "draft"
    evidencePaths: list[str] = []
    evidenceChunkKeys: list[str] = []
    sourceKeys: list[str] = []
    contradictsClaimKeys: list[str] = []
    evidenceKind: str | None = None
    caveats: list[str] = []
    openQuestions: list[str] = []
    confidence: float | None = None


class HypothesisUpsertRequest(BaseModel):
    id: str
    statement: str
    scope: str | None = None
    falsifiers: list[str] = []
    status: str = "draft"
    score: float | None = None
    parentId: str | None = None
    claimKeys: list[str] = []
    taskIds: list[str] = []
    artifactPaths: list[str] = []
    humanNotes: str | None = None


class HypothesisPatchRequest(BaseModel):
    statement: str | None = None
    scope: str | None = None
    falsifiers: list[str] | None = None
    status: str | None = None
    score: float | None = None
    parentId: str | None = None
    claimKeys: list[str] | None = None
    taskIds: list[str] | None = None
    artifactPaths: list[str] | None = None
    humanNotes: str | None = None


class CriticReviewRequest(BaseModel):
    hypothesisIds: list[str] | None = None


class ResearchBurstRequest(BaseModel):
    objective: str
    maxParallel: int | None = None


class IntegrityRecordLineageRequest(BaseModel):
    artifactPath: str
    artifactType: str
    title: str
    promotionState: str = "draft"
    reproducibilityMode: str | None = None
    inputs: list[str] = []
    scripts: list[str] = []
    verificationCommands: list[str] = []
    sources: list[str] = []
    assumptions: list[str] = []
    claims: list[str] = []
    verificationRuns: list[str] = []


class IntegrityReproducibilityRerunRequest(BaseModel):
    outputs: dict[str, str] = {}
    runId: str = "rerun-verification"
    scope: str = "health"


class IntegrityFreshnessEvaluationRequest(BaseModel):
    asOf: str | None = None


class IntegrityArtifactPromotionRequest(BaseModel):
    artifactPath: str
    targetState: str


ALLOWED_SOURCE_ADMISSIBILITY_STATUSES = {"observed", "derived", "estimated", "synthetic", "missing"}
ALLOWED_SOURCE_FRESHNESS_STATUSES = {"unknown", "fresh", "needs_refresh", "stale"}
ALLOWED_SOURCE_QUALITY_STATUSES = {"candidate", "validated", "blocked", "rejected"}
ALLOWED_SOURCE_IMPACT_LEVELS = {"low", "normal", "high", "critical"}
ALLOWED_ASSUMPTION_STATUSES = {"active", "needs_review", "superseded", "rejected"}
ALLOWED_CLAIM_STATUSES = {"draft", "supported", "unsupported", "needs_evidence", "superseded", "stale", "conflicted"}
ALLOWED_HYPOTHESIS_STATUSES = {"draft", "supported", "weakened", "rejected", "archived"}
ALLOWED_EVIDENCE_KINDS = {"direct", "derived", "contextual", "semantic_suggestion"}
ALLOWED_PROMOTION_STATES = {"exploratory", "draft", "needs_evidence", "partially_verified", "verified", "stale", "blocked"}
ALLOWED_REPRODUCIBILITY_MODES = {"deterministic", "manual", "non_reproducible"}
ALLOWED_TASK_APPROVAL_STATES = {"pending", "granted"}
ALLOWED_APPROVAL_STATUSES = {"pending", "granted", "rejected", "approved"}
ALLOWED_APPROVAL_TYPES = {"run_task", "research_launch"}
ALLOWED_TASK_RUNNERS = {"default", "jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli", "copilot_cli"}
ALLOWED_TASK_PRIORITIES = {"high", "medium", "low"}
ALLOWED_TASK_AGENT_ROLES = {"research", "data", "coding", "artifact", "health", "planner"}
ALLOWED_PLANNER_MESSAGE_ROLES = {"user", "assistant", "system"} | ALLOWED_TASK_AGENT_ROLES


def _validate_trusted_source_contract(
    *,
    impact_level: str | None,
    quality_status: str | None,
    admissibility_status: str | None,
    freshness_status: str | None,
    provenance: dict | None,
) -> None:
    if impact_level not in {None, ""} and impact_level not in ALLOWED_SOURCE_IMPACT_LEVELS:
        raise HTTPException(
            status_code=422,
            detail="Source impact level must be one of: low, normal, high, critical.",
        )
    if quality_status not in {None, ""} and quality_status not in ALLOWED_SOURCE_QUALITY_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Source quality must be one of: candidate, validated, blocked, rejected.",
        )
    if freshness_status not in {None, ""} and freshness_status not in ALLOWED_SOURCE_FRESHNESS_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Source freshness must be one of: unknown, fresh, needs_refresh, stale.",
        )
    if admissibility_status not in {None, ""} and admissibility_status not in ALLOWED_SOURCE_ADMISSIBILITY_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Source admissibility must be one of: observed, derived, estimated, synthetic, missing."
            ),
        )
    if quality_status != "validated":
        return
    if admissibility_status not in {"observed", "derived"}:
        raise HTTPException(
            status_code=422,
            detail=(
                "Validated sources require explicit admissibility state. "
                "Use `observed` or `derived` for trusted source records."
            ),
        )
    if not isinstance(provenance, dict) or not provenance:
        raise HTTPException(
            status_code=422,
            detail="Validated sources require provenance metadata before they can be treated as trusted.",
        )
    if admissibility_status == "derived" and not (provenance.get("derived_from") or provenance.get("derivedFrom")):
        raise HTTPException(
            status_code=422,
            detail="Validated derived sources must declare `derived_from` provenance before they can be treated as trusted.",
        )
    if freshness_status in {None, "", "unknown"}:
        raise HTTPException(
            status_code=422,
            detail="Validated sources require explicit freshness state before they can be treated as trusted.",
        )


def _validate_assumption_status(status: str | None) -> None:
    if status not in {None, ""} and status not in ALLOWED_ASSUMPTION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Assumption status must be one of: active, needs_review, superseded, rejected.",
        )


def _validate_hypothesis_status(status: str | None) -> None:
    if status not in {None, ""} and status not in ALLOWED_HYPOTHESIS_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Hypothesis status must be one of: draft, supported, weakened, rejected, archived.",
        )


def _validate_planner_task_status(status: str | None) -> None:
    if status not in {None, ""} and status not in set(planner_service.TASK_STATUSES):
        raise HTTPException(
            status_code=422,
            detail="Planner task status must be one of: " + ", ".join(planner_service.TASK_STATUSES) + ".",
        )


def _validate_planner_task_approval_state(approval_state: str | None) -> None:
    if approval_state not in {None, ""} and approval_state not in ALLOWED_TASK_APPROVAL_STATES:
        raise HTTPException(
            status_code=422,
            detail="Planner task approval state must be one of: pending, granted.",
        )


def _validate_planner_task_runner(runner: str | None) -> None:
    if runner not in {None, ""} and runner not in ALLOWED_TASK_RUNNERS:
        raise HTTPException(
            status_code=422,
            detail="Planner task runner must be one of: default, jules, claude_code, gemini_cli, cursor_cli, codex_cli, copilot_cli.",
        )


def _normalize_runner_name(runner: str | None) -> str:
    normalized = str(runner or "jules").strip().lower()
    if normalized not in ALLOWED_TASK_RUNNERS:
        raise HTTPException(
            status_code=422,
            detail="Runner session runnerName must be one of: default, jules, claude_code, gemini_cli, cursor_cli, codex_cli, copilot_cli.",
        )
    return normalized


def _validate_planner_task_priority(priority: str | None) -> None:
    if priority not in {None, ""} and priority not in ALLOWED_TASK_PRIORITIES:
        raise HTTPException(
            status_code=422,
            detail="Planner task priority must be one of: high, medium, low.",
        )


def _normalize_agent_role(agent_role: str | None, *, field_name: str) -> str:
    normalized = str(agent_role or "").strip().lower()
    normalized = ROLE_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_TASK_AGENT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be one of: research, data, coding, artifact, health, planner.",
        )
    return normalized


def _normalize_planner_message_role(role: str | None, *, field_name: str) -> str:
    normalized = str(role or "").strip().lower()
    normalized = ROLE_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_PLANNER_MESSAGE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} must be one of: user, assistant, system, "
                "research, data, coding, artifact, health, planner."
            ),
        )
    return normalized


def _validate_approval_status(status: str | None) -> None:
    if status not in {None, ""} and status not in ALLOWED_APPROVAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Approval status must be one of: pending, granted, rejected.",
        )


def _validate_approval_type(approval_type: str | None) -> None:
    if approval_type not in {None, ""} and approval_type not in ALLOWED_APPROVAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Approval type must be one of: run_task, research_launch.",
        )


def _validate_claim_reference_integrity(
    repo,
    *,
    project_root: Path,
    status: str | None,
    evidence_kind: str | None,
    evidence_paths: list[str],
    source_keys: list[str],
    evidence_chunk_keys: list[str],
) -> None:
    if status not in {None, ""} and status not in ALLOWED_CLAIM_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Claim status must be one of: draft, supported, unsupported, needs_evidence, superseded, stale, conflicted.",
        )
    if evidence_kind not in {None, ""} and evidence_kind not in ALLOWED_EVIDENCE_KINDS:
        raise HTTPException(
            status_code=422,
            detail="Claim evidence kind must be one of: direct, derived, contextual, semantic_suggestion.",
        )
    missing_paths = sorted(
        {
            path
            for path in evidence_paths
            if path
            and not (project_root / path).exists()
        }
    )
    if missing_paths:
        raise HTTPException(
            status_code=422,
            detail="Claim references missing evidence paths: " + ", ".join(missing_paths),
        )

    known_sources = {item.source_key for item in repo.load_sources()}
    missing_sources = sorted({key for key in source_keys if key not in known_sources})
    if missing_sources:
        raise HTTPException(
            status_code=422,
            detail="Claim references unknown source keys: " + ", ".join(missing_sources),
        )

    known_chunks = {item.chunk_key for item in repo.load_evidence_chunks()}
    missing_chunks = sorted({key for key in evidence_chunk_keys if key not in known_chunks})
    if missing_chunks:
        raise HTTPException(
            status_code=422,
            detail="Claim references unknown evidence chunk keys: " + ", ".join(missing_chunks),
        )


def _normalize_integrity_reference(reference: str) -> str:
    return str(reference).split("#", 1)[-1].strip()


def _validate_artifact_lineage_references(
    repo,
    *,
    project_root: Path,
    promotion_state: str | None,
    reproducibility_mode: str | None,
    inputs: list[str],
    scripts: list[str],
    sources: list[str],
    assumptions: list[str],
    claims: list[str],
    verification_runs: list[str],
) -> None:
    if promotion_state not in {None, ""} and promotion_state not in ALLOWED_PROMOTION_STATES:
        raise HTTPException(
            status_code=422,
            detail="Artifact promotion state must be one of: exploratory, draft, needs_evidence, partially_verified, verified, stale, blocked.",
        )
    if reproducibility_mode not in {None, ""} and reproducibility_mode not in ALLOWED_REPRODUCIBILITY_MODES:
        raise HTTPException(
            status_code=422,
            detail="Artifact reproducibility mode must be one of: deterministic, manual, non_reproducible.",
        )
    missing_inputs = sorted(
        {
            path
            for path in inputs
            if path
            and not (project_root / path).exists()
        }
    )
    if missing_inputs:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references missing input paths: " + ", ".join(missing_inputs),
        )

    missing_scripts = sorted(
        {
            path
            for path in scripts
            if path
            and not (project_root / path).exists()
        }
    )
    if missing_scripts:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references missing script paths: " + ", ".join(missing_scripts),
        )

    known_sources = {item.source_key for item in repo.load_sources()}
    missing_sources = sorted(
        {
            _normalize_integrity_reference(reference)
            for reference in sources
            if _normalize_integrity_reference(reference) not in known_sources
        }
    )
    if missing_sources:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references unknown source keys: " + ", ".join(missing_sources),
        )

    known_assumptions = {item.assumption_key for item in repo.load_assumptions()}
    missing_assumptions = sorted(
        {
            _normalize_integrity_reference(reference)
            for reference in assumptions
            if _normalize_integrity_reference(reference) not in known_assumptions
        }
    )
    if missing_assumptions:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references unknown assumption keys: " + ", ".join(missing_assumptions),
        )

    known_claims = {item.claim_key for item in repo.load_claims()}
    missing_claims = sorted(
        {
            _normalize_integrity_reference(reference)
            for reference in claims
            if _normalize_integrity_reference(reference) not in known_claims
        }
    )
    if missing_claims:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references unknown claim keys: " + ", ".join(missing_claims),
        )

    known_runs = {item.run_id for item in repo.load_verification_runs()}
    missing_runs = sorted(
        {
            _normalize_integrity_reference(reference)
            for reference in verification_runs
            if _normalize_integrity_reference(reference) not in known_runs
        }
    )
    if missing_runs:
        raise HTTPException(
            status_code=422,
            detail="Artifact lineage references unknown verification runs: " + ", ".join(missing_runs),
        )


def _validate_trusted_artifact_lineage_contract(
    *,
    promotion_state: str | None,
    inputs: list[str],
    scripts: list[str],
    verification_runs: list[str],
) -> None:
    has_workflow_support = bool(inputs or scripts or verification_runs)
    if promotion_state == "verified" and not verification_runs:
        raise HTTPException(
            status_code=409,
            detail=(
                "Verified artifact lineage writes require recorded verification runs before the artifact "
                "can be written in trusted state."
            ),
        )
    if promotion_state == "partially_verified" and not has_workflow_support:
        raise HTTPException(
            status_code=409,
            detail=(
                "Partially verified artifact lineage writes require workflow support "
                "(inputs, scripts, or verification runs)."
            ),
        )


def _csv_query_param(value: str | None) -> list[str] | None:
    if not value:
        return None
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or None


# Catalog projects are now managed in Convex.


def _projects_base_dir() -> Path:
    default_base = Path(__file__).resolve().parents[4]
    return Path(os.environ.get("RAIL_PROJECTS_DIR", str(default_base))).expanduser().resolve()


def _local_catalog_roots() -> list[Path]:
    base = _projects_base_dir()
    candidates = [base, base / "generated_projects"]
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def _local_catalog_projects() -> list[dict]:
    projects: list[dict] = []
    seen_slugs: set[str] = set()
    for base in _local_catalog_roots():
        for root in sorted(base.iterdir()):
            if not root.is_dir() or not (root / "rail.yaml").exists():
                continue
            fallback = {
                "name": root.name,
                "slug": root.name,
                "description": "",
            }
            metadata = _manifest_metadata(root, fallback)
            slug = str(metadata.get("slug") or root.name).strip()
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            projects.append(
                {
                    "_id": f"local:{slug}",
                    "name": metadata.get("name") or root.name,
                    "slug": slug,
                    "description": metadata.get("description") or "",
                    "status": "ready",
                    "localRepoPath": str(root),
                    "manifestPath": "rail.yaml",
                    "defaultBranch": metadata.get("defaultBranch") or "main",
                    "pipelineConfigSlug": metadata.get("pipelineConfigSlug"),
                }
            )
    return projects


async def _known_project(slug: str) -> dict | None:
    return await convex.query("projects:getBySlug", {"slug": slug})


async def _catalog_project_by_slug(slug: str) -> dict | None:
    project = await _known_project(slug)
    if project:
        return project
    for candidate in _local_catalog_projects():
        if candidate.get("slug") == slug:
            return candidate
    return None


def _manifest_metadata(root: Path, fallback: dict) -> dict:
    manifest_path = root / "rail.yaml"
    if not manifest_path.exists():
        return {}
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    project = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    hydration = raw.get("hydration") if isinstance(raw.get("hydration"), dict) else {}
    return {
        "name": project.get("name") or fallback["name"],
        "slug": project.get("slug") or fallback["slug"],
        "description": project.get("description") or fallback["description"],
        "defaultBranch": project.get("default_branch") or project.get("defaultBranch") or "main",
        "pipelineConfigSlug": hydration.get("default_pipeline") or hydration.get("pipeline") or None,
    }


async def _upsert_known_project_record(defn: dict, root: Path) -> dict:
    metadata = _manifest_metadata(root, defn)
    slug = metadata.get("slug") or defn["slug"]
    existing = await convex.query("projects:getBySlug", {"slug": slug})
    git_repo_url = defn.get("gitRepoUrl") or defn.get("repoUrl")
    payload = {
        "name": metadata.get("name") or defn["name"],
        "slug": slug,
        "description": metadata.get("description") or defn["description"],
        "localRepoPath": str(root),
        "manifestPath": "rail.yaml",
    }
    if git_repo_url:
        payload["gitRepoUrl"] = git_repo_url
    if metadata.get("pipelineConfigSlug"):
        payload["pipelineConfigSlug"] = metadata["pipelineConfigSlug"]
    if existing:
        await convex.mutation(
            "projects:updateById",
            {
                "projectId": existing["_id"],
                **{key: value for key, value in payload.items() if key != "slug"},
            },
        )
        return await convex.query("projects:getBySlug", {"slug": slug}) or {**existing, **payload}
    project_id = await convex.mutation("projects:create", {**payload, "approach": "ontology-first"})
    return await convex.query("projects:getById", {"projectId": project_id}) or {**payload, "_id": project_id}


async def _catalog_row(project: dict) -> dict:
    repo_path = project.get("localRepoPath")
    if repo_path:
        root = Path(repo_path).expanduser().resolve()
    else:
        # Fallback if localRepoPath is missing
        root = _projects_base_dir() / project["slug"]
        
    metadata = _manifest_metadata(root, project) if root.exists() else {}
    projection = command_center_service.load_control_plane_summary(
        {
            **project,
            "localRepoPath": str(root),
        }
    )
    summary = projection["summary"]
    snapshot = projection["snapshot"]
    task_counts = summary.get("taskCounts") or {}
    by_status = task_counts.get("byStatus") or {}
    closed_count = sum(
        int(count or 0)
        for status, count in by_status.items()
        if status in {"done", "completed", "cancelled"}
    )
    return {
        "name": project.get("name") or metadata.get("name"),
        "slug": project["slug"],
        "description": project.get("description") or metadata.get("description"),
        "repoUrl": project.get("gitRepoUrl"),
        "localRepoPath": str(root),
        "localExists": root.exists(),
        "manifestExists": (root / "rail.yaml").exists(),
        "backendProject": project,
        "needsClone": not root.exists(),
        "progress": {
            "closed": closed_count,
            "total": int(task_counts.get("total") or 0),
        },
        "controlPlane": {
            "phase": summary.get("lifecyclePhase"),
            "nextAction": summary.get("nextAction"),
            "snapshotLoaded": bool(snapshot.get("loaded")),
        },
    }


def _configured_pipeline_slug(project: dict, project_root: Path, requested: str | None = None) -> str:
    if requested:
        return requested
    return resolve_pipeline_slug(project, project_root)


def _project_catalog_score(project: dict) -> tuple[int, int, int, int, float]:
    return (
        1 if project.get("status") == "hydrated" else 0,
        1 if project.get("gitRepoUrl") else 0,
        1 if project.get("github") else 0,
        1 if project.get("localRepoPath") else 0,
        float(project.get("updatedAt") or project.get("_creationTime") or 0),
    )


def _dedupe_projects_for_catalog(projects: list[dict]) -> list[dict]:
    best_by_slug: dict[str, dict] = {}
    for project in projects:
        slug = str(project.get("slug") or "").strip()
        if not slug:
            continue
        current = best_by_slug.get(slug)
        if current is None or _project_catalog_score(project) > _project_catalog_score(current):
            best_by_slug[slug] = project
    return list(best_by_slug.values())


def _local_hydration_configs(project_root: Path, pipeline_slug: str) -> tuple[str, dict[str, str], dict[str, str]] | None:
    pipeline_path = project_root / ".ontology" / "pipelines" / f"{pipeline_slug}.yaml"
    if not pipeline_path.exists():
        return None
    pipeline_content = pipeline_path.read_text(encoding="utf-8")
    try:
        pipeline_spec = yaml.safe_load(pipeline_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"Local pipeline YAML is invalid: {exc}") from exc

    api_configs: dict[str, str] = {}
    for step in pipeline_spec.get("steps") or []:
        if not isinstance(step, dict) or not step.get("api"):
            continue
        api_slug = str(step["api"])
        source_path = project_root / ".ontology" / "sources" / f"{api_slug}.yaml"
        if source_path.exists():
            api_configs[api_slug] = source_path.read_text(encoding="utf-8")

    onto_configs: dict[str, str] = {}
    onto_ref = str(pipeline_spec.get("ontology", "core") or "core")
    
    # Prefer the ontology file named directly by the pipeline before falling back
    # to generic scaffold locations.
    candidate_paths = [
        project_root / onto_ref,
        project_root / ".ontology" / "ontologies" / f"{onto_ref}.yaml",
        project_root / ".ontology" / "ontologies" / f"{Path(onto_ref).stem}.yaml",
        project_root / ".ontology" / "ontology.yaml",
    ]
    
    for onto_path in candidate_paths:
        if onto_path.exists():
            onto_content = onto_path.read_text(encoding="utf-8")
            onto_configs[onto_ref] = onto_content
            onto_configs[Path(onto_ref).stem] = onto_content
            break

    return pipeline_content, api_configs, onto_configs


def _git_init(path: Path, *, default_branch: str = "main") -> None:
    if (path / ".git").exists():
        return
    result = subprocess.run(
        ["git", "init", "--initial-branch", default_branch, str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git init failed: {result.stderr or result.stdout}")


def _git_has_commits(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _git_create_initial_commit(
    path: Path,
    *,
    default_branch: str = "main",
    message: str = "chore: initial project scaffold from RAIL brief",
) -> str | None:
    status = subprocess.run(
        ["git", "-C", str(path), "status", "--short"],
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr or status.stdout}")

    if _git_has_commits(path) and not status.stdout.strip():
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            raise RuntimeError(f"git rev-parse failed: {head.stderr or head.stdout}")
        return head.stdout.strip()

    checkout = subprocess.run(
        ["git", "-C", str(path), "checkout", "-B", default_branch],
        capture_output=True,
        text=True,
    )
    if checkout.returncode != 0:
        raise RuntimeError(f"git checkout failed: {checkout.stderr or checkout.stdout}")

    add = subprocess.run(
        ["git", "-C", str(path), "add", "-A"],
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr or add.stdout}")

    commit = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=RAIL Bot",
            "-c",
            "user.email=rail-bot@rutgers.edu",
            "commit",
            "--allow-empty",
            "-m",
            message,
        ],
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr or commit.stdout}")

    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {head.stderr or head.stdout}")
    return head.stdout.strip()


def _git_set_remote(path: Path, remote_name: str, remote_url: str) -> None:
    current = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", remote_name],
        capture_output=True,
        text=True,
    )
    if current.returncode == 0:
        if current.stdout.strip() == remote_url:
            return
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "set-url", remote_name, remote_url],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["git", "-C", str(path), "remote", "add", remote_name, remote_url],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise RuntimeError(f"git remote configuration failed: {result.stderr or result.stdout}")


def _collect_repo_text_files(repo_root: Path) -> list[dict[str, str]]:
    repo_files: list[dict[str, str]] = []
    for file_path in repo_root.rglob("*"):
        if not file_path.is_file() or ".git" in file_path.parts:
            continue
        rel = file_path.relative_to(repo_root).as_posix()
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        repo_files.append({"path": rel, "content": content})
    return repo_files


async def _ensure_project_github_repo(
    *,
    slug: str,
    description: str,
    git_repo_url: str | None,
) -> tuple[str, str | None]:
    resolved_url = (git_repo_url or "").strip()
    if resolved_url:
        return resolved_url, infer_github_repo(resolved_url)

    short_slug = slug[:40].rstrip("-")
    repo_name = f"RAIL-{short_slug}"
    created = await GitHubService().create_repo(
        name=repo_name,
        description=description,
        private=True,
    )
    resolved_url = str(created.get("html_url") or created.get("clone_url") or "")
    if not resolved_url and created.get("full_name"):
        resolved_url = f"https://github.com/{created['full_name']}"
    return resolved_url, infer_github_repo(resolved_url)


async def _push_initial_repo_snapshot_via_github_app(
    *,
    repo_root: Path,
    git_repo: str | None,
    git_repo_url: str | None,
    default_branch: str,
    message: str,
) -> list[dict[str, Any]]:
    if not git_repo:
        return []
    if git_repo_url and (repo_root / ".git").exists():
        _git_set_remote(repo_root, "origin", git_repo_url)
    repo_files = _collect_repo_text_files(repo_root)
    if not repo_files:
        return []
    result = await GitHubService().commit_files(git_repo, default_branch, repo_files, message)
    return [result]


def _relative_to_project(project_root: Path | None, path: Path | None) -> str | None:
    if project_root is None or path is None or not path.exists():
        return None
    return str(path.relative_to(project_root))


def _session_review_model(project: dict, session: dict) -> dict:
    project_root = Path(project["localRepoPath"]) if project.get("localRepoPath") else None
    resolved_session_path = _resolve_session_path(project, session)
    session_path = Path(resolved_session_path) if resolved_session_path else None
    state = session_files.read_state(session_path) if session_path and session_path.exists() else {}
    return {
        "workspacePath": state.get("workspace_path"),
        "workspaceBranch": state.get("workspace_branch"),
        "reviewStatus": state.get("review_status"),
        "runnerEventCursor": state.get("runner_event_cursor"),
        "summaryPath": _relative_to_project(project_root, session_path / "summary.md" if session_path else None),
        "diffPath": _relative_to_project(project_root, session_path / "diff.md" if session_path else None),
        "todosPath": _relative_to_project(project_root, session_path / "todos.md" if session_path else None),
        "verificationPath": _relative_to_project(project_root, session_path / "verification.md" if session_path else None),
    }


@router.post("/")
async def create_project(data: CreateProjectRequest):
    project_data = data.model_dump()
    project_root = Path(data.localRepoPath).expanduser().resolve() if data.localRepoPath else None
    git_repo_url = data.gitRepoUrl

    # Process ontologyTemplates if provided
    ontology_templates = project_data.pop("ontologyTemplates", None)
    if ontology_templates:
        merged_onto = {
            "uri": f"http://rail.rutgers.edu/ontology/{data.slug}",
            "classes": [],
            "data_properties": [],
            "object_properties": []
        }
        for template_slug in ontology_templates:
            tpl = await convex.query("ontologyTemplates:getBySlug", {"slug": template_slug})
            if tpl and tpl.get("content"):
                tpl_content = yaml.safe_load(tpl["content"])
                merged_onto["classes"].extend(tpl_content.get("classes", []))
                merged_onto["data_properties"].extend(tpl_content.get("data_properties", []))
                merged_onto["object_properties"].extend(tpl_content.get("object_properties", []))

        # Create as the project's initial ontologyConfig
        config_slug = f"{data.slug}-ontology"
        await convex.mutation("configs:createOntology", {
            "name": f"{data.name} Ontology",
            "slug": config_slug,
            "content": yaml.dump(merged_onto),
            "parsedSpec": merged_onto,
            "ontologyUri": merged_onto["uri"],
            "isPublic": False
        })
        project_data["ontologyConfigSlug"] = config_slug
        project_data["ontologyTemplates"] = ontology_templates

    if project_root is not None and project_root.exists():
        try:
            git_repo_url, git_repo = await _ensure_project_github_repo(
                slug=data.slug,
                description=data.description or f"RAIL project: {data.name}",
                git_repo_url=git_repo_url,
            )
            project_data["gitRepoUrl"] = git_repo_url
            project_data["github"] = git_repo or ""
            _git_init(project_root)
            _git_create_initial_commit(
                project_root,
                message="chore: initial project scaffold from RAIL project create",
            )
            await _push_initial_repo_snapshot_via_github_app(
                repo_root=project_root,
                git_repo=git_repo,
                git_repo_url=git_repo_url,
                default_branch="main",
                message="chore: initial project scaffold from RAIL project create",
            )
        except Exception as exc:
            logger.error("Automatic GitHub bootstrap failed for project '%s': %s", data.slug, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Automatic GitHub bootstrap failed: {exc}",
            )

    project_id = await convex.mutation("projects:create", project_data)
    return await convex.query("projects:getBySlug", {"slug": data.slug})


@router.get("")
async def list_projects_catalog():
    remote_projects = await convex.query("projects:list", {}) or []
    projects = _dedupe_projects_for_catalog([*remote_projects, *_local_catalog_projects()])
    rows = []
    for project in projects:
        try:
            rows.append(await _catalog_row(project))
        except Exception as exc:
            rows.append(
                {
                    **project,
                    "localExists": False,
                    "error": str(exc),
                }
            )
    return {"projects": rows}


@router.post("/catalog/{slug}/activate")
async def activate_catalog_project(slug: str, data: CatalogProjectActionRequest):
    defn = await _catalog_project_by_slug(slug)
    if not defn:
        raise HTTPException(404, f"Unknown catalog project '{slug}'")

    repo_path = defn.get("localRepoPath")
    if data.targetDir:
        root = Path(data.targetDir).expanduser().resolve()
    elif repo_path:
        root = Path(repo_path).expanduser().resolve()
    else:
        root = _projects_base_dir() / defn["slug"]
    if root.exists() and not root.is_dir():
        raise HTTPException(409, f"Target exists but is not a directory: {root}")
    if not root.exists():
        if not data.clone:
            return {
                "status": "clone_required",
                "project": None,
                "catalogProject": {
                    **defn,
                    "localRepoPath": str(root),
                    "localExists": False,
                    "manifestExists": False,
                    "needsClone": True,
                },
            }
        root.parent.mkdir(parents=True, exist_ok=True)
        clone_url = defn.get("gitRepoUrl") or defn.get("repoUrl")
        if not clone_url:
            raise HTTPException(409, f"Catalog project '{slug}' has no repo URL to clone")
        github_repo = infer_github_repo(clone_url)
        if github_repo:
            token = await GitHubService().get_installation_token(github_repo)
            # Embed token into HTTPS URL: https://x-access-token:<token>@github.com/...
            clone_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
        result = subprocess.run(["git", "clone", clone_url, str(root)], capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(500, f"git clone failed: {result.stderr or result.stdout}")

    project = await _upsert_known_project_record(defn, root)
    try:
        ensure_project_boot(root)
    except ManifestValidationError as exc:
        raise HTTPException(status_code=422, detail=manifest_validation_http_detail(exc)) from exc
    reconcile_result = await reconciliation_service.reconcile_project_reality(project)
    refreshed_project = await planner_service.get_project_by_slug(project.get("slug") or defn["slug"])
    if refreshed_project:
        project = refreshed_project
    row = await _catalog_row(project)
    return {
        "status": "ready",
        "project": project,
        "catalogProject": row,
        "reconcile": reconcile_result,
    }


@router.post("/future/bootstrap")
async def bootstrap_future_project_route(data: BootstrapFutureProjectRequest):
    root = bootstrap_future_project(
        data.targetDir,
        name=data.name,
        slug=data.slug,
        default_branch=data.defaultBranch,
    )

    try:
        manifest = ensure_project_boot(root)
    except ManifestValidationError as exc:
        raise HTTPException(status_code=422, detail=manifest_validation_http_detail(exc)) from exc
    manifest_slug = manifest.project.slug
    git_repo_url, git_repo = await _ensure_project_github_repo(
        slug=manifest_slug,
        description=data.description or "Future RAIL project",
        git_repo_url=data.gitRepoUrl,
    )
    _git_init(root, default_branch=data.defaultBranch)
    _git_create_initial_commit(
        root,
        default_branch=data.defaultBranch,
        message="chore: initial future RAIL project scaffold",
    )
    await _push_initial_repo_snapshot_via_github_app(
        repo_root=root,
        git_repo=git_repo,
        git_repo_url=git_repo_url,
        default_branch=data.defaultBranch,
        message="chore: initial future RAIL project scaffold",
    )
    project_id = await convex.mutation(
        "projects:create",
        {
            "name": data.name,
            "slug": manifest_slug,
            "description": data.description or "Future RAIL project",
            "approach": "ontology-first",
            "gitRepoUrl": git_repo_url,
            "github": git_repo or "",
            "localRepoPath": str(root),
            "manifestPath": "rail.yaml",
            "defaultBranch": data.defaultBranch,
        },
    )
    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project could not be loaded after bootstrap")
    await planner_service.ensure_planner_thread(project_id)
    board = await planner_service.ensure_main_board(project)
    await planner_service.append_planner_message(
        project=project,
        role="system",
        content="Planner thread initialized.",
        message_type="system",
    )
    await planner_service.sync_planner_files(project, board)
    return await convex.query("projects:getById", {"projectId": project_id})


@router.post("/from-brief/preview")
async def preview_project_from_brief(data: ResearchBriefInput):
    if not data.brief.strip():
        raise HTTPException(400, "Brief is required")
    return await build_preview(data.brief, model=data.model)


@router.post("/from-brief/create")
async def create_project_from_brief(data: CreateProjectFromBriefRequest):
    if not data.brief.strip():
        raise HTTPException(400, "Brief is required")

    preview = await build_preview(data.brief, model=data.model)
    project_meta = preview["project"]
    slug = project_meta["slug"]
    existing = await convex.query("projects:getBySlug", {"slug": slug})
    if existing:
        raise HTTPException(409, f"Project '{slug}' already exists")

    repo_root = Path(data.targetDir).expanduser().resolve() if data.targetDir else default_repo_target(Path(__file__).resolve().parents[4], slug)
    repo_root.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_future_project(repo_root, name=project_meta["name"], slug=slug, default_branch=data.defaultBranch)
    write_repo_files(repo_root, preview["repoFiles"])
    _git_init(repo_root, default_branch=data.defaultBranch)

    try:
        git_repo_url, git_repo = await _ensure_project_github_repo(
            slug=slug,
            description=project_meta.get("description", ""),
            git_repo_url=data.gitRepoUrl,
        )
    except Exception as exc:
        logger.error("GitHub repo creation failed for project '%s': %s", slug, exc)
        raise HTTPException(
            status_code=502,
            detail=f"GitHub repo creation failed: {exc}. Check that the GitHub App has 'administration: write' permission on the org.",
        )
    project_id = await convex.mutation(
        "projects:create",
        {
            "name": project_meta["name"],
            "slug": slug,
            "description": project_meta["description"],
            "approach": project_meta.get("approach", "ontology-first"),
            "gitRepoUrl": git_repo_url or "",
            "localRepoPath": str(repo_root),
            "manifestPath": "rail.yaml",
        },
    )

    ontology = preview["ontology"]
    pipeline = preview["pipeline"]
    ready_or_draft_sources = [source for source in preview["sourceCandidates"] if source["readiness"] in {READY, DRAFT}]
    created_source_slugs: list[str] = []
    for source in ready_or_draft_sources:
        parsed_source = yaml.safe_load(source["content"]) or {}
        await convex.mutation(
            "configs:createApi",
            {
                "name": source["name"],
                "slug": source["slug"],
                "content": source["content"],
                "parsedSpec": parsed_source,
                "sourceType": parsed_source.get("type", "api"),
                "isPublic": False,
                "tags": [],
            },
        )
        created_source_slugs.append(source["slug"])

    await convex.mutation(
        "configs:createOntology",
        {
            "name": ontology["name"],
            "slug": ontology["slug"],
            "content": ontology["content"],
            "parsedSpec": ontology["parsedSpec"],
            "ontologyUri": ontology["parsedSpec"]["uri"],
            "isPublic": False,
        },
    )
    await convex.mutation(
        "configs:createPipeline",
        {
            "name": pipeline["name"],
            "slug": pipeline["slug"],
            "content": pipeline["content"],
            "parsedSpec": pipeline["parsedSpec"],
            "referencedApiSlugs": pipeline["referencedApiSlugs"],
            "isPublic": False,
            "tags": [],
        },
    )

    await convex.mutation(
        "projects:updateById",
        {
            "projectId": project_id,
            "ontologyConfigSlug": ontology["slug"],
            "apiConfigSlugs": created_source_slugs,
            "pipelineConfigSlug": pipeline["slug"],
            "defaultBranch": data.defaultBranch,
            "github": git_repo or "",
            "status": "draft",
        },
    )

    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project could not be loaded after creation")
    rail_path = repo_root / "rail.yaml"
    existing_rail = rail_path.read_text(encoding="utf-8") if rail_path.exists() else None
    rail_path.write_text(render_rail_manifest(project, existing_rail), encoding="utf-8")
    try:
        _git_create_initial_commit(
            repo_root,
            default_branch=data.defaultBranch,
            message="chore: initial project scaffold from RAIL brief",
        )
    except Exception as exc:
        logger.error("Initial local scaffold commit failed for '%s': %s", slug, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Initial local scaffold commit failed: {exc}",
        )

    try:
        await _push_initial_repo_snapshot_via_github_app(
            repo_root=repo_root,
            git_repo=git_repo,
            git_repo_url=git_repo_url,
            default_branch=data.defaultBranch,
            message="chore: initial project scaffold from RAIL brief",
        )
    except Exception as exc:
        logger.error("Initial scaffold push to GitHub failed for '%s': %s", git_repo, exc)

    await planner_service.ensure_planner_thread(project_id)
    board = await planner_service.ensure_main_board(project)
    await planner_service.append_planner_message(
        project=project,
        role="system",
        content="Project created from a brief. Review the generated research graph, source readiness, and hydration plan before running hydration.",
        message_type="system",
    )
    await planner_service.sync_planner_files(project, board)

    publish_results: list[dict] = []
    if project and await should_auto_publish(project):
        try:
            publish_results.append(await publish_manifest(project))
            await record_publish_success(project_id, publish_results[-1])
            publish_results.append(await publish_config_files(project, "ontologies", ontology["slug"], ontology["content"], action="create"))
            await record_publish_success(project_id, publish_results[-1])
            publish_results.append(await publish_config_files(project, "pipelines", pipeline["slug"], pipeline["content"], action="create"))
            await record_publish_success(project_id, publish_results[-1])
            for source in ready_or_draft_sources:
                result = await publish_config_files(project, "apis", source["slug"], source["content"], action="create")
                publish_results.append(result)
                await record_publish_success(project_id, result)
        except Exception as exc:
            await record_publish_failure(project_id, str(exc))

    updated = await convex.query("projects:getById", {"projectId": project_id})
    return {
        "project": updated,
        "preview": preview,
        "publish": publish_results,
        "hydrationReady": False,
        "nextAction": "Review draft sources if needed, then approve hydration separately.",
    }


@router.post("/{slug}/register-artifacts")
async def register_artifacts_from_job(
    slug: str,
    job_id: str | None = Query(None, alias="jobId"),
    body: RegisterArtifactsBody | None = Body(None),
):
    """
    Copy ontology artifact paths from a successful hydration job onto the Convex project.

    Use when hydration finished but the project doc was never updated (428 Sync Required).
    Defaults to the latest successful job for this project that has outputDbPath.
    Optional JSON body: {"output_db_path": "/abs/path/onto.db", "output_owl_path": "..."} to set paths without job lookup.
    """
    try:
        project = await planner_service.get_project_by_slug(slug)
    except ValueError:
        raise HTTPException(404, "Project not found")

    job: dict | None = None
    db_key: str | None = None
    owl_key: str | None = None
    last_job_convex_id: str | None = None

    if body and body.output_db_path:
        db_key = body.output_db_path.strip()
        owl_key = body.output_owl_path
        if job_id:
            j = await convex.query("jobs:get", {"jobId": job_id})
            if j:
                last_job_convex_id = j["_id"]
    elif job_id:
        job = await convex.query("jobs:get", {"jobId": job_id})
        if not job:
            raise HTTPException(404, "Job not found")
        if job.get("status") not in ("success", "completed"):
            raise HTTPException(400, "Job is not in success status")
        db_key = job.get("outputDbPath")
        owl_key = job.get("outputOwlPath")
        last_job_convex_id = job["_id"]
    else:
        job = await find_latest_success_job_with_outputs(project)
        if not job:
            raise HTTPException(
                400,
                "No successful hydration job with stored outputs found for this project. "
                "Run hydration with this project selected, POST with ?jobId=..., or send "
                '{"output_db_path": "/path/to/onto.db"} in the request body.',
            )
        db_key = job.get("outputDbPath")
        owl_key = job.get("outputOwlPath")
        last_job_convex_id = job["_id"]

    if not db_key:
        raise HTTPException(400, "Job has no outputDbPath stored")

    parent = Path(db_key).parent
    duckdb_path = str(parent / "onto.duckdb")
    try:
        await promote_project_hydration_artifact(
            project=project,
            ontology_artifact_path=db_key,
            duckdb_artifact_path=duckdb_path,
            owl_artifact_path=owl_key,
            embeddings_artifact_path=str(parent / "embeddings.db"),
            status="hydrated",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if last_job_convex_id is not None and not str(project.get("_id") or "").startswith("local:"):
        await convex.mutation(
            "projects:updateById",
            {
                "projectId": project["_id"],
                "lastJobId": last_job_convex_id,
            },
        )

    # Warm ontology on the same thread the API uses for Owlready2 (executor), not the event loop.
    db_path = Path(db_key).resolve()
    if db_path.is_file():
        try:
            await ontology_service.ensure_loaded_async(str(db_path), project_id=slug)
        except Exception:
            pass
    duck_p = Path(duckdb_path).resolve()
    if duck_p.is_file():
        try:
            sql_service.set_path(str(duck_p))
        except Exception:
            pass

    return {
        "ok": True,
        "jobId": last_job_convex_id,
        "activeOntologyDbPath": db_key,
        "activeOntologyDuckdbPath": duckdb_path,
    }


@router.post("/{slug}/clear-hydration")
async def clear_hydration(slug: str):
    """
    Clear the active ontology artifact paths and reset the project status to 'ready'.
    The artifact files on disk are NOT deleted — only the Convex project record is patched.
    """
    try:
        project = await planner_service.get_project_by_slug(slug)
    except ValueError:
        raise HTTPException(404, "Project not found")

    project_id = str(project.get("_id") or "")
    if project_id.startswith("local:"):
        project_root = Path(project["localRepoPath"]).resolve() if project.get("localRepoPath") else None
        if not project_root:
            raise HTTPException(400, "Project does not have a localRepoPath configured")
        hydration_meta = project_root / ".ontology" / ".rail_hydration.json"
        hydration_meta.unlink(missing_ok=True)
        return {"ok": True, "slug": slug, "status": "ready", "mode": "local_repo"}

    await convex.mutation("projects:clearHydration", {"projectId": project["_id"]})
    return {"ok": True, "slug": slug, "status": "ready", "mode": "convex"}


@router.post("/{slug}/sync-metadata")
async def sync_project_metadata(slug: str, data: ProjectMetadataSyncRequest):
    try:
        project = await planner_service.get_project_by_slug(slug)
    except ValueError:
        raise HTTPException(404, "Project not found")

    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if "gitRepoUrl" in patch:
        inferred_repo = infer_github_repo(patch["gitRepoUrl"])
        if inferred_repo:
            patch["github"] = inferred_repo

    is_local_only = str(project.get("_id") or "").startswith("local:")
    if is_local_only:
        project_root = planner_service.project_root_from_record(project)
        if project_root is None:
            raise HTTPException(status_code=400, detail="Project has no local repo path configured")
        manifest_path = project_root / (project.get("manifestPath") or "rail.yaml")
        existing_content = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        updated_project = {**project, **patch}
        manifest_content = render_rail_manifest(updated_project, existing_content)
        manifest_path.write_text(manifest_content, encoding="utf-8")
        updated = await planner_service.get_project_by_slug(slug)
    else:
        await convex.mutation("projects:updateById", {
            "projectId": project["_id"],
            **patch,
        })
        updated = await convex.query("projects:getById", {"projectId": project["_id"]})

    publish_result = None
    should_publish_manifest = any(field in patch for field in MANIFEST_BACKED_FIELDS)
    if should_publish_manifest and updated and not is_local_only and await should_auto_publish(updated):
        try:
            publish_result = await publish_manifest(updated)
            await record_publish_success(updated["_id"], publish_result)
        except Exception as exc:
            await rollback_project_update(project["_id"], project)
            await record_publish_failure(project["_id"], str(exc))
            raise HTTPException(502, f"Project update rolled back because GitHub publish failed: {exc}")

    return {"project": updated, "publish": publish_result}


@router.get("/{slug}/context")
async def get_project_context(slug: str):
    """Returns a structured context snapshot for agent initialization."""
    print(f"  [context] resolving for slug={slug}")
    try:
        project = await planner_service.get_project_by_slug(slug)
    except ValueError:
        raise HTTPException(404, "Project not found")

    project_root = Path(project["localRepoPath"]).resolve() if project.get("localRepoPath") else None
    projection = command_center_service.load_control_plane_summary(project)
    summary = projection["summary"]
    repo_health = summary.get("repoHealth") or {
        "hasLocalRepo": bool(project_root and project_root.exists()),
        "hasRailYaml": bool(project_root and (project_root / "rail.yaml").exists()),
        "hasResearchPlan": bool(project_root and (project_root / "research_plan").exists()),
    }

    context = {
        "project": {
            "name": project["name"],
            "slug": project["slug"],
            "status": project.get("status"),
            "last_hydrated": project.get("lastHydratedAt"),
            "phase": summary.get("lifecyclePhase"),
        },
        "controlPlane": {
            "phase": summary.get("lifecyclePhase"),
            "nextAction": summary.get("nextAction"),
            "currentBlocker": summary.get("currentBlocker"),
            "blockerSummary": summary.get("blockerSummary"),
            "closeoutCertificate": summary.get("closeoutCertificate"),
            "missionBrief": summary.get("missionBrief"),
            "repoHealth": repo_health,
            "snapshot": projection["snapshot"],
        },
        "ontology": {},
        "data_sources": [],
        "pipelines": [],
        "analysis_plugins": [],
    }

    # Fetch ontology info if project is hydrated
    if project.get("activeOntologyDuckdbPath") or project.get("status") == "hydrated":
        try:
            from app.services import sql_service, ontology_service, project_artifacts_service
            art = await project_artifacts_service.resolve(project.get("_id") or project.get("slug") or slug)
            print(f"  [context] resolved artifacts for {slug}: db={art.db_path}")
            sql_service.set_path(art.duckdb_path)
            classes = await ontology_service._run_with_ensure(
                slug, art.db_path, ontology_service.list_classes
            )
            context["ontology"] = {
                "classes": classes,
                "schema_ddl": sql_service.get_schema_ddl(),
            }
        except Exception as e:
            print(f"  [context] ontology load failed for {slug}: {e}")
            pass

    found_slugs = set()
    local_sources = project_root / ".ontology" / "sources" if project_root else None
    if local_sources and local_sources.exists():
        for yml in local_sources.glob("*.yaml"):
            if yml.stem in found_slugs:
                continue
            try:
                with open(yml) as f:
                    cfg = yaml.safe_load(f)
                    if cfg and "name" in cfg:
                        context["data_sources"].append({"slug": yml.stem, "name": cfg["name"]})
                        found_slugs.add(yml.stem)
            except Exception:
                pass

    for source_slug in project.get("apiConfigSlugs", []):
        if source_slug in found_slugs:
            continue
        cfg = await convex.query("configs:getApiBySlug", {"slug": source_slug})
        if cfg:
            context["data_sources"].append({"slug": cfg["slug"], "name": cfg["name"]})
            found_slugs.add(source_slug)

    found_pipeline_slugs = set()
    pipeline_slug = project.get("pipelineConfigSlug")
    local_pipelines = project_root / ".ontology" / "pipelines" if project_root else None
    if pipeline_slug and local_pipelines and local_pipelines.exists():
        for yml in local_pipelines.glob("*.yaml"):
            if yml.stem != pipeline_slug:
                continue
            try:
                with open(yml) as f:
                    cfg = yaml.safe_load(f) or {}
            except Exception:
                cfg = {}
            context["pipelines"].append({"slug": yml.stem, "name": cfg.get("name") or yml.stem})
            found_pipeline_slugs.add(yml.stem)
            break

    if pipeline_slug and pipeline_slug not in found_pipeline_slugs:
        pipeline = await convex.query("configs:getPipelineBySlug", {"slug": pipeline_slug})
        if pipeline:
            context["pipelines"].append({"slug": pipeline["slug"], "name": pipeline["name"]})

    return context


@router.get("/{slug}/command-center")
async def get_command_center(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await command_center_service.build_command_center(project)


@router.get("/{slug}/reality")
async def get_project_reality(slug: str):
    """Control-plane snapshot: drift counts, execution lane, and auditor gates."""
    project = await planner_service.get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {slug}")
    return await reconciliation_service.build_project_control_plane_status(project)


@router.post("/{slug}/command-center/reconcile")
async def reconcile_command_center_state(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await reconciliation_service.reconcile_project_reality(project)


@router.post("/{slug}/command-center/ontology-follow-ups/expand")
async def create_ontology_follow_up_task(slug: str, request: OntologyFollowUpTaskRequest):
    from app.services.question_expansion_service import (
        expansion_task_specs_for_question,
        normalize_classification,
    )

    project = await planner_service.get_project_by_slug(slug)
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)

    title = str(request.title).strip()
    classification = normalize_classification(request.classification)
    if not title:
        raise HTTPException(status_code=400, detail="Follow-up question title is required.")
    if classification not in {"requires_expansion", "blocked_by_data"}:
        raise HTTPException(status_code=400, detail="Classification must be requires_expansion or blocked_by_data.")

    specs = expansion_task_specs_for_question(title, classification)
    if not specs:
        raise HTTPException(status_code=400, detail="No expansion tasks defined for this classification.")
    spec = specs[0]

    existing = next((task for task in tasks if str(task.get("title") or "") == spec["title"]), None)
    if existing is not None:
        return {"created": False, "task": existing}

    task = await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=spec["title"],
        description=spec["description"],
        status=spec["status"],
        agent_role=spec["agent_role"],
        repo_paths=spec["repo_paths"],
        acceptance_criteria=spec["acceptance_criteria"],
        runner=spec["runner"],
    )
    await planner_service.sync_planner_files(project, board)
    return {"created": True, "task": task}


@router.get("/{slug}/skills")
async def get_project_skills(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    try:
        return command_center_service.list_project_skills(project)
    except Exception:
        projection = command_center_service.load_control_plane_summary(project)
        return {
            "skills": [],
            "summary": projection["summary"].get("skillSummary") or {
                "count": 0,
                "agentRolesWithSkillAccess": [],
            },
        }


@router.get("/{slug}/sources")
async def get_project_sources(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    try:
        return command_center_service.list_project_sources(project)
    except Exception:
        projection = command_center_service.load_control_plane_summary(project)
        return {
            "sources": [],
            "summary": projection["summary"].get("sourceSummary") or {
                "count": 0,
                "statusCounts": {},
                "freshnessCounts": {},
                "admissibilityCounts": {},
                "admissibilityHighlights": [],
                "notesPath": None,
            },
            "notes": None,
        }


@router.get("/{slug}/artifacts")
async def get_project_artifacts(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    try:
        return command_center_service.list_project_artifacts(project)
    except Exception:
        projection = command_center_service.load_control_plane_summary(project)
        return {
            "artifacts": projection["summary"].get("recentArtifacts") or [],
            "summary": {
                "count": len(projection["summary"].get("recentArtifacts") or []),
                "staleCount": int(((projection["summary"].get("integritySummary") or {}).get("staleArtifactCount")) or 0),
                "typeCounts": {},
                "promotionStateCounts": {},
                "verificationStatusCounts": {},
            },
        }


@router.get("/{slug}/integrity")
async def get_project_integrity(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    try:
        return command_center_service.list_project_integrity(project)
    except Exception:
        projection = command_center_service.load_control_plane_summary(project)
        integrity_summary = projection["summary"].get("integritySummary") or {}
        source_summary = projection["summary"].get("sourceSummary") or {}
        return {
            "indexes": {
                "assumptions": [],
                "sources": [],
                "claims": [],
                "hypotheses": [],
                "artifact_lineage": [],
                "verification_runs": [],
            },
            "summary": {
                "assumptionCount": 0,
                "sourceCount": int(source_summary.get("count") or 0),
                "claimCount": 0,
                "artifactCount": len(projection["summary"].get("recentArtifacts") or []),
                "staleArtifactCount": int(integrity_summary.get("staleArtifactCount") or 0),
                "verificationRunCount": 0,
                "sourceFreshnessCounts": integrity_summary.get("sourceFreshnessCounts") or source_summary.get("freshnessCounts") or {},
                "verificationStatusCounts": {},
                "promotionStateCounts": {},
            },
            "staleOutputs": [],
            "agentWorkflow": integrity_summary.get("agentWorkflow") or {
                "research": {"status": "ready", "requirements": []},
                "data": {"status": "ready", "requirements": []},
                "coding": {"status": "ready", "requirements": []},
                "artifact": {"status": "ready", "requirements": []},
                "health": {"status": "ready", "requirements": []},
            },
            "hypothesisRanking": integrity_summary.get("hypothesisRanking") or [],
        }


@router.get("/{slug}/integrity/assumptions")
async def get_project_integrity_assumptions(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    repo = get_integrity_repo(root)
    return {"assumptions": [item.model_dump(mode="json") for item in repo.load_assumptions()]}


@router.patch("/{slug}/integrity/assumptions/{assumption_key}")
async def patch_project_integrity_assumption(slug: str, assumption_key: str, data: IntegrityAssumptionUpdateRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_assumption_status(data.status)
    changes = {
        key: value
        for key, value in {
            "title": data.title,
            "value": data.value,
            "status": data.status,
            "notes": data.notes,
            "affected_paths": data.affectedPaths,
        }.items()
        if value is not None
    }
    try:
        updated, affected = update_assumption_and_mark_stale(root, assumption_key, changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rerun_plan = build_rerun_plan(root, assumption_key)
    return {
        "assumption": updated.model_dump(mode="json"),
        "affectedArtifacts": [item.model_dump(mode="json") for item in affected],
        "rerunPlan": rerun_plan,
    }


@router.get("/{slug}/integrity/sources")
async def get_project_integrity_sources(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return {"sources": list_source_summaries(root)}


@router.get("/{slug}/integrity/sources/{source_key}")
async def get_project_integrity_source_detail(slug: str, source_key: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    try:
        return get_source_detail(root, source_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{slug}/integrity/sources/{source_key}")
async def patch_project_integrity_source(slug: str, source_key: str, data: IntegritySourceUpdateRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_trusted_source_contract(
        impact_level=data.impactLevel,
        quality_status=data.qualityStatus,
        admissibility_status=data.admissibilityStatus,
        freshness_status=data.freshnessStatus,
        provenance=data.provenance,
    )
    changes = {
        key: value
        for key, value in {
            "title": data.title,
            "source_type": data.sourceType,
            "url_or_path": data.urlOrPath or data.url,
            "origin": data.origin or data.publisher,
            "acquired_at": data.acquiredAt or data.accessDate,
            "access_method": data.accessMethod,
            "freshness_status": data.freshnessStatus,
            "impact_level": data.impactLevel,
            "quality_status": data.qualityStatus,
            "admissibility_status": data.admissibilityStatus,
            "provenance": data.provenance,
            "quality_notes": data.qualityNotes,
            "notes": data.notes,
        }.items()
        if value is not None
    }
    try:
        updated, claims, artifacts = update_source_and_mark_stale(root, source_key, changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "source": updated.model_dump(mode="json"),
        "affectedClaims": [item.model_dump(mode="json") for item in claims],
        "affectedArtifacts": [item.model_dump(mode="json") for item in artifacts],
    }


@router.get("/{slug}/integrity/claims")
async def get_project_integrity_claims(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return {"claims": list_claim_summaries(root)}


@router.get("/{slug}/hypotheses")
async def get_project_hypotheses(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    repo = get_integrity_repo(root)
    return {"hypotheses": [item.model_dump(mode="json", by_alias=True) for item in repo.load_hypotheses()]}


@router.post("/{slug}/hypotheses")
async def upsert_project_hypothesis(slug: str, data: HypothesisUpsertRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_hypothesis_status(data.status)
    if data.score is not None and not (0 <= data.score <= 1):
        raise HTTPException(status_code=422, detail="Hypothesis score must be between 0 and 1.")
    repo = get_integrity_repo(root)
    record = repo.upsert_hypothesis(
        {
            "id": data.id,
            "statement": data.statement,
            "scope": data.scope,
            "falsifiers": data.falsifiers,
            "status": data.status,
            "score": data.score,
            "parent_id": data.parentId,
            "claim_keys": data.claimKeys,
            "task_ids": data.taskIds,
            "artifact_paths": data.artifactPaths,
            "human_notes": data.humanNotes,
        }
    )
    return record.model_dump(mode="json", by_alias=True)


@router.patch("/{slug}/hypotheses/{hypothesis_id}")
async def patch_project_hypothesis(slug: str, hypothesis_id: str, data: HypothesisPatchRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_hypothesis_status(data.status)
    if data.score is not None and not (0 <= data.score <= 1):
        raise HTTPException(status_code=422, detail="Hypothesis score must be between 0 and 1.")
    changes = {
        key: value
        for key, value in {
            "statement": data.statement,
            "scope": data.scope,
            "falsifiers": data.falsifiers,
            "status": data.status,
            "score": data.score,
            "parent_id": data.parentId,
            "claim_keys": data.claimKeys,
            "task_ids": data.taskIds,
            "artifact_paths": data.artifactPaths,
            "human_notes": data.humanNotes,
        }.items()
        if value is not None
    }
    repo = get_integrity_repo(root)
    try:
        record = repo.update_hypothesis(hypothesis_id, **changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return record.model_dump(mode="json", by_alias=True)


@router.post("/{slug}/critic/review")
async def run_project_critic_review(slug: str, data: CriticReviewRequest):
    project = await planner_service.get_project_by_slug(slug)
    try:
        result = run_critic_review(project, hypothesis_ids=data.hypothesisIds)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.post("/{slug}/research-burst")
async def run_project_research_burst(slug: str, data: ResearchBurstRequest):
    project = await planner_service.get_project_by_slug(slug)
    objective = (data.objective or "").strip()
    if not objective:
        raise HTTPException(status_code=422, detail="objective is required.")
    if data.maxParallel is not None and data.maxParallel < 1:
        raise HTTPException(status_code=422, detail="maxParallel must be >= 1.")
    try:
        result = await run_research_burst(
            project,
            objective=objective,
            max_parallel=data.maxParallel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.get("/{slug}/integrity/claims/{claim_key}")
async def get_project_integrity_claim_detail(slug: str, claim_key: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    try:
        return get_claim_detail(root, claim_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{slug}/integrity/lineage")
async def get_project_integrity_lineage(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    repo = get_integrity_repo(root)
    return {"artifactLineage": [item.model_dump(mode="json") for item in repo.load_artifact_lineage()]}


@router.get("/{slug}/integrity/artifact-lineage")
async def get_project_integrity_artifact_lineage(slug: str):
    return await get_project_integrity_lineage(slug)


@router.get("/{slug}/integrity/artifacts/{artifact_path:path}")
async def get_project_integrity_artifact_detail(slug: str, artifact_path: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    try:
        return get_artifact_detail(root, artifact_path, manifest=load_manifest(root))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{slug}/integrity/graph")
async def get_project_integrity_dependency_graph(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return get_integrity_dependency_graph(root)


@router.get("/{slug}/integrity/stale-graph")
async def get_project_integrity_stale_graph(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return get_stale_dependency_graph(root)


@router.get("/{slug}/integrity/verification-runs")
async def get_project_integrity_verification_runs(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    repo = get_integrity_repo(root)
    runs = [item.model_dump(mode="json") for item in repo.load_verification_runs()]
    status_counts: dict[str, int] = {}
    loop_type_counts: dict[str, int] = {}
    for row in runs:
        status = str(row.get("status") or "pending")
        status_counts[status] = status_counts.get(status, 0) + 1
        loop_type = str(row.get("loop_type") or "analysis_reproducibility")
        loop_type_counts[loop_type] = loop_type_counts.get(loop_type, 0) + 1
    return {
        "verificationRuns": runs,
        "summary": {
            "count": len(runs),
            "statusCounts": status_counts,
            "loopTypeCounts": loop_type_counts,
        },
    }


@router.get("/{slug}/integrity/benchmark")
async def get_project_integrity_benchmark(slug: str, retrieval_limit: int = Query(10, ge=1, le=100, alias="retrievalLimit")):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return evaluate_default_integrity_benchmark_corpus(root, retrieval_limit=retrieval_limit)


@router.get("/{slug}/integrity/retrieve")
async def get_project_integrity_retrieval(
    slug: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
    artifact_types: str | None = Query(None, alias="artifactTypes"),
    claim_statuses: str | None = Query(None, alias="claimStatuses"),
    source_freshness: str | None = Query(None, alias="sourceFreshness"),
    date_from: str | None = Query(None, alias="dateFrom"),
    date_to: str | None = Query(None, alias="dateTo"),
    include_stale: bool = Query(False, alias="includeStale"),
    include_blocked: bool = Query(False, alias="includeBlocked"),
):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return hybrid_retrieve(
        root,
        q,
        limit=limit,
        artifact_types=_csv_query_param(artifact_types),
        claim_statuses=_csv_query_param(claim_statuses),
        source_freshness=_csv_query_param(source_freshness),
        date_from=date_from,
        date_to=date_to,
        include_stale=include_stale,
        include_blocked=include_blocked,
    )


@router.post("/{slug}/integrity/rerun-plan")
async def preview_project_integrity_rerun_plan(slug: str, data: IntegrityRerunPlanRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    try:
        plan = build_rerun_plan(root, data.assumptionKey)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return plan


@router.post("/{slug}/integrity/rerun-plan/apply")
async def apply_project_integrity_rerun_plan(slug: str, data: IntegrityRerunPlanRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    try:
        plan = build_rerun_plan(root, data.assumptionKey)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _apply_integrity_plan(project, root, plan)


@router.post("/{slug}/integrity/batch-rerun-plan/apply")
async def apply_project_integrity_batch_rerun_plan(slug: str, data: IntegrityBatchRerunPlanRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    plan = build_batch_rerun_plan(root, data.assumptionKeys)
    return await _apply_integrity_plan(project, root, plan)


@router.post("/{slug}/integrity/reproducibility-rerun")
async def apply_project_integrity_reproducibility_rerun(slug: str, data: IntegrityReproducibilityRerunRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return apply_reproducibility_rerun(
        root,
        data.outputs,
        run_id=data.runId,
        scope=data.scope,
    )


@router.post("/{slug}/integrity/freshness-evaluate")
async def apply_project_integrity_freshness_evaluation(slug: str, data: IntegrityFreshnessEvaluationRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    return apply_source_freshness_policy(root, as_of=data.asOf)


@router.post("/{slug}/integrity/artifacts/promote")
async def apply_project_integrity_artifact_promotion(slug: str, data: IntegrityArtifactPromotionRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    if data.targetState not in ALLOWED_PROMOTION_STATES:
        raise HTTPException(
            status_code=422,
            detail="Artifact promotion target state must be one of: exploratory, draft, needs_evidence, partially_verified, verified, stale, blocked.",
        )
    # Check artifact existence and transition validity BEFORE auditor state.
    # If the operator asked to promote something that doesn't exist or
    # requested an invalid transition, surfacing the auditor's blocker
    # first is misleading — the real fix is the input, not the auditor.
    from rail.integrity import ResearchIntegrityRepo

    repo = ResearchIntegrityRepo(root)
    artifact = next(
        (item for item in repo.load_artifact_lineage() if item.artifact_path == data.artifactPath),
        None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact_path: {data.artifactPath}")
    allowed_targets = ALLOWED_PROMOTION_TRANSITIONS.get(artifact.promotion_state, set())
    if data.targetState != artifact.promotion_state and data.targetState not in allowed_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid promotion transition: {artifact.promotion_state} -> {data.targetState}",
        )
    if data.targetState in {"partially_verified", "verified"}:
        ontology_status = await _ontology_auditor_status(project)
        # Only treat ontology-auditor blocks as a hard 409 here. Integrity
        # auditor blocks (claims needing evidence, stale sources, etc.) are
        # handled inside promote_artifact, which returns a structured
        # `{status: blocked, gate: {...}}` 200 payload that the operator UI
        # already knows how to render. Pre-empting that with a 409 would
        # discard the structured remediation details the gate produces.
        if str(ontology_status.get("status") or "") == "blocked":
            blocker = next(
                (str(item) for item in (ontology_status.get("blockers") or []) if str(item).strip()),
                "blocked",
            )
            raise HTTPException(
                status_code=409,
                detail=f"Artifact promotion blocked by auditor state: ontology: {blocker}",
            )
    manifest = load_manifest(root)
    try:
        return promote_artifact(root, manifest, data.artifactPath, target_state=data.targetState)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _apply_integrity_plan(project: dict, root: Path, plan: dict):
    board = await planner_service.ensure_main_board(project)
    created_tasks = []
    for spec in plan["proposedTasks"]:
        role_config = load_role_runtime_config(project, spec["agentRole"])
        decision = evaluate_autonomy_policy(
            role_config.manifest,
            action=activity_key_for_role(role_config.role),
            write_capable=is_write_capable(role_policy=role_config.policy, allowed_paths=spec["repoPaths"]),
        )
        task = await planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title=spec["title"],
            description=spec["description"],
            status="ready",
            agent_role=spec["agentRole"],
            repo_paths=spec["repoPaths"],
            acceptance_criteria=spec["acceptanceCriteria"],
            approval_state="granted" if not decision.requires_human_approval else "pending",
        )
        created_tasks.append(task)
    return {"tasks": created_tasks}


@router.post("/{slug}/integrity/assumptions")
async def record_project_integrity_assumption(slug: str, data: IntegrityRecordAssumptionRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_assumption_status(data.status)
    repo = get_integrity_repo(root)
    record = repo.upsert_assumption(
        {
            "assumption_key": data.assumptionKey,
            "title": data.title,
            "value": data.value,
            "status": data.status,
            "notes": data.notes,
            "affected_paths": data.affectedPaths,
        }
    )
    return record.model_dump(mode="json")


@router.post("/{slug}/integrity/sources")
async def record_project_integrity_source(slug: str, data: IntegrityRecordSourceRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    _validate_trusted_source_contract(
        impact_level=data.impactLevel,
        quality_status=data.qualityStatus,
        admissibility_status=data.admissibilityStatus,
        freshness_status=data.freshnessStatus,
        provenance=data.provenance,
    )
    repo = get_integrity_repo(root)
    record = repo.upsert_source(
        {
            "source_key": data.sourceKey,
            "source_type": data.sourceType,
            "title": data.title,
            "url_or_path": data.urlOrPath or data.url or "",
            "origin": data.origin or data.publisher,
            "acquired_at": data.acquiredAt or data.accessDate,
            "access_method": data.accessMethod,
            "freshness_status": data.freshnessStatus,
            "admissibility_status": data.admissibilityStatus,
            "impact_level": data.impactLevel,
            "provenance": data.provenance,
            "quality_notes": data.qualityNotes,
            "quality_status": data.qualityStatus,
            "notes": data.notes,
        }
    )
    return next(item for item in list_source_summaries(root) if item["source_key"] == record.source_key)


@router.post("/{slug}/integrity/claims")
async def record_project_integrity_claim(slug: str, data: IntegrityRecordClaimRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    has_explicit_evidence = bool(data.evidencePaths or data.evidenceChunkKeys or data.sourceKeys)
    if data.status == "supported" and (
        not has_explicit_evidence or data.evidenceKind == "semantic_suggestion"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Supported claims require explicit recorded evidence. "
                "Attach evidence paths, source keys, or evidence chunk keys and avoid "
                "`semantic_suggestion` when writing trusted claims."
            ),
        )
    repo = get_integrity_repo(root)
    _validate_claim_reference_integrity(
        repo,
        project_root=root,
        status=data.status,
        evidence_kind=data.evidenceKind,
        evidence_paths=data.evidencePaths,
        source_keys=data.sourceKeys,
        evidence_chunk_keys=data.evidenceChunkKeys,
    )
    record = repo.upsert_claim(
        {
            "claim_key": data.claimKey,
            "claim_text": data.statement,
            "artifact_path": data.artifactPath,
            "status": data.status,
            "evidence_paths": data.evidencePaths,
            "evidence_chunk_keys": data.evidenceChunkKeys,
            "source_keys": data.sourceKeys,
            "contradicts_claim_keys": data.contradictsClaimKeys,
            "evidence_kind": data.evidenceKind,
            "caveats": data.caveats,
            "open_questions": data.openQuestions,
            "confidence": data.confidence,
        }
    )
    return next(item for item in list_claim_summaries(root) if item["claim_key"] == record.claim_key)


@router.post("/{slug}/integrity/artifacts")
async def record_project_integrity_lineage(slug: str, data: IntegrityRecordLineageRequest):
    project = await planner_service.get_project_by_slug(slug)
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise HTTPException(status_code=404, detail="Project repo not found")
    # Ontology auditor blocks (e.g. ontology not hydrated) supersede the
    # workflow-contract check — the operator needs to fix ontology hydration
    # before any trusted lineage write makes sense, regardless of whether the
    # request happens to also be missing verification runs. Integrity auditor
    # blocks fall through and get caught by the workflow-contract +
    # reference-validation layers below, which return more actionable detail.
    if data.promotionState in {"partially_verified", "verified"}:
        ontology_status = await _ontology_auditor_status(project)
        if str(ontology_status.get("status") or "") == "blocked":
            blocker = next(
                (str(item) for item in (ontology_status.get("blockers") or []) if str(item).strip()),
                "blocked",
            )
            raise HTTPException(
                status_code=409,
                detail=f"Artifact lineage write blocked by auditor state: ontology: {blocker}",
            )
    _validate_trusted_artifact_lineage_contract(
        promotion_state=data.promotionState,
        inputs=data.inputs,
        scripts=data.scripts,
        verification_runs=data.verificationRuns,
    )
    repo = get_integrity_repo(root)
    _validate_artifact_lineage_references(
        repo,
        project_root=root,
        promotion_state=data.promotionState,
        reproducibility_mode=data.reproducibilityMode,
        inputs=data.inputs,
        scripts=data.scripts,
        sources=data.sources,
        assumptions=data.assumptions,
        claims=data.claims,
        verification_runs=data.verificationRuns,
    )
    record = repo.upsert_artifact_lineage(
        {
            "artifact_path": data.artifactPath,
            "artifact_type": data.artifactType,
            "title": data.title,
            "promotion_state": data.promotionState,
            "reproducibility_mode": data.reproducibilityMode,
            "inputs": data.inputs,
            "scripts": data.scripts,
            "verification_commands": data.verificationCommands,
            "sources": data.sources,
            "assumptions": data.assumptions,
            "claims": data.claims,
            "verification_runs": data.verificationRuns,
        }
    )
    return record.model_dump(mode="json")


@router.post("/{slug}/research-launch/preview")
async def preview_research_launch(slug: str, data: ResearchLaunchRequest):
    project = await planner_service.get_project_by_slug(slug)
    return command_center_service.build_launch_preview(project, data.model_dump())


@router.post("/{slug}/research-launch/approve")
async def approve_research_launch(slug: str, data: ResearchLaunchRequest):
    project = await planner_service.get_project_by_slug(slug)
    return await command_center_service.approve_launch_preview(project, data.model_dump())


@router.get("/{slug}/planner/thread")
async def get_planner_thread(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    messages = await planner_service.list_planner_messages(project, thread_id=thread_id)
    return {
        "threadId": thread_id,
        "messages": messages,
    }


async def _build_planner_home_payload(project: dict[str, Any], slug: str) -> dict[str, Any]:
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    messages = await planner_service.list_planner_messages(project, thread_id=thread_id, limit=50)
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    approvals = await planner_service.list_approvals(project)
    autopilot_snapshot = await get_autopilot_status(slug)
    sessions = await running_agent_service.list_project_running_agents(project["_id"], active_only=False, limit=20)
    project_root = planner_service.project_root_from_record(project)
    research_plan_root = project_root / "research_plan" if project_root else None
    blockers_path = research_plan_root / "blockers.md" if research_plan_root else None
    sessions_root = research_plan_root / "sessions" if research_plan_root else None
    projection = command_center_service.load_control_plane_summary(project)
    summary = projection["summary"]
    repo_health = summary.get("repoHealth") or {
        "hasLocalRepo": bool(project_root and project_root.exists()),
        "hasRailYaml": bool(project_root and (project_root / "rail.yaml").exists()),
        "hasResearchPlan": bool(research_plan_root and research_plan_root.exists()),
    }

    return {
        "project": {
            "id": project["_id"],
            "name": project.get("name") or project.get("slug") or "Project",
            "slug": project.get("slug") or "",
            "status": project.get("status"),
            "description": project.get("description"),
            "gitRepoUrl": project.get("gitRepoUrl"),
            "defaultBranch": project.get("defaultBranch"),
            "agentModel": project.get("agentModel"),
            "githubSyncMode": project.get("githubSyncMode"),
            "localRepoPath": project.get("localRepoPath"),
            "manifestPath": project.get("manifestPath") or "rail.yaml",
        },
        "repoHealth": repo_health,
        "autopilot": autopilot_snapshot,
        "pendingDispatches": _load_pending_dispatches(project),
        "pendingQuestions": _load_pending_qa(project),
        "decisions": _load_planner_decisions(project),
        "refreshedAt": int(time.time() * 1000),
        "planner": {
            "threadId": thread_id,
            "messages": list(reversed(messages)),
            "board": board,
            "tasks": tasks,
            "approvals": approvals,
            "files": {
                "currentPlan": str((research_plan_root / "current_plan.md").relative_to(project_root)) if research_plan_root and (research_plan_root / "current_plan.md").exists() else None,
                "taskBoard": str((research_plan_root / "task_board.md").relative_to(project_root)) if research_plan_root and (research_plan_root / "task_board.md").exists() else None,
                "approvals": str((research_plan_root / "approvals.md").relative_to(project_root)) if research_plan_root and (research_plan_root / "approvals.md").exists() else None,
                "blockers": str(blockers_path.relative_to(project_root)) if blockers_path and blockers_path.exists() else None,
            },
            "workspaceReview": {
                "sessionsRoot": str(sessions_root.relative_to(project_root)) if sessions_root and sessions_root.exists() else None,
            },
            "sessions": [_session_review_model(project, session) | {"id": session.get("_id"), "status": session.get("status"), "role": session.get("role")} for session in sessions],
        },
        "controlPlane": {
            "phase": summary.get("lifecyclePhase"),
            "nextAction": summary.get("nextAction"),
            "currentBlocker": summary.get("currentBlocker"),
            "goal": summary.get("goal"),
            "taskCounts": summary.get("taskCounts"),
            "recentArtifacts": summary.get("recentArtifacts"),
            "sourceSummary": summary.get("sourceSummary"),
            "skillSummary": summary.get("skillSummary"),
            "integritySummary": summary.get("integritySummary"),
            "projectReality": summary.get("projectReality"),
            "auditors": summary.get("auditors"),
            "blockerSummary": summary.get("blockerSummary"),
            "repairQueue": summary.get("repairQueue"),
            "recommendedRepairTask": summary.get("recommendedRepairTask"),
            "closeoutCertificate": summary.get("closeoutCertificate"),
            "missionBrief": summary.get("missionBrief"),
            "ontologyFollowUps": summary.get("ontologyFollowUps"),
            "snapshot": projection["snapshot"],
        },
    }


@router.get("/{slug}/planner/home")
async def get_planner_home(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await _build_planner_home_payload(project, slug)


@router.post("/{slug}/planner/messages")
async def append_planner_message(slug: str, data: PlannerMessageRequest):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    role = _normalize_planner_message_role(data.role, field_name="Planner message role")
    await planner_service.append_planner_message(
        project=project,
        role=role,
        content=data.content,
        message_type=data.messageType,
        session_id=data.sessionId,
        thread_id=thread_id,
    )
    messages = await planner_service.list_planner_messages(project, thread_id=thread_id)
    return {"threadId": thread_id, "messages": list(reversed(messages))}


@router.post("/{slug}/planner/chat")
async def planner_chat(slug: str, data: PlannerChatRequest):
    project = await planner_service.get_project_by_slug(slug)
    return await planner_runtime.run_planner_turn(
        project=project,
        user_message=data.message,
        history=data.history,
        model=data.model,
        persist=True,
    )


@router.post("/{slug}/planner/worker-update")
async def worker_update_planner(slug: str, data: WorkerUpdateRequest):
    project = await planner_service.get_project_by_slug(slug)
    role = _normalize_planner_message_role(data.role, field_name="Worker update role")
    # Append to planner history as a system/agent message
    await planner_service.append_planner_message(
        project=project,
        role=role,
        content=data.message,
        message_type="worker_update"
    )
    # Trigger Autopilot wake-up so the planner can react
    from app.services.autopilot_service import trigger_wake
    trigger_wake(slug)
    return {"status": "message_sent"}


@router.get("/{slug}/planner/board")
async def get_planner_board(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    home = await _build_planner_home_payload(project, slug)
    return {
        "board": home["planner"]["board"],
        "tasks": home["planner"]["tasks"],
        "approvals": home["planner"]["approvals"],
        "blockersPath": home["planner"]["files"]["blockers"] or "research_plan/blockers.md",
        "sessions": home["planner"]["sessions"],
    }


@router.post("/{slug}/planner/tasks")
async def create_planner_task(slug: str, data: PlannerTaskRequest):
    project = await planner_service.get_project_by_slug(slug)
    _validate_planner_task_status(data.status)
    _validate_planner_task_approval_state(data.approvalState)
    _validate_planner_task_runner(data.runner)
    _validate_planner_task_priority(data.priority)
    agent_role = _normalize_agent_role(data.agentRole, field_name="Planner task agent role")
    board = await planner_service.ensure_main_board(project, session_id=data.sessionId)
    task = await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=data.title,
        description=data.description,
        status=data.status,
        agent_role=agent_role,
        repo_paths=data.repoPaths,
        acceptance_criteria=data.acceptanceCriteria,
        depends_on_task_ids=data.dependsOnTaskIds,
        session_id=data.sessionId,
        priority=data.priority,
        runner=data.runner,
        approval_state=data.approvalState,
    )
    await planner_service.sync_planner_files(project, board)
    return task


@router.patch("/{slug}/planner/tasks/{task_id}")
async def update_planner_task(slug: str, task_id: str, data: PlannerTaskUpdateRequest):
    project = await planner_service.get_project_by_slug(slug)
    _validate_planner_task_status(data.status)
    _validate_planner_task_approval_state(data.approvalState)
    _validate_planner_task_runner(data.runner)
    _validate_planner_task_priority(data.priority)
    board = await planner_service.ensure_main_board(project)
    try:
        await planner_service.update_task(task_id, project=project, **data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await planner_service.sync_planner_files(project, board)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    for task in tasks:
        if str(task["_id"]) == task_id:
            return task
    return {"ok": True}


@router.post("/{slug}/devices/heartbeat")
async def heartbeat_project_device(slug: str, data: DeviceHeartbeatRequest):
    project = await planner_service.get_project_by_slug(slug)
    metadata = get_device_metadata()
    payload = {
        "deviceId": metadata["deviceId"],
        "label": data.label or metadata["label"],
        "hostname": data.hostname or metadata["hostname"],
        "platform": data.platform or metadata["platform"],
    }
    device_row_id = await convex.mutation("devices:heartbeat", payload)
    return {"projectId": project["_id"], "device": {**payload, "rowId": device_row_id}}


@router.get("/{slug}/hydration/status")
async def get_hydration_status(slug: str, pipelineSlug: str | None = Query(None), hydrationMode: str = Query("full")):
    project = await planner_service.get_project_by_slug(slug)
    if not project.get("localRepoPath"):
        raise HTTPException(400, "Project does not have a localRepoPath configured")
    return await get_project_hydration_status(
        project=project,
        pipeline_slug=pipelineSlug,
        hydration_mode=hydrationMode,
    )


@router.post("/{slug}/hydration/artifacts/register")
async def register_project_hydration_artifact(slug: str, data: RegisterHydrationArtifactRequest):
    project = await planner_service.get_project_by_slug(slug)
    if not project.get("localRepoPath"):
        raise HTTPException(400, "Project does not have a localRepoPath configured")
    artifact_id = await register_hydration_artifact(
        project=project,
        pipeline_slug=data.pipelineSlug or "default",
        hydration_mode=data.hydrationMode,
        ontology_artifact_path=data.ontologyArtifactPath,
        duckdb_artifact_path=data.duckdbArtifactPath,
        status=data.status,
    )
    return {"artifactId": artifact_id}


@router.post("/{slug}/hydration/rerun")
async def rerun_project_hydration(
    slug: str,
    data: HydrationRerunRequest,
    background_tasks: BackgroundTasks,
):
    project = await planner_service.get_project_by_slug(slug)
    project_root = Path(project["localRepoPath"]).resolve() if project.get("localRepoPath") else None
    
    if project_root is None:
        raise HTTPException(400, "Project does not have a localRepoPath configured")
    if not project_root.exists():
        raise HTTPException(404, f"Project root directory not found: {project_root}")

    pipeline_slug = _configured_pipeline_slug(project, project_root, data.pipelineSlug)
    
    # Try to find a registered pipeline in Convex first to get a valid ID
    pipeline_record = await convex.query("configs:getPipeline", {"slug": pipeline_slug})
    pipeline_id = pipeline_record["_id"] if pipeline_record else None

    local_configs = _local_hydration_configs(project_root, pipeline_slug)

    if local_configs:
        pipeline_content, api_configs, onto_configs = local_configs
        if not pipeline_id:
            engine = LocalEngine(project_path=str(project_root))
            local_result = await asyncio.to_thread(engine.hydrate, pipeline_slug)
            artifact_db_path = str(local_result.get("artifact_db_path") or "")
            artifact_duckdb_path = str(local_result.get("artifact_duckdb_path") or "")
            hydration_mode = engine.manifest.hydration.hydration_mode or "full"
            artifact_id = await register_hydration_artifact(
                project=project,
                pipeline_slug=pipeline_slug,
                hydration_mode=hydration_mode,
                ontology_artifact_path=artifact_db_path,
                duckdb_artifact_path=artifact_duckdb_path,
                status="valid",
            )
            await promote_project_hydration_artifact(
                project=project,
                ontology_artifact_path=artifact_db_path,
                duckdb_artifact_path=artifact_duckdb_path,
            )
            result = {
                "jobId": None,
                "status": local_result.get("status") or "hydrated",
                "source": "project_repo_local",
                "artifactId": artifact_id,
                "artifactDbPath": artifact_db_path,
                "artifactDuckdbPath": artifact_duckdb_path,
            }
        else:
            mutation_result = await convex.mutation(
                "jobs:create",
                {
                    "pipelineConfigId": pipeline_id,
                    "pipelineSlug": pipeline_slug,
                    "projectSlug": slug,
                    "status": "queued",
                    "triggeredBy": "api",
                    "createdAt": int(time.time() * 1000),
                    "stepResults": [],
                    "machine": platform.node(),
                },
            )
            job_id = mutation_result.get("jobId") if isinstance(mutation_result, dict) else None
            if not job_id:
                raise HTTPException(500, f"Convex jobs:create did not return a jobId (got {mutation_result!r})")
            background_tasks.add_task(hydration_worker.run, job_id, pipeline_content, api_configs, onto_configs)
            result = {"jobId": job_id, "status": "queued", "source": "project_repo"}
    else:
        from app.routers.jobs import TriggerJobRequest, trigger_job

        try:
            result = await trigger_job(
                TriggerJobRequest(pipeline_slug=pipeline_slug, project_id=slug),
                background_tasks,
            )
        except ValueError as exc:
            raise HTTPException(404, f"Pipeline '{pipeline_slug}' not found locally or in registry: {exc}") from exc

    return {
        **result,
        "pipelineSlug": pipeline_slug,
        "projectSlug": slug,
        "device": get_device_metadata(),
    }


@router.post("/{slug}/pipeline/run")
async def run_project_data_pipeline(
    slug: str,
    data: HydrationRerunRequest,
    background_tasks: BackgroundTasks,
    reconcile: bool = True,
):
    """One-shot: reconcile control-plane drift, then queue fetch + hydrate for the project."""
    project = await planner_service.get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {slug}")

    reconcile_result = None
    if reconcile:
        reconcile_result = await reconciliation_service.reconcile_project_reality(project)

    hydration_result = await rerun_project_hydration(slug, data, background_tasks)

    return {
        "reconciled": reconcile,
        "reconcile": reconcile_result,
        "hydration": hydration_result,
        "message": (
            f"Queued pipeline {hydration_result.get('pipelineSlug', 'default')}. "
            "External APIs will run, transforms execute, and the ontology DuckDB will refresh."
        ),
    }


@router.get("/{slug}/settings/secrets")
async def list_project_secrets(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    secrets = await convex.query("projectSecrets:listByProject", {"projectId": project["_id"]}) or []
    policies = await convex.query("agentSecretPolicies:listByProject", {"projectId": project["_id"]}) or []
    normalized_policies = [
        dict(policy)
        | {
            "agentRole": ROLE_ALIASES.get(
                str(policy.get("agentRole") or "").strip().lower(),
                str(policy.get("agentRole") or ""),
            )
        }
        for policy in policies
    ]

    masked = []
    for item in secrets:
        try:
            decrypted = decrypt_secret_value(item["encryptedValue"])
            masked_value = mask_secret_value(decrypted)
        except Exception:
            masked_value = "***"
        masked.append(
            {
                "id": item["_id"],
                "keyName": item["keyName"],
                "maskedValue": masked_value,
                "updatedAt": item.get("updatedAt"),
            }
        )

    return {"secrets": masked, "policies": normalized_policies}


@router.post("/{slug}/settings/secrets")
async def upsert_project_secret(slug: str, data: ProjectSecretUpsertRequest):
    project = await planner_service.get_project_by_slug(slug)
    encrypted = encrypt_secret_value(data.plaintextValue)
    secret_id = await convex.mutation(
        "projectSecrets:upsert",
        {
            "projectId": project["_id"],
            "keyName": data.keyName,
            "encryptedValue": encrypted,
        },
    )
    return {"secretId": secret_id, "keyName": data.keyName}


@router.get("/{slug}/settings/agent-secret-policies")
async def list_agent_secret_policies(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    policies = await convex.query("agentSecretPolicies:listByProject", {"projectId": project["_id"]}) or []
    normalized_policies = [
        dict(policy)
        | {
            "agentRole": ROLE_ALIASES.get(
                str(policy.get("agentRole") or "").strip().lower(),
                str(policy.get("agentRole") or ""),
            )
        }
        for policy in policies
    ]
    return {"policies": normalized_policies}


@router.post("/{slug}/settings/agent-secret-policies")
async def upsert_agent_secret_policy(slug: str, data: AgentSecretPolicyUpsertRequest):
    project = await planner_service.get_project_by_slug(slug)
    agent_role = _normalize_agent_role(data.agentRole, field_name="Agent secret policy role")
    policy_id = await convex.mutation(
        "agentSecretPolicies:upsert",
        {
            "projectId": project["_id"],
            "agentRole": agent_role,
            "allowedSecretNames": data.allowedSecretNames,
        },
    )
    return {"policyId": policy_id, "agentRole": agent_role}


@router.delete("/{slug}/settings/secrets/{key_name}")
async def delete_project_secret(slug: str, key_name: str):
    project = await planner_service.get_project_by_slug(slug)
    await convex.mutation(
        "projectSecrets:deleteByKey",
        {"projectId": project["_id"], "keyName": key_name},
    )
    return {"deleted": True, "keyName": key_name}


@router.delete("/{slug}/settings/agent-secret-policies/{agent_role}")
async def delete_agent_secret_policy(slug: str, agent_role: str):
    project = await planner_service.get_project_by_slug(slug)
    normalized_role = _normalize_agent_role(agent_role, field_name="Agent secret policy role")
    await convex.mutation(
        "agentSecretPolicies:deleteByRole",
        {"projectId": project["_id"], "agentRole": normalized_role},
    )
    return {"deleted": True, "agentRole": normalized_role}


@router.get("/{slug}/secrets/resolve")
async def resolve_secrets_for_agent(slug: str, agentRole: str = Query(...)):
    """Return decrypted secrets the given agent role is allowed to access.

    This endpoint is intended for runner/orchestrator use at task start time.
    It enforces the agent secret policy — only secrets in the role's allowlist
    are returned, and only if they exist in the project's secret store.
    """
    project = await planner_service.get_project_by_slug(slug)
    from app.services.secret_service import resolve_secrets_for_role
    normalized_role = _normalize_agent_role(agentRole, field_name="Secrets resolve agentRole")
    secrets = await resolve_secrets_for_role(project["_id"], normalized_role)
    return {"agentRole": normalized_role, "secrets": secrets}


@router.get("/{slug}/approvals")
async def list_project_approvals(slug: str, limit: int = Query(100)):
    project = await planner_service.get_project_by_slug(slug)
    approvals = await planner_service.list_approvals(project)
    return {"approvals": approvals[:limit]}


@router.post("/{slug}/approvals")
async def create_project_approval(slug: str, data: ApprovalCreateRequest):
    project = await planner_service.get_project_by_slug(slug)
    _validate_approval_status(data.status)
    _validate_approval_type(data.approvalType)
    requested_by_role = _normalize_agent_role(data.requestedByRole, field_name="Approval requestedByRole")
    approval_id = await planner_service.create_approval(
        project=project,
        task_id=data.taskId,
        agent_session_id=data.agentSessionId,
        approval_type=data.approvalType,
        status=data.status,
        requested_by_role=requested_by_role,
        granted_by_user_id=data.grantedByUserId,
    )
    from app.services.autopilot_service import trigger_wake
    trigger_wake(slug)
    return {"approvalId": approval_id}


@router.post("/{slug}/approvals/{approval_id}/resolve")
async def resolve_project_approval(slug: str, approval_id: str, data: ApprovalResolveRequest):
    project = await planner_service.get_project_by_slug(slug)
    _validate_approval_status(data.status)
    approval = await planner_service.resolve_approval(
        project=project,
        approval_id=approval_id,
        status=data.status,
        granted_by_user_id=data.grantedByUserId,
        resolution_note=data.resolutionNote,
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    # Sync task approval_state so planner and runner pick up the change
    task_id = approval.get("taskId")
    if task_id and data.status == "granted":
        await planner_service.update_task(
            task_id,
            project=project,
            status="ready",
            approvalState="granted",
        )
    
    from app.services.autopilot_service import trigger_wake
    trigger_wake(slug)
    
    return approval


# --- Project-Scoped Runner Sessions ---

@router.post("/{slug}/runner/sessions")
async def create_project_runner_session(
    slug: str,
    data: ProjectRunnerSessionCreateRequest,
    background_tasks: BackgroundTasks,
):
    project = await planner_service.get_project_by_slug(slug)
    from app.runners import session_lifecycle
    role = _normalize_agent_role(data.role, field_name="Runner session role")
    runner_name = _normalize_runner_name(data.runnerName)
    agent_role_for_secrets = None
    if data.agentRoleForSecrets not in {None, ""}:
        agent_role_for_secrets = _normalize_agent_role(
            data.agentRoleForSecrets,
            field_name="Runner agentRoleForSecrets",
        )

    repo_url = data.repoUrl or project.get("gitRepoUrl") or ""
    branch = data.branch or project.get("defaultBranch") or "main"

    policy_approval_granted = False
    if data.taskId:
        # Check for existing granted approval
        approvals = await planner_service.list_approvals(project)
        policy_approval_granted = any(
            item.get("taskId") == data.taskId and item.get("status") == "granted"
            for item in approvals
        )
        
        # If not already granted, we auto-grant it here because the user
        # explicitly clicked "Run Task" in the UI.
        if not policy_approval_granted:
            try:
                # 1. Create a requested approval record if one doesn't exist
                # Note: create_approval returns the ID string
                approval_id = await planner_service.create_approval(
                    project=project,
                    task_id=data.taskId,
                    agent_session_id=None,
                    approval_type="run_task",
                    requested_by_role="planner", # Default for task runs
                )
                
                # 2. Immediately resolve it as granted
                await planner_service.resolve_approval(
                    project=project,
                    approval_id=approval_id,
                    status="granted",
                    granted_by_user_id="user",
                    resolution_note="Auto-granted by UI Run Task action."
                )
                
                # 3. Mark task as ready/granted
                await planner_service.update_task(
                    data.taskId,
                    project=project,
                    status="ready",
                    approvalState="granted",
                )
                
                policy_approval_granted = True
                print(f"  [runner] auto-granted approval for task={data.taskId}")
            except Exception as e:
                print(f"  [runner] failed to auto-grant approval for task={data.taskId}: {e}")
                # Fall through to the PermissionError check below

    try:
        result = await session_lifecycle.create_runner_session(
            project_id=project["_id"],
            project_slug=project["slug"],
            task_id=data.taskId,
            runner_name=runner_name,
            role=role,
            task_description=data.taskDescription,
            repo_url=repo_url,
            branch=branch,
            local_repo_path=project.get("localRepoPath"),
            allowed_paths=data.allowedPaths,
            acceptance_criteria=data.acceptanceCriteria,
            agent_role_for_secrets=agent_role_for_secrets,
            policy_approval_granted=policy_approval_granted,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Start polling in background
    background_tasks.add_task(
        session_lifecycle.poll_session_until_done,
        result["convex_session_id"],
        project_id=project["_id"],
    )

    return result


@router.get("/{slug}/runner/sessions")
async def list_project_runner_sessions(slug: str, limit: int = Query(20)):
    project = await planner_service.get_project_by_slug(slug)
    sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=False,
        limit=limit,
    )
    return {
        "sessions": [
            dict(session) | {"review": _session_review_model(project, session)}
            for session in sessions
        ]
    }


@router.get("/{slug}/runner/sessions/{session_id}")
async def get_project_runner_session(slug: str, session_id: str, sync: bool = Query(True)):
    project = await planner_service.get_project_by_slug(slug)
    from app.runners import session_lifecycle
    result = await session_lifecycle.get_runner_session(
        session_id,
        sync_from_runner=sync,
        project_id=project["_id"],
    )
    return dict(result) | {"review": _session_review_model(project, result)}


@router.get("/{slug}/runner/sessions/{session_id}/files")
async def get_project_runner_session_files(slug: str, session_id: str):
    project = await planner_service.get_project_by_slug(slug)
    session = await running_agent_service.get_running_agent(session_id)
    if not session or session.get("projectId") != project["_id"]:
        raise HTTPException(status_code=404, detail="Runner session not found")
    session_path = _resolve_session_path(project, session)
    if not session_path:
        raise HTTPException(status_code=404, detail="Session files not found")
    root = Path(session_path)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Session file directory does not exist")

    return {
        "sessionId": session_id,
        "sessionPath": session_path,
        "state": session_files.read_state(root),
        "events": session_files.list_events(root),
        "commands": session_files.list_commands(root),
        "summary": (root / "summary.md").read_text(encoding="utf-8") if (root / "summary.md").exists() else "",
        "reviewFiles": {
            "diff": str((root / "diff.md").relative_to(Path(project.get("localRepoPath")))) if (root / "diff.md").exists() and project.get("localRepoPath") else None,
            "todos": str((root / "todos.md").relative_to(Path(project.get("localRepoPath")))) if (root / "todos.md").exists() and project.get("localRepoPath") else None,
            "verification": str((root / "verification.md").relative_to(Path(project.get("localRepoPath")))) if (root / "verification.md").exists() and project.get("localRepoPath") else None,
        },
    }


@router.get("/{slug}/runner/sessions/{session_id}/detail")
async def get_project_runner_session_detail(slug: str, session_id: str):
    """
    Rich, frontend-ready session detail object.

    Returns all four agent-observability layers from the command-center spec:
      Layer 1 – executive summary (currentFocus, status, workspaceBranch, ...)
      Layer 2 – activity timeline (normalized event rows)
      Layer 3 – workspace/file activity (changedFiles, changedFileCount, ...)
      Layer 4 – commands and messages (recentCommands, recentMessages, ...)

    Also includes inline review-file content (summary, diff, todos,
    verification) so the frontend does not need a separate file-read call for
    the most common detail views.
    """
    from app.services.session_detail_service import build_session_detail

    project = await planner_service.get_project_by_slug(slug)
    session = await running_agent_service.get_running_agent(session_id)
    if not session or session.get("projectId") != project["_id"]:
        raise HTTPException(status_code=404, detail="Runner session not found")
    session_path = _resolve_session_path(project, session)
    if not session_path or not Path(session_path).exists():
        raise HTTPException(status_code=404, detail="Session files not found")

    project_root = Path(project["localRepoPath"]) if project.get("localRepoPath") else None
    detail = build_session_detail(session_path, project_root)
    decisions = command_center_service.extract_decisions_from_session_detail(detail)

    return {
        "sessionId": session_id,
        "projectSlug": slug,
        "role": session.get("role"),
        "runner": session.get("runner"),
        "title": session.get("title"),
        "taskId": session.get("taskId"),
        "externalSessionId": session.get("externalSessionId"),
        "startedAt": session.get("startedAt"),
        "endedAt": session.get("endedAt"),
        **detail,
        "decisions": decisions,
    }

def _repo_response_for_path(project: dict[str, Any], path: str | None = None) -> dict[str, Any]:
    if not project.get("localRepoPath"):
        raise HTTPException(status_code=400, detail="Project has no localRepoPath configured")

    repo_root = Path(project["localRepoPath"]).resolve()
    normalized = (path or "").strip("/")
    target = (repo_root / normalized).resolve() if normalized else repo_root
    if not str(target).startswith(str(repo_root)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not target.exists():
        missing = normalized or "."
        raise HTTPException(status_code=404, detail=f"File not found: {missing}")
    if target.is_dir():
        entries = []
        for child in sorted(target.iterdir()):
            entries.append({
                "name": child.name,
                "path": str(child.relative_to(repo_root)),
                "kind": "directory" if child.is_dir() else "file",
                "extension": child.suffix.lstrip(".") if child.is_file() else None,
                "sizeBytes": child.stat().st_size if child.is_file() else None,
            })
        return {"path": normalized, "kind": "directory", "entries": entries}

    suffix = target.suffix.lower()
    syntax_kind = {
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".py": "python",
        ".sh": "shell",
        ".txt": "text",
    }.get(suffix, "text")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}")

    return {
        "path": normalized,
        "kind": "file",
        "syntaxKind": syntax_kind,
        "extension": suffix.lstrip("."),
        "sizeBytes": target.stat().st_size,
        "content": content,
    }


@router.get("/{slug}/repo")
async def get_project_repo_root(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return _repo_response_for_path(project, None)


@router.get("/{slug}/repo/tree")
async def get_project_repo_tree(slug: str, rootDir: str | None = Query(None), maxDepth: int = Query(3)):
    project = await planner_service.get_project_by_slug(slug)
    requested = (rootDir or "").strip("/")
    response = _repo_response_for_path(project, requested or None)
    if response.get("kind") != "directory":
        raise HTTPException(status_code=400, detail="Requested path is not a directory")
    # `maxDepth` is accepted for backward compatibility even though the response
    # is intentionally shallow; the repo UI drills in path-by-path.
    response["maxDepth"] = maxDepth
    return response


@router.get("/{slug}/repo/file")
async def get_project_repo_file_compat(slug: str, path: str = Query(...)):
    project = await planner_service.get_project_by_slug(slug)
    response = _repo_response_for_path(project, path)
    if response.get("kind") != "file":
        raise HTTPException(status_code=400, detail="Requested path is not a file")
    return response


@router.get("/{slug}/repo/{path:path}")
async def get_project_repo_file(slug: str, path: str):
    """
    Read a file from the project's local Git repository by repo-relative path.

    Used by the frontend repo browser and deep-linked review files
    (research_plan/current_plan.md, task_board.md, sessions/**/summary.md, etc.)

    Returns the file content as a string plus metadata about the file type
    so the frontend can choose the right renderer (markdown, yaml, json, text).

    Raises 404 for missing files and 400 for path-traversal attempts.
    """
    project = await planner_service.get_project_by_slug(slug)
    return _repo_response_for_path(project, path)


@router.post("/{slug}/runner/sessions/{session_id}/commands")
async def send_project_runner_session_command(slug: str, session_id: str, data: ProjectRunnerCommandRequest):
    project = await planner_service.get_project_by_slug(slug)
    session = await running_agent_service.get_running_agent(session_id)
    if not session or session.get("projectId") != project["_id"]:
        raise HTTPException(status_code=404, detail="Runner session not found")
    from app.runners import session_lifecycle

    try:
        command = await session_lifecycle.append_session_command(
            session_id,
            command_type=data.commandType,
            content=data.content,
            payload=data.payload,
            idempotency_key=data.idempotencyKey,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "command": command}


@router.post("/{slug}/runner/sessions/{session_id}/cancel")
async def cancel_project_runner_session(slug: str, session_id: str):
    project = await planner_service.get_project_by_slug(slug)
    from app.runners import session_lifecycle
    return await session_lifecycle.cancel_runner_session(
        session_id,
        project_id=project["_id"],
    )


@router.post("/{slug}/runner/sessions/{session_id}/poll")
async def trigger_project_runner_session_poll(
    slug: str,
    session_id: str,
    background_tasks: BackgroundTasks,
):
    project = await planner_service.get_project_by_slug(slug)
    from app.runners import session_lifecycle
    background_tasks.add_task(
        session_lifecycle.poll_session_until_done,
        session_id,
        project_id=project["_id"],
    )
    return {"ok": True, "message": "Polling started in background"}


@router.get("/{slug}/agents/active")
async def list_active_agents(slug: str):
    """Return currently active (queued/running/awaiting_*) sessions for this project."""
    project = await planner_service.get_project_by_slug(slug)
    sessions = await running_agent_service.list_project_running_agents(
        project["_id"],
        active_only=True,
        limit=50,
    )
    from app.services.session_detail_service import build_session_detail
    return {
        "agents": [
            (
                lambda detail: {
                    "sessionId": s.get("_id") or s.get("sessionId"),
                    "role": s.get("role"),
                    "runner": s.get("runner"),
                    "status": s.get("status"),
                    "title": s.get("title"),
                    "startedAt": s.get("startedAt"),
                    "taskId": s.get("taskId"),
                    "currentFocus": detail.get("currentFocus"),
                    "thinkingSummary": detail.get("thinkingSummary"),
                    "workingOn": detail.get("workingOn"),
                    "currentActivity": detail.get("currentActivity"),
                }
            )(
                build_session_detail(resolved)
                if (resolved := _resolve_session_path(project, s)) and Path(resolved).exists()
                else {}
            )
            for s in sessions
        ]
    }


class ResearchAgentSpec(BaseModel):
    focus: str
    queries: list[str] = []


class RunResearchAgentsRequest(BaseModel):
    agents: list[ResearchAgentSpec]
    extra_context: str = ""
    output_subdir: str = "research/findings"


@router.post("/{slug}/research-agents/run")
async def run_research_agents_direct(slug: str, data: RunResearchAgentsRequest, background_tasks: BackgroundTasks):
    """Directly trigger Gemini research subagents and commit findings to repo."""
    from app.services.research_subagent import run_research_agents

    project = await planner_service.get_project_by_slug(slug)

    async def _run():
        results = await run_research_agents(
            project,
            agents=[a.model_dump() for a in data.agents],
            output_subdir=data.output_subdir,
            extra_context=data.extra_context,
        )
        from app.services.planner_runtime import _git_commit_and_push
        await _git_commit_and_push(
            project,
            f"feat(research): add findings from {len(results)} research subagent(s)",
        )

    background_tasks.add_task(_run)
    return {
        "ok": True,
        "message": f"Launched {len(data.agents)} research agent(s) in background",
        "agents": [a.focus for a in data.agents],
    }


@router.get("/{slug}/goal")
async def get_project_goal(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    bundle = goal_service.load_goal_bundle(project)
    if not bundle:
        raise HTTPException(status_code=404, detail="Goal mode has not been configured for this project.")
    return bundle


@router.post("/{slug}/goal")
async def configure_project_goal(
    slug: str,
    data: GoalContractRequest,
    background_tasks: BackgroundTasks,
):
    project = await planner_service.get_project_by_slug(slug)
    bundle = goal_service.create_goal_contract(
        project,
        {
            "objective": data.objective,
            "successCriteria": data.successCriteria,
            "requiredEvidence": data.requiredEvidence,
            "forbiddenShortcuts": data.forbiddenShortcuts,
            "escalationPolicy": data.escalationPolicy,
            "allowedSpend": data.allowedSpend.model_dump(),
        },
    )
    preflight = goal_service.evaluate_preflight(project)
    if data.launchAutopilot and preflight.get("passed"):
        from app.services import autopilot_service

        background_tasks.add_task(autopilot_service.start_autopilot, slug, False)
    return {
        **bundle,
        "preflight": preflight,
        "autopilotLaunchQueued": bool(data.launchAutopilot and preflight.get("passed")),
    }

# --- Autopilot (God Mode) ---

@router.post("/{slug}/autopilot")
async def toggle_autopilot(
    slug: str,
    data: AutopilotRequest,
    background_tasks: BackgroundTasks,
):
    from app.services import autopilot_service
    if data.enabled:
        background_tasks.add_task(autopilot_service.start_autopilot, slug, data.autoApprove, data.dispatchApprovalRequired)
        return {"status": "started", "slug": slug, "autoApprove": data.autoApprove, "dispatchApprovalRequired": data.dispatchApprovalRequired}
    else:
        await autopilot_service.stop_autopilot(slug)
        return {"status": "stopped", "slug": slug}

@router.get("/{slug}/autopilot/status")
async def get_autopilot_status(slug: str):
    from app.services import autopilot_service
    snapshot = await autopilot_service.ensure_autopilot_running(slug)
    return {
        "enabled": snapshot["desired_enabled"],
        "active": snapshot["active"],
        "autoApprove": snapshot["auto_approve"],
        "dispatchApprovalRequired": snapshot.get("dispatch_approval_required", False),
    }


@router.get("/{slug}/planner/decisions")
async def get_planner_decisions(slug: str, limit: int = 50):
    project = await planner_service.get_project_by_slug(slug)
    return _load_planner_decisions(project, limit=limit)


class AnswerQaRequest(BaseModel):
    answer: str


@router.get("/{slug}/qa/pending")
async def get_pending_qa(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return _load_pending_qa(project)


@router.post("/{slug}/qa/{question_id}/answer")
async def answer_question(slug: str, question_id: str, data: AnswerQaRequest):
    import json
    import datetime
    project = await planner_service.get_project_by_slug(slug)
    local_path = project.get("localRepoPath")
    if not local_path:
        raise HTTPException(status_code=400, detail="Project lacks a local repo path")
    
    from app.services.planner_answer_service import QA_LOG_REL_PATH
    qa_path = Path(local_path) / QA_LOG_REL_PATH
    if not qa_path.exists():
        raise HTTPException(status_code=404, detail="Q&A log not found")
        
    try:
        log = json.loads(qa_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read Q&A log: {e}")
        
    target_entry = None
    for entry in log:
        if entry.get("question_id") == question_id:
            target_entry = entry
            break
            
    if not target_entry:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")
        
    target_entry["answer"] = data.answer
    target_entry["status"] = "resolved"
    target_entry["timestamp"] = datetime.datetime.now(datetime.UTC).isoformat() + "Z"
    qa_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    
    session_id = target_entry.get("session_id")
    if session_id:
        agent_session = await running_agent_service.get_running_agent(session_id)
        if agent_session:
            from app.runners.base import RunnerEvent, RunnerEventType
            from app.services.convex_client import convex
            import time
            
            event = RunnerEvent(
                event_type=RunnerEventType.PROGRESS,
                session_id=session_id,
                normalized_payload={
                    "message": f"Q&A Resolved: {data.answer}",
                    "question": target_entry.get("question"),
                    "answer": data.answer,
                    "status": "resolved"
                },
                raw_payload=target_entry,
            )
            await convex.mutation(
                "runnerEvents:append",
                {
                    "agentSessionId": agent_session["_id"],
                    **event.to_convex_dict(),
                    "createdAt": int(time.time() * 1000),
                }
            )
            await running_agent_service.update_running_agent(session_id, status="running")
            
    return {"status": "resolved", "question_id": question_id}


class ApproveDispatchRequest(BaseModel):
    edits: dict[str, Any] | None = None


class RejectDispatchRequest(BaseModel):
    reason: str


def _load_planner_decisions(project: dict, limit: int = 50) -> list[dict[str, Any]]:
    import json

    local_path = project.get("localRepoPath")
    if not local_path:
        return []

    decisions_path = Path(local_path) / "research_plan" / "planner_decisions.jsonl"
    if not decisions_path.exists():
        return []

    decisions: list[dict[str, Any]] = []
    try:
        with open(decisions_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    decisions.append(json.loads(line))
                except Exception:
                    continue
    except Exception as exc:
        logger.warning("Failed to read planner_decisions.jsonl: %s", exc)
        return []

    return decisions[::-1][:limit]


def _load_pending_qa(project: dict) -> list[dict[str, Any]]:
    import json

    local_path = project.get("localRepoPath")
    if not local_path:
        return []

    from app.services.planner_answer_service import QA_LOG_REL_PATH

    qa_path = Path(local_path) / QA_LOG_REL_PATH
    if not qa_path.exists():
        return []

    try:
        log = json.loads(qa_path.read_text(encoding="utf-8"))
        return [entry for entry in log if entry.get("status") in {"pending", "awaiting_human"}]
    except Exception as exc:
        logger.warning("Failed to load Q&A log: %s", exc)
        return []


def _load_pending_dispatches(project: dict) -> list[dict[str, Any]]:
    import json

    local_path = project.get("localRepoPath")
    if not local_path:
        return []

    pending_dir = Path(local_path) / "research_plan" / "pending_dispatch"
    if not pending_dir.exists():
        return []

    dispatches: list[dict[str, Any]] = []
    for file_path in pending_dir.glob("*.json"):
        try:
            dispatches.append(json.loads(file_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return dispatches


@router.get("/{slug}/planner/control-plane")
async def get_planner_control_plane(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    home = await _build_planner_home_payload(project, slug)
    summary = home["controlPlane"]

    return {
        "board": {
            "board": home["planner"]["board"],
            "tasks": home["planner"]["tasks"],
            "approvals": home["planner"]["approvals"],
            "blockersPath": home["planner"]["files"]["blockers"] or "research_plan/blockers.md",
            "sessions": home["planner"]["sessions"],
        },
        "autopilot": home["autopilot"],
        "goal": summary.get("goal"),
        "phase": summary.get("phase"),
        "nextAction": summary.get("nextAction"),
        "currentBlocker": summary.get("currentBlocker"),
        "projectReality": summary.get("projectReality"),
        "auditors": summary.get("auditors"),
        "closeoutCertificate": summary.get("closeoutCertificate"),
        "missionBrief": summary.get("missionBrief"),
        "pendingDispatches": home["pendingDispatches"],
        "pendingQuestions": home["pendingQuestions"],
        "decisions": home["decisions"],
        "snapshot": summary.get("snapshot"),
        "refreshedAt": home["refreshedAt"],
    }


@router.get("/{slug}/dispatches/pending")
async def get_pending_dispatches(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return _load_pending_dispatches(project)


@router.post("/{slug}/dispatches/{wo_id}/approve")
async def approve_pending_dispatch_route(slug: str, wo_id: str, data: ApproveDispatchRequest):
    project = await planner_service.get_project_by_slug(slug)
    local_path = project.get("localRepoPath")
    if not local_path:
        raise HTTPException(status_code=400, detail="Project lacks a local repo path")
        
    from app.runners import session_lifecycle
    try:
        res = await session_lifecycle.resume_pending_dispatch(
            project_root=Path(local_path),
            work_order_id=wo_id,
            edits=data.edits,
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slug}/dispatches/{wo_id}/reject")
async def reject_pending_dispatch_route(slug: str, wo_id: str, data: RejectDispatchRequest):
    project = await planner_service.get_project_by_slug(slug)
    local_path = project.get("localRepoPath")
    if not local_path:
        raise HTTPException(status_code=400, detail="Project lacks a local repo path")
        
    from app.runners import session_lifecycle
    try:
        await session_lifecycle.reject_pending_dispatch(
            project_root=Path(local_path),
            work_order_id=wo_id,
            reason=data.reason,
        )
        return {"status": "rejected", "work_order_id": wo_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{slug}/autopilot/kill")
async def kill_project_autopilot(slug: str, payload: dict = Body(default_factory=dict)):
    """Engage the project-scoped kill switch.

    Stops the autopilot loop for this project and cancels its active runner
    session (if any). The global kill switch is unaffected.
    """
    from app.services import kill_switch_service
    reason = payload.get("reason") if isinstance(payload, dict) else None
    engaged_by = payload.get("engagedBy") if isinstance(payload, dict) else None
    return await kill_switch_service.engage_project(slug, reason=reason, engaged_by=engaged_by)


@router.post("/{slug}/autopilot/release")
async def release_project_autopilot(slug: str):
    """Release the project-scoped kill switch."""
    from app.services import kill_switch_service
    return await kill_switch_service.release_project(slug)


@router.get("/{slug}/phase")
async def get_project_phase(slug: str):
    """Single authoritative phase projection for a project.

    Returns the current lifecycle phase, the top blocker, the next recommended
    action, and all five auditor statuses in one call.  This is the canonical
    control-plane endpoint: the UI, autopilot, and any operator query should
    use this instead of assembling partial signals.
    """
    project = await planner_service.get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")

    projection = command_center_service.load_control_plane_summary(project)
    summary = projection["summary"]
    active_sessions: list[dict] = []
    try:
        from app.services.running_agent_service import list_project_running_agents
        active_sessions = await list_project_running_agents(
            str(project.get("_id")),
            active_only=True,
            limit=50,
        )
    except Exception:
        pass

    if projection["snapshot"]["loaded"]:
        task_counts = summary.get("taskCounts") or {}
        total_tasks = int(task_counts.get("total") or 0)
        terminal_tasks = sum(
            int(count or 0)
            for status, count in (task_counts.get("byStatus") or {}).items()
            if status in {"done", "cancelled"}
        )
        return {
            "slug": slug,
            "phase": summary.get("lifecyclePhase"),
            "topBlocker": summary.get("currentBlocker"),
            "nextAction": summary.get("nextAction"),
            "auditors": summary.get("auditors") or {},
            "activeSessions": len(active_sessions),
            "openTasks": max(total_tasks - terminal_tasks, 0),
            "snapshot": projection["snapshot"],
        }

    root = planner_service.project_root_from_record(project)
    tasks: list[dict] = []
    try:
        board = await planner_service.ensure_main_board(project)
        tasks = await planner_service.list_tasks(board["_id"], project=project)
    except Exception:
        pass

    auditors = await build_auditor_statuses(project, tasks=tasks, active_sessions=active_sessions)
    manifest = load_manifest(root) if root else None

    # Infer current lifecycle phase from auditor and repo state
    phase = _infer_lifecycle_phase(root, manifest, auditors, tasks, active_sessions)

    # Top blocker: first non-ready auditor's first blocker
    top_blocker: str | None = None
    for key in ("session", "planner", "ontology", "integrity", "closeout"):
        a = auditors.get(key) or {}
        if str(a.get("status") or "") == "blocked":
            blockers = a.get("blockers") or []
            if blockers:
                top_blocker = f"{key}: {blockers[0]}"
                break

    # Recommended next action
    next_action = _recommend_next_action(phase, auditors, tasks, active_sessions)

    return {
        "slug": slug,
        "phase": phase,
        "topBlocker": top_blocker,
        "nextAction": next_action,
        "auditors": auditors,
        "activeSessions": len(active_sessions),
        "openTasks": sum(1 for t in tasks if t.get("status") not in {"done", "cancelled"}),
        "snapshot": {
            "loaded": False,
            "path": command_center_service.CONTROL_PLANE_SNAPSHOT_RELATIVE_PATH,
            "generatedAt": None,
            "version": command_center_service.CONTROL_PLANE_SNAPSHOT_VERSION,
        },
    }


def _infer_lifecycle_phase(
    root: Any,
    manifest: Any,
    auditors: dict[str, Any],
    tasks: list[dict],
    active_sessions: list[dict],
) -> str:
    """Delegate to the shared command-center helper.

    Kept as a thin wrapper so existing callers in this module are unaffected.
    """
    from app.services.command_center_service import infer_lifecycle_phase

    return infer_lifecycle_phase(root, manifest, auditors, tasks, active_sessions)


def _recommend_next_action(
    phase: str,
    auditors: dict[str, Any],
    tasks: list[dict],
    active_sessions: list[dict],
) -> str:
    if active_sessions:
        roles = {str(s.get("role") or "agent") for s in active_sessions}
        return f"Wait for {len(active_sessions)} active session(s) to complete ({', '.join(sorted(roles))})."

    planner = auditors.get("planner") or {}
    if str(planner.get("status") or "") == "blocked":
        b = (planner.get("blockers") or ["planner blocked"])[0]
        return f"Resolve planner blocker before launching new work: {b}"

    if phase == "brief":
        return "Add a research brief to topics/ and scope the project."
    if phase == "scoped":
        return "Discover and register sources in research_plan/state/sources.json."
    if phase == "source_discovery":
        return "Configure data pipelines and ontology for source ingestion."
    if phase == "config_ready":
        return "Run the data agent to hydrate the ontology."
    if phase == "hydration_ready":
        return "Run the data agent to hydrate the ontology."
    if phase == "hydrated":
        return "Run ontology health checks and verify hydration quality."
    if phase == "ontology_healthy":
        return "Run research and analysis sessions."
    if phase == "research_active":
        ready = [t for t in tasks if t.get("status") == "ready"]
        return f"Launch next research task ({ready[0]['title'][:60]}…)." if ready else "Create or assign research tasks."
    if phase == "synthesis_ready":
        return "Run artifact synthesis session to produce final outputs."
    if phase == "closed":
        return "Project is closed. Review artifacts and consider follow-up questions."
    return "Review auditor statuses to determine next step."


@router.get("/{slug}/next-best-action")
async def get_next_best_action(
    slug: str = FPath(...),
) -> dict[str, Any]:
    """Fetch the next best research action for a project (Track B)."""
    from app.services import lifecycle_service, planner_service
    
    project = await planner_service.get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    
    return await lifecycle_service.evaluate_lifecycle(project, tasks)
