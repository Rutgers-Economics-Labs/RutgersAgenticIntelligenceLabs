import time
import yaml
import subprocess
import os
import platform
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
from app.services.device_service import get_device_metadata
from app.services.hydration_registry_service import (
    get_hydration_status as get_project_hydration_status,
    register_hydration_artifact,
    resolve_pipeline_slug,
)
from app.services.repo_contract_service import infer_github_repo, render_rail_manifest
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

router = APIRouter(prefix="/projects", tags=["projects"])

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


KNOWN_PROJECT_REPOS = [
    {
        "name": "Academic",
        "slug": "academic",
        "description": "Academic research starter workspace.",
        "repoUrl": "https://github.com/Rutgers-Economics-Labs/RAIL-academic",
        "directory": "RAIL-academic",
    },
    {
        "name": "Synthetic Test",
        "slug": "synthetic",
        "description": "Synthetic test workspace for RAIL workflows.",
        "repoUrl": "https://github.com/Rutgers-Economics-Labs/RAIL-synthetic-test",
        "directory": "RAIL-synthetic-test",
    },
    {
        "name": "RAIL Census Ontology Starter",
        "slug": "census-ontology-starter",
        "description": "Minimal Census-backed ontology starter repo.",
        "repoUrl": "https://github.com/Rutgers-Economics-Labs/RAIL-Census-Ontology-Starter",
        "directory": "RAIL-Census-Ontology-Starter",
    },
]


def _projects_base_dir() -> Path:
    default_base = Path(__file__).resolve().parents[5]
    return Path(os.environ.get("RAIL_PROJECTS_DIR", str(default_base))).expanduser().resolve()


def _known_project(slug: str) -> dict | None:
    for item in KNOWN_PROJECT_REPOS:
        if item["slug"] == slug:
            return item
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


async def _catalog_row(defn: dict) -> dict:
    root = _projects_base_dir() / defn["directory"]
    metadata = _manifest_metadata(root, defn) if root.exists() else {}
    slug = metadata.get("slug") or defn["slug"]
    project = await convex.query("projects:getBySlug", {"slug": slug})
    return {
        **defn,
        "slug": slug,
        "name": metadata.get("name") or defn["name"],
        "description": metadata.get("description") or defn["description"],
        "localRepoPath": str(root),
        "localExists": root.exists(),
        "manifestExists": (root / "rail.yaml").exists(),
        "backendProject": project,
        "needsClone": not root.exists(),
    }


def _configured_pipeline_slug(project: dict, project_root: Path, requested: str | None = None) -> str:
    if requested:
        return requested
    if project.get("pipelineConfigSlug"):
        return str(project["pipelineConfigSlug"])
    try:
        slug = resolve_pipeline_slug(project_root, project.get("manifestPath") or "rail.yaml")
        if (project_root / ".ontology" / "pipelines" / f"{slug}.yaml").exists():
            return slug
    except Exception:
        pass

    pipeline_dir = project_root / ".ontology" / "pipelines"
    candidates = sorted(path.stem for path in pipeline_dir.glob("*.y*ml")) if pipeline_dir.is_dir() else []
    for preferred in (f"{project.get('slug')}_hydration", "nj_hydration", "academic_hydration", "default"):
        if preferred in candidates:
            return preferred
    return candidates[0] if candidates else "default"


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
    onto_path = project_root / ".ontology" / "ontology.yaml"
    if onto_path.exists():
        onto_content = onto_path.read_text(encoding="utf-8")
        onto_ref = str(pipeline_spec.get("ontology", "core") or "core")
        onto_configs[onto_ref] = onto_content
        onto_configs[Path(onto_ref).stem] = onto_content

    return pipeline_content, api_configs, onto_configs


