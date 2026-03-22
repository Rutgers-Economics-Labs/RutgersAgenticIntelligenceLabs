import asyncio
import time
from typing import Union
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import hydration_worker

router = APIRouter(prefix="/jobs", tags=["jobs"])


class TriggerJobRequest(BaseModel):
    pipeline_slug: str
    env_overrides: dict[str, str] = {}


async def _trigger_job(pipeline_slug: str) -> dict:
    """
    Core job-creation logic, callable from both the HTTP router and the agent.
    Fires hydration as a plain asyncio task (no BackgroundTasks dependency).
    Returns {jobId, status}.
    """
    pipeline = await convex.query("configs:getPipeline", {"slug": pipeline_slug})
    if not pipeline:
        raise ValueError(f"Pipeline '{pipeline_slug}' not found")

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

    result = await convex.mutation("jobs:create", {
        "pipelineConfigId": pipeline["_id"],
        "pipelineSlug": pipeline_slug,
        "status": "queued",
        "triggeredBy": "agent",
        "createdAt": int(time.time() * 1000),
        "stepResults": [],
    })
    job_id = result["jobId"]

    asyncio.create_task(
        hydration_worker.run(job_id, pipeline["content"], api_configs, onto_configs)
    )
    return {"jobId": job_id, "status": "queued"}


@router.post("")
async def trigger_job(req: TriggerJobRequest, background_tasks: BackgroundTasks):
    pipeline = await convex.query("configs:getPipeline", {"slug": req.pipeline_slug})
    if not pipeline:
        raise HTTPException(404, detail=f"Pipeline '{req.pipeline_slug}' not found")

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

    result = await convex.mutation("jobs:create", {
        "pipelineConfigId": pipeline["_id"],
        "pipelineSlug": req.pipeline_slug,
        "status": "queued",
        "triggeredBy": "api",
        "createdAt": int(time.time() * 1000),
        "stepResults": [],
    })
    job_id = result["jobId"]

    background_tasks.add_task(
        hydration_worker.run,
        job_id,
        pipeline["content"],
        api_configs,
        onto_configs,
    )

    return {"jobId": job_id, "status": "queued"}


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
