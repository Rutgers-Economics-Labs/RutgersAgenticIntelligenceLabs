"""
Manages artifact files attached to hydration jobs via the rail_client SDK.
Artifacts are stored using the existing storage_service and recorded in Convex.
"""
import time
import tempfile
from pathlib import Path

from app.services.storage_service import storage
from app.services.convex_client import convex

MAX_INLINE_BYTES = 64 * 1024  # 64 KB — text artifacts below this are stored inline in Convex


async def save_artifact(
    job_id: str,
    name: str,
    artifact_type: str,
    content_bytes: bytes,
    mime_type: str,
) -> dict:
    """
    Persist an artifact file and record metadata in Convex.
    Returns the Convex artifact record dict.
    """
    # Write to a temp file so storage_service can upload it
    suffix = Path(name).suffix or ""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content_bytes)
        tmp_path = Path(tmp.name)

    try:
        storage_key = await storage.upload(job_id, f"artifacts/{name}", tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    inline_content: str | None = None
    if artifact_type == "text" and len(content_bytes) <= MAX_INLINE_BYTES:
        inline_content = content_bytes.decode("utf-8", errors="replace")

    artifact_doc = {
        "jobId": job_id,
        "name": name,
        "artifactType": artifact_type,
        "storageKey": storage_key,
        "mimeType": mime_type,
        "sizeBytes": len(content_bytes),
        "createdAt": int(time.time() * 1000),
    }
    if inline_content is not None:
        artifact_doc["inlineContent"] = inline_content

    artifact_id = await convex.mutation("artifacts:create", artifact_doc)
    return {**artifact_doc, "_id": artifact_id}


async def list_artifacts(job_id: str) -> list:
    result = await convex.query("artifacts:listByJob", {"jobId": job_id})
    return result or []


async def get_artifact_bytes(storage_key: str) -> bytes:
    """Download artifact bytes from storage."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await storage.download(storage_key, tmp_path)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)
