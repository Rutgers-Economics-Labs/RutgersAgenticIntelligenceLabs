# Work Order 33 — S3 / R2 Artifact Storage

## Layer
8 — Infrastructure and Scale

## Goal
Store large artifacts (ontology snapshots, DuckDB files, exported figures, analysis bundles) in S3-compatible object storage (AWS S3 or Cloudflare R2) instead of the local filesystem, enabling multi-replica deployments and persistent storage across restarts.

## Steps

### 1. Storage config
Add to `packages/api/app/core/config.py`:
```python
storage_backend: str = "local"          # "local" | "s3"
s3_bucket: str = ""
s3_region: str = "us-east-1"
s3_endpoint_url: str = ""               # for R2: https://<account>.r2.cloudflarestorage.com
aws_access_key_id: str = ""
aws_secret_access_key: str = ""
s3_prefix: str = "rail/"                # key prefix for all objects
```

### 2. Storage abstraction
File: `packages/api/app/services/storage_backend.py`

```python
class StorageBackend(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes, return public URL or presigned URL."""

    async def download(self, key: str) -> bytes:
        """Download bytes by key."""

    async def exists(self, key: str) -> bool:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def list_keys(self, prefix: str) -> list[str]:
        ...

class LocalStorageBackend:
    """Stores files in the local filesystem under a base path."""

class S3StorageBackend:
    """Uses boto3 async (aioboto3) to read/write S3-compatible storage."""
```

Factory function:
```python
def get_storage() -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3StorageBackend(...)
    return LocalStorageBackend(...)
```

### 3. Ontology snapshot uploads
In `hydration_worker.py`, after hydration completes and DuckDB export is done:
1. Upload the `.owl` file to `s3_prefix/ontologies/{slug}/{timestamp}.owl`
2. Upload `onto.duckdb` to `s3_prefix/duckdb/{timestamp}.duckdb`
3. Store the S3 key in the Convex `jobs` record

On startup, if no local `.owl` file exists, download the latest snapshot from S3.

### 4. Export artifact uploads
In `export_service.py`, when generating a bundle (WO-27):
- Upload the `.zip` to `s3_prefix/exports/{workspace_id}/{run_id}.zip`
- Return a presigned download URL valid for 1 hour

### 5. Environment variable documentation
Document in `specs/api.md` (and set in root `.env`):
```
STORAGE_BACKEND=local        # or "s3"
S3_BUCKET=my-rail-bucket
S3_REGION=us-east-1
S3_ENDPOINT_URL=             # leave blank for AWS, set for R2
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_PREFIX=rail/
```

### 6. Railway deployment config
Update `railway.toml` (or add deployment notes) to mount a persistent volume for local storage or configure S3 env vars for production.

### 7. New dependency
Add `aioboto3>=12.0` to `packages/api/pyproject.toml`.

## Affected Files
- `packages/api/app/core/config.py` — add storage settings
- `packages/api/app/services/storage_backend.py` — **create**
- `packages/api/app/services/hydration_worker.py` — upload artifacts post-hydration
- `packages/api/app/services/export_service.py` — upload bundles (WO-27)
- `packages/api/pyproject.toml` — add `aioboto3`
- `specs/api.md` — document storage env vars
- `specs/architecture.md` — document storage backend design decision

## Acceptance Criteria
- [ ] `STORAGE_BACKEND=local` works with no S3 credentials (existing behavior)
- [ ] `STORAGE_BACKEND=s3` uploads `.owl` and `.duckdb` after hydration
- [ ] On container restart with S3 backend, ontology is restored from latest S3 snapshot
- [ ] Export bundle returns a presigned URL that downloads the `.zip`
- [ ] R2-compatible endpoint URL works (tested with Cloudflare R2)
