import asyncio
import logging
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass

from app.services.convex_client import convex

logger = logging.getLogger("rail.execution_manager")

@dataclass
class ActiveJob:
    job_id: str
    task: asyncio.Task
    process: Optional[asyncio.subprocess.Process] = None
    start_time: float = 0.0

class ExecutionManager:
    def __init__(self):
        self._active_jobs: Dict[str, ActiveJob] = {}

    def register_job(self, job_id: str, task: asyncio.Task, process: Optional[asyncio.subprocess.Process] = None):
        """Register a running job and its task/process for management and interruption."""
        self._active_jobs[job_id] = ActiveJob(
            job_id=job_id,
            task=task,
            process=process,
            start_time=time.time()
        )
        logger.info(f"Job {job_id} registered.")

    def update_process(self, job_id: str, process: asyncio.subprocess.Process):
        """Update the process handle for a job once it has started."""
        if job_id in self._active_jobs:
            self._active_jobs[job_id].process = process
            logger.info(f"Job {job_id} process handle updated (PID: {process.pid}).")

    def unregister_job(self, job_id: str):
        """Remove a job from the active registry once it completes."""
        if job_id in self._active_jobs:
            del self._active_jobs[job_id]
            logger.info(f"Job {job_id} unregistered.")

    async def interrupt_job(self, job_id: str) -> bool:
        """Interrupt a running job by killing its subprocess and cancelling its task."""
        job = self._active_jobs.get(job_id)
        if not job:
            logger.warning(f"Attempted to interrupt non-existent job {job_id}.")
            return False

        logger.info(f"Interrupting job {job_id}...")
        
        # 1. Kill the subprocess if it exists
        if job.process and job.process.returncode is None:
            try:
                job.process.terminate()
                # Wait briefly for it to exit gracefully
                try:
                    await asyncio.wait_for(job.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    job.process.kill()
                logger.info(f"Job {job_id} subprocess terminated.")
            except Exception as e:
                logger.error(f"Error killing process for job {job_id}: {e}")

        # 2. Cancel the asyncio task
        if not job.task.done():
            job.task.cancel()
            logger.info(f"Job {job_id} task cancelled.")

        # 3. Update Convex status
        await convex.mutation("executions:updateStatus", {
            "jobId": job_id,
            "status": "cancelled",
            "finishedAt": int(time.time() * 1000),
            "errorMessage": "Interrupted by user."
        })

        self.unregister_job(job_id)
        return True

    def is_running(self, job_id: str) -> bool:
        return job_id in self._active_jobs

# Global singleton
execution_manager = ExecutionManager()
