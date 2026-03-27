import asyncio
import time
from typing import Union
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import hydration_worker
from app.services.execution_manager import execution_manager
from app.services.pipeline_validate import ensure_pipeline_ready, PipelineValidationFailed

router = APIRouter(prefix="/jobs", tags=["jobs"])


class TriggerJobRequest(BaseModel):
    pipeline_slug: str
    project_id: str | None = None
    env_overrides: dict[str, str] = {}


async def _trigger_job(pipeline_slug: str, project_id: str | None = None) -> dict:
    """
    Core job-creation logic, callable from both the HTTP router and the agent.
    Fires hydration as a plain asyncio task (no BackgroundTasks dependency).
    Returns {jobId, status}.
    """
    pipeline = await convex.query("configs:getPipeline", {"slug": pipeline_slug})
    if not pipeline:
        raise ValueError(f"Pipeline '{pipeline_slug}' not found")

    await ensure_pipeline_ready(convex, pipeline)

    api_slugs = pipeline.get("referencedApiSlugs", [])
    api_configs: dict[str, str] = {}
    for slug in api_slugs:
        cfg = await convex.query("configs:getApi", {"slug": slug})
        if cfg:
            api_configs[slug] = cfg["content"]

    pipeline_spec = pipeline.get("parsedSpec", {})
    onto_ref = pipeline_spec.get("ontology", "core")
    onto_configs: dict[str, str] = {}
    onto_cfg = await convex.query("configs:getOntology", {"slug": onto_ref})
    if onto_cfg:
        onto_configs[onto_ref] = onto_cfg["content"]

    mutation_args: dict = {
        "pipelineConfigId": pipeline["_id"],
        "pipelineSlug": pipeline_slug,
        "status": "queued",
        "triggeredBy": "agent",
        "createdAt": int(time.time() * 1000),
        "stepResults": [],
    }
    if project_id:
        mutation_args["projectId"] = project_id

    result = await convex.mutation("jobs:create", mutation_args)
    job_id = result["jobId"]

    asyncio.create_task(
        hydration_worker.run(job_id, pipeline["content"], api_configs, onto_configs)
    )
    return {"jobId": job_id, "status": "queued"}


@router.post("")
async def trigger_job(req: TriggerJobRequest, background_tasks: BackgroundTasks):
    from pathlib import Path
    import yaml

    # 1. Fetch Pipeline
    pipeline = await convex.query("configs:getPipeline", {"slug": req.pipeline_slug})
    
    if not pipeline:
        # FALLBACK: Try local engine config
        local_path = Path("../engine/configs/pipelines") / f"{req.pipeline_slug}.yaml"
        if local_path.exists():
            print(f"📄 [jobs] Convex query failed. Falling back to local pipeline: {local_path}")
            content = local_path.read_text()
            spec = yaml.safe_load(content)
            pipeline = {
                "_id": f"local_{req.pipeline_slug}",
                "slug": req.pipeline_slug,
                "content": content,
                "parsedSpec": spec,
                "referencedApiSlugs": spec.get("apis", []) # Basic estimation
            }
        else:
            raise HTTPException(404, detail=f"Pipeline '{req.pipeline_slug}' not found (Convex & Local)")
    else:
        # If found in Convex, ensure it's valid according to current rules
        try:
            await ensure_pipeline_ready(convex, pipeline)
        except PipelineValidationFailed as e:
            raise HTTPException(422, detail=e.errors)

    # 2. Fetch API Configs

    api_slugs = pipeline.get("referencedApiSlugs", [])
    api_configs: dict[str, str] = {}
    for slug in api_slugs:
        cfg = await convex.query("configs:getApi", {"slug": slug})
        if cfg:
            api_configs[slug] = cfg["content"]
        else:
            # FALLBACK: Try local engine API config
            api_path = Path("../engine/configs/apis") / f"{slug}.yaml"
            if api_path.exists():
                api_configs[slug] = api_path.read_text()

    # 3. Resolve Ontology
    pipeline_spec = pipeline.get("parsedSpec", {})
    onto_ref = pipeline_spec.get("ontology", "core")
    # Strip path from onto_ref if it was a file path
    if "/" in onto_ref:
        onto_ref = Path(onto_ref).stem

    onto_configs: dict[str, str] = {}
    onto_cfg = await convex.query("configs:getOntology", {"slug": onto_ref})
    if onto_cfg:
        onto_configs[onto_ref] = onto_cfg["content"]
    else:
        # FALLBACK: Try local engine ontology config
        onto_path = Path("../engine/configs/ontology") / f"{onto_ref}.yaml"
        if onto_path.exists():
            onto_configs[onto_ref] = onto_path.read_text()

    # 4. Trigger Job record
    result = await convex.mutation("jobs:create", {
        "pipelineConfigId": pipeline["_id"],
        "pipelineSlug": req.pipeline_slug,
        "status": "queued",
        "triggeredBy": "api",
        "createdAt": int(time.time() * 1000),
        "stepResults": [],
    })
    job_id = result.get("jobId") if isinstance(result, dict) else f"local_job_{int(time.time())}"

    background_tasks.add_task(
        hydration_worker.run,
        job_id,
        pipeline["content"],
        api_configs,
        onto_configs,
    )

    return {"jobId": job_id, "status": "queued", "source": "local_fallback" if "local_" in pipeline["_id"] else "convex"}


@router.get("")
async def list_jobs(status: Union[str, None] = None, limit: int = 50):
    return await convex.query("jobs:list", {"status": status, "limit": limit})


@router.get("/{job_id}")
async def get_job(job_id: str):
    result = await convex.query("jobs:get", {"jobId": job_id})
    if not result:
        raise HTTPException(404, detail=f"Job '{job_id}' not found")
    return result


@router.get("/{job_id}/logs")
async def get_job_logs(job_id: str, after_seq: int = 0, limit: int = 200):
    return await convex.query("jobs:getLogs", {
        "jobId": job_id,
        "afterSeq": after_seq,
        "limit": limit,
    })


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    # Mark as cancelled in Convex — the worker checks this flag on next iteration
    return await convex.mutation("jobs:updateJob", {
        "jobId": job_id,
        "status": "cancelled",
        "finishedAt": int(time.time() * 1000),
    })


@router.delete("/executions/{job_id}/interrupt")
async def interrupt_execution(job_id: str):
    """Interrupt a running code or SQL execution."""
    success = await execution_manager.interrupt_job(job_id)
    if not success:
        raise HTTPException(404, detail=f"Active execution job '{job_id}' not found")
    return {"status": "cancelled", "jobId": job_id}
