import logging
import time
import yaml
import subprocess
import os
import platform

logger = logging.getLogger(__name__)
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from rail.bootstrap import bootstrap_future_project
from rail.manifest import load_manifest

from app.services.convex_client import convex
from app.services import ontology_service, sql_service
from app.services import hydration_worker
from app.services.project_artifacts_service import find_latest_success_job_with_outputs
from app.services import planner_runtime, planner_service
from app.services import running_agent_service
from app.services import session_files
from app.services import command_center_service
from app.services import reconciliation_service
from app.services.auditor_service import build_auditor_statuses
from app.services.device_service import get_device_metadata
from app.services.hydration_registry_service import (
    get_hydration_status as get_project_hydration_status,
    register_hydration_artifact,
    resolve_pipeline_slug,
)
from app.services.repo_contract_service import infer_github_repo, render_rail_manifest
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
from app.services.role_runtime_service import load_role_runtime_config
from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy, is_write_capable

router = APIRouter(prefix="/projects", tags=["projects"])


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
    branch: str = "main"
    allowedPaths: list[str] = []
    acceptanceCriteria: list[str] = []
    runnerName: str = "jules"
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


def _validate_trusted_source_contract(
    *,
    quality_status: str | None,
    admissibility_status: str | None,
    freshness_status: str | None,
    provenance: dict | None,
) -> None:
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


def _validate_claim_reference_integrity(
    repo,
    *,
    project_root: Path,
    evidence_paths: list[str],
    source_keys: list[str],
    evidence_chunk_keys: list[str],
) -> None:
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
    inputs: list[str],
    scripts: list[str],
    sources: list[str],
    assumptions: list[str],
    claims: list[str],
    verification_runs: list[str],
) -> None:
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


def _csv_query_param(value: str | None) -> list[str] | None:
    if not value:
        return None
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or None


# Catalog projects are now managed in Convex.


def _projects_base_dir() -> Path:
    default_base = Path(__file__).resolve().parents[5]
    return Path(os.environ.get("RAIL_PROJECTS_DIR", str(default_base))).expanduser().resolve()


async def _known_project(slug: str) -> dict | None:
    return await convex.query("projects:getBySlug", {"slug": slug})


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
    payload = {
        "name": metadata.get("name") or defn["name"],
        "slug": slug,
        "description": metadata.get("description") or defn["description"],
        "approach": "ontology-first",
        "gitRepoUrl": defn["repoUrl"],
        "localRepoPath": str(root),
        "manifestPath": "rail.yaml",
        "defaultBranch": metadata.get("defaultBranch") or "main",
    }
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
    project_id = await convex.mutation("projects:create", payload)
    return await convex.query("projects:getById", {"projectId": project_id}) or {**payload, "_id": project_id}


async def _catalog_row(project: dict) -> dict:
    repo_path = project.get("localRepoPath")
    if repo_path:
        root = Path(repo_path).expanduser().resolve()
    else:
        # Fallback if localRepoPath is missing
        root = _projects_base_dir() / project["slug"]
        
    metadata = _manifest_metadata(root, project) if root.exists() else {}
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

    project_id = await convex.mutation("projects:create", project_data)
    return await convex.query("projects:getBySlug", {"slug": data.slug})