def _git_init(path: Path) -> None:
    if (path / ".git").exists():
        return
    result = subprocess.run(["git", "init", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git init failed: {result.stderr or result.stdout}")


def _relative_to_project(project_root: Path | None, path: Path | None) -> str | None:
    if project_root is None or path is None or not path.exists():
        return None
    return str(path.relative_to(project_root))


def _session_review_model(project: dict, session: dict) -> dict:
    project_root = Path(project["localRepoPath"]) if project.get("localRepoPath") else None
    session_path = Path(session["sessionPath"]) if session.get("sessionPath") else None
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
    rows = []
    for defn in KNOWN_PROJECT_REPOS:
        try:
            rows.append(await _catalog_row(defn))
        except Exception as exc:
            root = _projects_base_dir() / defn["directory"]
            rows.append(
                {
                    **defn,
                    "localRepoPath": str(root),
                    "localExists": root.exists(),
                    "manifestExists": (root / "rail.yaml").exists(),
                    "backendProject": None,
                    "needsClone": not root.exists(),
                    "error": str(exc),
                }
            )
    return {"projects": rows}


@router.post("/catalog/{slug}/activate")
async def activate_catalog_project(slug: str, data: CatalogProjectActionRequest):
    defn = _known_project(slug)
    if not defn:
        raise HTTPException(404, f"Unknown catalog project '{slug}'")

    root = Path(data.targetDir).expanduser().resolve() if data.targetDir else _projects_base_dir() / defn["directory"]
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
        result = subprocess.run(["git", "clone", defn["repoUrl"], str(root)], capture_output=True, text=True)
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
    _git_init(repo_root)

    git_repo = infer_github_repo(data.gitRepoUrl) if data.gitRepoUrl else None
    project_id = await convex.mutation(
        "projects:create",
        {
            "name": project_meta["name"],
            "slug": slug,
            "description": project_meta["description"],
            "approach": project_meta.get("approach", "ontology-first"),
            "gitRepoUrl": data.gitRepoUrl,
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

    source_counts = preview["readiness"]
    status = "ready_for_hydration_review" if source_counts.get(DRAFT, 0) == 0 and source_counts.get(MISSING, 0) == 0 and created_source_slugs else "draft"
    await convex.mutation(
        "projects:updateById",
        {
            "projectId": project_id,
            "ontologyConfigSlug": ontology["slug"],
            "apiConfigSlugs": created_source_slugs,
            "pipelineConfigSlug": pipeline["slug"],
            "defaultBranch": data.defaultBranch,
            "github": git_repo,
            "githubSyncMode": data.githubSyncMode or "manual",
            "status": status,
            "creationStatus": "from_brief",
            "briefHash": preview["briefHash"],
            "researchGraphSummary": {
                "title": preview["researchGraph"]["title"],
                "objective": preview["researchGraph"]["objective"],
                "methods": preview["researchGraph"]["methods"],
                "deliverables": preview["researchGraph"]["deliverables"],
            },
            "sourceReadinessCounts": source_counts,
        },
    )

    project = await convex.query("projects:getById", {"projectId": project_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project could not be loaded after creation")
    rail_path = repo_root / "rail.yaml"
    existing_rail = rail_path.read_text(encoding="utf-8") if rail_path.exists() else None
    rail_path.write_text(render_rail_manifest(project, existing_rail), encoding="utf-8")
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
        "hydrationReady": status == "ready_for_hydration_review",
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
    if project.get("activeOntologyDuckdbPath"):
        try:
            from app.services import sql_service, ontology_service
            sql_service.set_path(project["activeOntologyDuckdbPath"])
            schema = sql_service.get_schema()
            classes = await ontology_service._run(ontology_service.list_classes)
            context["ontology"] = {
                "classes": classes,
                "schema_ddl": sql_service.get_schema_ddl(),
            }
        except Exception:
            pass

    # Fetch data sources
    api_slugs = project.get("apiConfigSlugs", [])
    for slug_s in api_slugs:
        cfg = await convex.query("configs:getApiBySlug", {"slug": slug_s})
        if cfg:
            context["data_sources"].append({"slug": cfg["slug"], "name": cfg["name"]})

    # Fetch pipeline info
    pipeline_slug = project.get("pipelineConfigSlug")
    if pipeline_slug:
        pipeline = await convex.query("configs:getPipelineBySlug", {"slug": pipeline_slug})
        if pipeline:
            context["pipelines"].append({"slug": pipeline["slug"], "name": pipeline["name"]})

    return context


@router.get("/{slug}/command-center")
async def get_command_center(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    return await command_center_service.build_command_center(project)


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
        "messages": list(reversed(messages)),
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

    pipeline_slug = _configured_pipeline_slug(project, project_root, data.pipelineSlug)
    local_configs = _local_hydration_configs(project_root, pipeline_slug)

    if local_configs:
        pipeline_content, api_configs, onto_configs = local_configs
        mutation_result = await convex.mutation(
            "jobs:create",
            {
                "pipelineConfigId": f"local:{slug}:{pipeline_slug}",
                "pipelineSlug": pipeline_slug,
                "projectSlug": slug,
                "projectId": project.get("_id"),
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
            raise HTTPException(404, str(exc)) from exc

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
    return {"approvalId": approval_id}


@router.post("/{slug}/approvals/{approval_id}/resolve")
async def resolve_project_approval(slug: str, approval_id: str, data: ApprovalResolveRequest):
    project = await planner_service.get_project_by_slug(slug)
    approval = await planner_service.resolve_approval(
        project=project,
        approval_id=approval_id,
        status=data.status,
        granted_by_user_id=data.grantedByUserId,
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
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
    )

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
    session_path = session.get("sessionPath")
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
    session_path = session.get("sessionPath")
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
