import time
import hashlib
from typing import Optional, Dict, Any
from app.services.convex_client import convex

class ArtifactRegistryService:
    def generate_rev(self, job_id: str, timestamp: float) -> str:
        """Generate a unique rev hash based on job_id and timestamp."""
        data = f"{job_id}-{timestamp}".encode('utf-8')
        return hashlib.sha256(data).hexdigest()[:16]

    async def register_rev(self, job_id: str, project_id: str, s3_path: str) -> str:
        """Register a new artifact revision."""
        ts = time.time()
        rev = self.generate_rev(job_id, ts)

        await convex.mutation(
            "artifacts:create",
            {
                "rev": rev,
                "projectId": project_id,
                "s3_path": s3_path,
                "timestamp": int(ts * 1000)
            }
        )
        return rev

    async def get_rev(self, rev: str) -> Optional[Dict[str, Any]]:
        """Get an artifact revision by rev hash."""
        return await convex.query("artifacts:getByRev", {"rev": rev})

artifact_registry = ArtifactRegistryService()
