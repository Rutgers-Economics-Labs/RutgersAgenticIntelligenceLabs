"""
Manages the lifecycle of onto.db quadstore artifacts.

In local mode: files are kept on disk; upload/download are no-ops.
In S3 mode: files are uploaded to S3 after hydration and downloaded before queries.
"""
import shutil
from pathlib import Path

from typing import Union
from app.core.config import settings


class StorageService:
    def __init__(self):
        self.backend = settings.storage_backend
        self._local_root = Path("/tmp/rail_artifacts")
        self._local_root.mkdir(parents=True, exist_ok=True)

    async def upload(self, job_id: str, filename: str, local_path: Union[str, Path]) -> str:
        """
        Upload a file produced by hydration. Returns the storage key.
        In local mode, copies the file to a stable local location and returns that path.
        """
        local_path = Path(local_path)
        if self.backend == "local":
            dest = self._local_root / job_id / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)
            return str(dest)

        # S3 mode
        async with session.client(
            "s3",
            region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ) as s3:
            await s3.upload_file(str(local_path), settings.s3_bucket, key)
        return key

    async def upload_input(self, filename: str, content: bytes) -> str:
        """
        Upload a file provided by a user to the inputs/ directory.
        Returns the storage key.
        """
        if self.backend == "local":
            dest = self._local_root / "inputs" / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(content)
            return str(dest)

        # S3 mode
        key = f"inputs/{filename}"
        import aioboto3
        import io
        session = aioboto3.Session()
        async with session.client(
            "s3",
            region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ) as s3:
            await s3.upload_fileobj(io.BytesIO(content), settings.s3_bucket, key)
        return key

    async def download(self, storage_key: str, dest_path: Union[str, Path]) -> Path:
        """
        Download a stored artifact to dest_path. Returns the dest path.
        In local mode, storage_key IS the local path; copies to dest_path.
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if self.backend == "local":
            shutil.copy2(storage_key, dest_path)
            return dest_path

        # S3 mode
        import aioboto3
        session = aioboto3.Session()
        async with session.client(
            "s3",
            region_name=settings.s3_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        ) as s3:
            await s3.download_file(settings.s3_bucket, storage_key, str(dest_path))
        return dest_path


storage = StorageService()