@router.get("")
async def list_projects_catalog():
    projects = _dedupe_projects_for_catalog(await convex.query("projects:list", {}) or [])
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
    project = await _known_project(slug)
    if not project:
        raise HTTPException(404, f"Unknown catalog project '{slug}'")

    repo_path = project.get("localRepoPath")
    if data.targetDir:
        root = Path(data.targetDir).expanduser().resolve()
    elif repo_path:
        root = Path(repo_path).expanduser().resolve()
    else:
        root = _projects_base_dir() / project["slug"]
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
        clone_url = defn["repoUrl"]
        github_repo = infer_github_repo(clone_url)
        if github_repo:
            token = await GitHubService().get_installation_token(github_repo)
            # Embed token into HTTPS URL: https://x-access-token:<token>@github.com/...
            clone_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
        result = subprocess.run(["git", "clone", clone_url, str(root)], capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(500, f"git clone failed: {result.stderr or result.stdout}")

    project = await _upsert_known_project_record(defn, root)
    row = await _catalog_row(defn)
    return {"status": "ready", "project": project, "catalogProject": row}


@router.post("/future/bootstrap")
async def bootstrap_future_project_route(data: BootstrapFutureProjectRequest):
    root = bootstrap_future_project(
        data.targetDir,
        name=data.name,
        slug=data.slug,
        default_branch=data.defaultBranch,
    )

    manifest = load_manifest(root)
    manifest_slug = manifest.project.slug
    project_id = await convex.mutation(
        "projects:create",
        {
            "name": data.name,
            "slug": manifest_slug,
            "description": data.description or "Future RAIL project",
            "approach": "ontology-first",
            "gitRepoUrl": data.gitRepoUrl,
            "localRepoPath": str(root),
            "manifestPath": "rail.yaml",
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

    # Auto-create GitHub repo if no URL provided
    git_repo_url = data.gitRepoUrl
    if not git_repo_url:
        try:
            # Use a short repo name: RAIL- + first 40 chars of slug (trimmed at word boundary)
            short_slug = slug[:40].rstrip("-")
            repo_name = f"RAIL-{short_slug}"
            created = await GitHubService().create_repo(
                name=repo_name,
                description=project_meta.get("description", ""),
                private=True,
            )
            git_repo_url = f"https://github.com/{created['full_name']}"
        except Exception as exc:
            logger.error("GitHub repo creation failed for project '%s': %s", slug, exc)
            raise HTTPException(
                status_code=502,
                detail=f"GitHub repo creation failed: {exc}. Check that the GitHub App has 'administration: write' permission on the org.",
            )

    git_repo = infer_github_repo(git_repo_url) if git_repo_url else None
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

    # Push all local repo files to GitHub as the initial commit
    if git_repo:
        try:
            repo_files: list[dict] = []
            for file_path in repo_root.rglob("*"):
                if file_path.is_file() and ".git" not in file_path.parts:
                    rel = file_path.relative_to(repo_root).as_posix()
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        repo_files.append({"path": rel, "content": content})
                    except Exception:
                        pass
            if repo_files:
                await GitHubService().commit_files(git_repo, data.defaultBranch, repo_files, "chore: initial project scaffold from RAIL brief")
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
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    convex_project_id = project["_id"]
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
    embeddings_path = str(parent / "embeddings.db")

    now_ms = int(time.time() * 1000)
    patch: dict = {
        "projectId": convex_project_id,
        "status": "hydrated",
        "lastHydratedAt": now_ms,
        "activeOntologyDbPath": db_key,
        "activeOntologyOwlPath": owl_key,
        "activeOntologyDuckdbPath": duckdb_path,
        "activeOntologyEmbeddingsPath": embeddings_path,
    }
    if last_job_convex_id is not None:
        patch["lastJobId"] = last_job_convex_id
    await convex.mutation("projects:updateById", patch)

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
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    await convex.mutation("projects:clearHydration", {"projectId": project["_id"]})
    return {"ok": True, "slug": slug, "status": "ready"}


@router.post("/{slug}/sync-metadata")
async def sync_project_metadata(slug: str, data: ProjectMetadataSyncRequest):
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if "gitRepoUrl" in patch:
        inferred_repo = infer_github_repo(patch["gitRepoUrl"])
        if inferred_repo:
            patch["github"] = inferred_repo

    await convex.mutation("projects:updateById", {
        "projectId": project["_id"],
        **patch,
    })
    updated = await convex.query("projects:getById", {"projectId": project["_id"]})

    publish_result = None
    should_publish_manifest = any(field in patch for field in MANIFEST_BACKED_FIELDS)
    if should_publish_manifest and updated and await should_auto_publish(updated):
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
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(404, "Project not found")

    context = {
        "project": {
            "name": project["name"],
            "slug": project["slug"],
            "status": project.get("status"),
            "last_hydrated": project.get("lastHydratedAt"),
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
            art = await project_artifacts_service.resolve(slug)
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

    # Fetch data sources (Convex + Local Fallback)
    api_slugs = project.get("apiConfigSlugs", [])
    found_slugs = set()
    for slug_s in api_slugs:
        cfg = await convex.query("configs:getApiBySlug", {"slug": slug_s})
        if cfg:
            context["data_sources"].append({"slug": cfg["slug"], "name": cfg["name"]})
            found_slugs.add(slug_s)

    # Local fallback for sources
    from pathlib import Path
    import yaml
    local_sources = Path(project["localRepoPath"]) / ".ontology" / "sources"
    if local_sources.exists():
        for yml in local_sources.glob("*.yaml"):
            if yml.stem in found_slugs: continue
            try:
                with open(yml) as f:
                    cfg = yaml.safe_load(f)
                    if cfg and "name" in cfg:
                        context["data_sources"].append({"slug": yml.stem, "name": cfg["name"]})
            except Exception: pass

    # Fetch pipeline info (Convex + Local Fallback)
    pipeline_slug = project.get("pipelineConfigSlug")
    if pipeline_slug:
        pipeline = await convex.query("configs:getPipelineBySlug", {"slug": pipeline_slug})
        if pipeline:
            context["pipelines"].append({"slug": pipeline["slug"], "name": pipeline["name"]})
        else:
            # Local fallback
            local_pipelines = Path(project["localRepoPath"]) / ".ontology" / "pipelines"
            if local_pipelines.exists():
                for yml in local_pipelines.glob("*.yaml"):
                    if yml.stem == pipeline_slug:
                        context["pipelines"].append({"slug": yml.stem, "name": yml.stem})

    return context


@router.get("/{slug}/command-center")
async def get_command_center(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await command_center_service.build_command_center(project)


@router.post("/{slug}/command-center/reconcile")
async def reconcile_command_center_state(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await reconciliation_service.reconcile_project_reality(project)


@router.post("/{slug}/command-center/ontology-follow-ups/expand")
async def create_ontology_follow_up_task(slug: str, request: OntologyFollowUpTaskRequest):
    project = await planner_service.get_project_by_slug(slug)
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)

    title = str(request.title).strip()
    classification = str(request.classification).strip().lower()
    if not title:
        raise HTTPException(status_code=400, detail="Follow-up question title is required.")
    if classification not in {"requires_expansion", "blocked_by_data"}:
        raise HTTPException(status_code=400, detail="Classification must be requires_expansion or blocked_by_data.")

    if classification == "requires_expansion":
        task_title = f"Expand ontology coverage for: {title}"
        description = (
            f"Create the ontology expansion needed to answer: {title}. "
            "This should result in concrete source, pipeline, transform, or ontology-verification work."
        )
        agent_role = "data"
        repo_paths = [".ontology/sources", ".ontology/pipelines", ".ontology/transforms", "research_plan", "topics"]
        acceptance_criteria = [
            "the missing ontology coverage is translated into concrete source or pipeline work",
            "the task records which source, transform, or relationship expansion is required",
            "follow-on ontology verification work is identified if hydration changes are needed",
        ]
    else:
        task_title = f"Resolve data blocker for: {title}"
        description = (
            f"Investigate and document the missing data access needed to answer: {title}. "
            "Record the missing source, access blocker, and what would unblock ontology expansion."
        )
        agent_role = "research"
        repo_paths = ["research_plan", "topics", ".ontology/sources"]
        acceptance_criteria = [
            "the missing source or access blocker is documented explicitly",
            "the task records whether the blocker is licensing, permissions, provenance, or coverage",
            "the repo contains the next recommended expansion path if the blocker can be resolved",
        ]

    existing = next((task for task in tasks if str(task.get("title") or "") == task_title), None)
    if existing is not None:
        return {"created": False, "task": existing}

    task = await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=task_title,
        description=description,
        status="ready",
        agent_role=agent_role,
        repo_paths=repo_paths,
        acceptance_criteria=acceptance_criteria,
        runner="codex_cli",
    )
    await planner_service.sync_planner_files(project, board)
    return {"created": True, "task": task}


@router.get("/{slug}/skills")
async def get_project_skills(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return command_center_service.list_project_skills(project)


@router.get("/{slug}/sources")
async def get_project_sources(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return command_center_service.list_project_sources(project)


@router.get("/{slug}/artifacts")
async def get_project_artifacts(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return command_center_service.list_project_artifacts(project)


@router.get("/{slug}/integrity")
async def get_project_integrity(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return command_center_service.list_project_integrity(project)


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
    if data.targetState in {"partially_verified", "verified"}:
        auditors = await build_auditor_statuses(project)
        blocked: list[str] = []
        for key in ("ontology", "integrity"):
            status = auditors.get(key) or {}
            if str(status.get("status") or "") != "blocked":
                continue
            blocker = next((str(item) for item in (status.get("blockers") or []) if str(item).strip()), "blocked")
            blocked.append(f"{key}: {blocker}")
        if blocked:
            raise HTTPException(
                status_code=409,
                detail="Artifact promotion blocked by auditor state: " + "; ".join(blocked),
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
    if data.promotionState in {"partially_verified", "verified"}:
        auditors = await build_auditor_statuses(project)
        blocked: list[str] = []
        for key in ("ontology", "integrity"):
            status = auditors.get(key) or {}
            if str(status.get("status") or "") != "blocked":
                continue
            blocker = next((str(item) for item in (status.get("blockers") or []) if str(item).strip()), "blocked")
            blocked.append(f"{key}: {blocker}")
        if blocked:
            raise HTTPException(
                status_code=409,
                detail="Artifact lineage write blocked by auditor state: " + "; ".join(blocked),
            )
    repo = get_integrity_repo(root)
    _validate_artifact_lineage_references(
        repo,
        project_root=root,
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


@router.get("/{slug}/planner/home")
async def get_planner_home(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    messages = await planner_service.list_planner_messages(project, thread_id=thread_id, limit=50)
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    approvals = await planner_service.list_approvals(project)
    sessions = await running_agent_service.list_project_running_agents(project["_id"], active_only=False, limit=20)
    project_root = planner_service.project_root_from_record(project)
    research_plan_root = project_root / "research_plan" if project_root else None
    blockers_path = research_plan_root / "blockers.md" if research_plan_root else None
    sessions_root = research_plan_root / "sessions" if research_plan_root else None

    return {
        "project": {
            "id": project["_id"],
            "name": project["name"],
            "slug": project["slug"],
            "status": project.get("status"),
            "localRepoPath": project.get("localRepoPath"),
            "manifestPath": project.get("manifestPath") or "rail.yaml",
        },
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
    }


@router.post("/{slug}/planner/messages")
async def append_planner_message(slug: str, data: PlannerMessageRequest):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    await planner_service.append_planner_message(
        project=project,
        role=data.role,
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
    # Append to planner history as a system/agent message
    await planner_service.append_planner_message(
        project=project,
        role=data.role,
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
    board = await planner_service.ensure_main_board(project)
    tasks = await planner_service.list_tasks(board["_id"], project=project)
    sessions = await running_agent_service.list_project_running_agents(project["_id"], active_only=False, limit=20)
    return {
        "board": board,
        "tasks": tasks,
        "approvals": await planner_service.list_approvals(project),
        "blockersPath": "research_plan/blockers.md",
        "sessions": [_session_review_model(project, session) | {"id": session.get("_id"), "status": session.get("status"), "role": session.get("role")} for session in sessions],
    }


@router.post("/{slug}/planner/tasks")
async def create_planner_task(slug: str, data: PlannerTaskRequest):
    project = await planner_service.get_project_by_slug(slug)
    board = await planner_service.ensure_main_board(project, session_id=data.sessionId)
    task = await planner_service.create_task(
        project=project,
        board_id=board["_id"],
        title=data.title,
        description=data.description,
        status=data.status,
        agent_role=data.agentRole,
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
    board = await planner_service.ensure_main_board(project)
    await planner_service.update_task(task_id, project=project, **data.model_dump())
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
        
        # If no registered ID, we must use a fallback format that the database accepts
        effective_pipeline_id = pipeline_id or f"local_{pipeline_slug}"
        
        mutation_result = await convex.mutation(
            "jobs:create",
            {
                "pipelineConfigId": effective_pipeline_id,
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


@router.get("/{slug}/settings/secrets")
async def list_project_secrets(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    secrets = await convex.query("projectSecrets:listByProject", {"projectId": project["_id"]}) or []
    policies = await convex.query("agentSecretPolicies:listByProject", {"projectId": project["_id"]}) or []

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

    return {"secrets": masked, "policies": policies}


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
    return {"policies": policies}


@router.post("/{slug}/settings/agent-secret-policies")
async def upsert_agent_secret_policy(slug: str, data: AgentSecretPolicyUpsertRequest):
    project = await planner_service.get_project_by_slug(slug)
    policy_id = await convex.mutation(
        "agentSecretPolicies:upsert",
        {
            "projectId": project["_id"],
            "agentRole": data.agentRole,
            "allowedSecretNames": data.allowedSecretNames,
        },
    )
    return {"policyId": policy_id, "agentRole": data.agentRole}


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
    await convex.mutation(
        "agentSecretPolicies:deleteByRole",
        {"projectId": project["_id"], "agentRole": agent_role},
    )
    return {"deleted": True, "agentRole": agent_role}


@router.get("/{slug}/secrets/resolve")
async def resolve_secrets_for_agent(slug: str, agentRole: str = Query(...)):
    """Return decrypted secrets the given agent role is allowed to access.

    This endpoint is intended for runner/orchestrator use at task start time.
    It enforces the agent secret policy — only secrets in the role's allowlist
    are returned, and only if they exist in the project's secret store.
    """
    project = await planner_service.get_project_by_slug(slug)
    from app.services.secret_service import resolve_secrets_for_role
    secrets = await resolve_secrets_for_role(project["_id"], agentRole)
    return {"agentRole": agentRole, "secrets": secrets}


@router.get("/{slug}/approvals")
async def list_project_approvals(slug: str, limit: int = Query(100)):
    project = await planner_service.get_project_by_slug(slug)
    approvals = await planner_service.list_approvals(project)
    return {"approvals": approvals[:limit]}


@router.post("/{slug}/approvals")
async def create_project_approval(slug: str, data: ApprovalCreateRequest):
    project = await planner_service.get_project_by_slug(slug)
    approval_id = await planner_service.create_approval(
        project=project,
        task_id=data.taskId,
        agent_session_id=data.agentSessionId,
        approval_type=data.approvalType,
        status=data.status,
        requested_by_role=data.requestedByRole,
        granted_by_user_id=data.grantedByUserId,
    )
    from app.services.autopilot_service import trigger_wake
    trigger_wake(slug)
    return {"approvalId": approval_id}


@router.post("/{slug}/approvals/{approval_id}/resolve")
async def resolve_project_approval(slug: str, approval_id: str, data: ApprovalResolveRequest):
    project = await planner_service.get_project_by_slug(slug)
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

    repo_url = data.repoUrl or project.get("gitRepoUrl")
    if not repo_url:
        raise HTTPException(status_code=400, detail="Project has no gitRepoUrl and none provided")

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
            runner_name=data.runnerName,
            role=data.role,
            task_description=data.taskDescription,
            repo_url=repo_url,
            branch=data.branch,
            local_repo_path=project.get("localRepoPath"),
            allowed_paths=data.allowedPaths,
            acceptance_criteria=data.acceptanceCriteria,
            agent_role_for_secrets=data.agentRoleForSecrets,
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
    if not project.get("localRepoPath"):
        raise HTTPException(status_code=400, detail="Project has no localRepoPath configured")

    repo_root = Path(project["localRepoPath"]).resolve()
    # Normalise and guard against path traversal
    target = (repo_root / path).resolve()
    if not str(target).startswith(str(repo_root)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if target.is_dir():
        # Return a directory listing instead of file content
        entries = []
        for child in sorted(target.iterdir()):
            entries.append({
                "name": child.name,
                "path": str(child.relative_to(repo_root)),
                "kind": "directory" if child.is_dir() else "file",
                "extension": child.suffix.lstrip(".") if child.is_file() else None,
            })
        return {"path": path, "kind": "directory", "entries": entries}

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
        "path": path,
        "kind": "file",
        "syntaxKind": syntax_kind,
        "extension": suffix.lstrip("."),
        "sizeBytes": target.stat().st_size,
        "content": content,
    }


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
# --- Autopilot (God Mode) ---

@router.post("/{slug}/autopilot")
async def toggle_autopilot(
    slug: str,
    data: AutopilotRequest,
    background_tasks: BackgroundTasks,
):
    from app.services import autopilot_service
    if data.enabled:
        background_tasks.add_task(autopilot_service.start_autopilot, slug, data.autoApprove)
        return {"status": "started", "slug": slug, "autoApprove": data.autoApprove}
    else:
        await autopilot_service.stop_autopilot(slug)
        return {"status": "stopped", "slug": slug}

@router.get("/{slug}/autopilot/status")
async def get_autopilot_status(slug: str):
    from app.services import autopilot_service
    return {
        "enabled": autopilot_service.is_autopilot_active(slug),
        "autoApprove": autopilot_service.get_autopilot_config(slug).get("auto_approve", False)
    }
