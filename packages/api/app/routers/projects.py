import time
import yaml
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from rail.bootstrap import bootstrap_future_project
from rail.manifest import load_manifest

from app.services.convex_client import convex
from app.services import ontology_service, sql_service
from app.services.project_artifacts_service import find_latest_success_job_with_outputs
from app.services import planner_service
from app.services.device_service import get_device_metadata
from app.services.hydration_registry_service import (
    get_hydration_status as get_project_hydration_status,
    register_hydration_artifact,
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
    await planner_service.ensure_planner_thread(project_id)
    board = await planner_service.ensure_main_board(project_id)
    await planner_service.append_planner_message(
        project_id=project_id,
        role="system",
        content="Planner thread initialized.",
        message_type="system",
    )
    await planner_service.sync_planner_files(project, board)
    return await convex.query("projects:getById", {"projectId": project_id})


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
    project = await convex.query("projects:get", {"slug": slug})
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


@router.get("/{slug}/planner/thread")
async def get_planner_thread(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    messages = await planner_service.list_planner_messages(project["_id"], thread_id=thread_id)
    return {
        "threadId": thread_id,
        "messages": list(reversed(messages)),
    }


@router.get("/{slug}/planner/home")
async def get_planner_home(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    messages = await planner_service.list_planner_messages(project["_id"], thread_id=thread_id, limit=50)
    board = await planner_service.ensure_main_board(project["_id"])
    tasks = await planner_service.list_tasks(board["_id"])
    project_root = planner_service.project_root_from_record(project)
    research_plan_root = project_root / "research_plan" if project_root else None

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
            "files": {
                "currentPlan": str((research_plan_root / "current_plan.md").relative_to(project_root)) if research_plan_root and (research_plan_root / "current_plan.md").exists() else None,
                "taskBoard": str((research_plan_root / "task_board.md").relative_to(project_root)) if research_plan_root and (research_plan_root / "task_board.md").exists() else None,
            },
        },
    }


@router.post("/{slug}/planner/messages")
async def append_planner_message(slug: str, data: PlannerMessageRequest):
    project = await planner_service.get_project_by_slug(slug)
    thread_id = await planner_service.ensure_planner_thread(project["_id"])
    await planner_service.append_planner_message(
        project_id=project["_id"],
        role=data.role,
        content=data.content,
        message_type=data.messageType,
        session_id=data.sessionId,
        thread_id=thread_id,
    )
    messages = await planner_service.list_planner_messages(project["_id"], thread_id=thread_id)
    return {"threadId": thread_id, "messages": list(reversed(messages))}


@router.get("/{slug}/planner/board")
async def get_planner_board(slug: str):
    project = await planner_service.get_project_by_slug(slug)
    board = await planner_service.ensure_main_board(project["_id"])
    tasks = await planner_service.list_tasks(board["_id"])
    return {"board": board, "tasks": tasks}


@router.post("/{slug}/planner/tasks")
async def create_planner_task(slug: str, data: PlannerTaskRequest):
    project = await planner_service.get_project_by_slug(slug)
    board = await planner_service.ensure_main_board(project["_id"], session_id=data.sessionId)
    task = await planner_service.create_task(
        board_id=board["_id"],
        project_id=project["_id"],
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
    board = await planner_service.ensure_main_board(project["_id"])
    await planner_service.update_task(task_id, **data.model_dump())
    await planner_service.sync_planner_files(project, board)
    tasks = await planner_service.list_tasks(board["_id"])
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
    approvals = await convex.query("approvals:listByProject", {"projectId": project["_id"], "limit": limit}) or []
    return {"approvals": approvals}


@router.post("/{slug}/approvals")
async def create_project_approval(slug: str, data: ApprovalCreateRequest):
    project = await planner_service.get_project_by_slug(slug)
    approval_id = await convex.mutation(
        "approvals:create",
        {
            "projectId": project["_id"],
            "taskId": data.taskId,
            "agentSessionId": data.agentSessionId,
            "approvalType": data.approvalType,
            "status": data.status,
            "requestedByRole": data.requestedByRole,
            "grantedByUserId": data.grantedByUserId,
        },
    )
    return {"approvalId": approval_id}


@router.post("/{slug}/approvals/{approval_id}/resolve")
async def resolve_project_approval(slug: str, approval_id: str, data: ApprovalResolveRequest):
    _project = await planner_service.get_project_by_slug(slug)
    await convex.mutation(
        "approvals:resolve",
        {
            "approvalId": approval_id,
            "status": data.status,
            "grantedByUserId": data.grantedByUserId,
        },
    )
    return {"approvalId": approval_id, "status": data.status}
