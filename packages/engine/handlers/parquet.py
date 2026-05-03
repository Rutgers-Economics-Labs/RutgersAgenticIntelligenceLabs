"""
Source handler for Parquet files (local path, URL download, or S3 key).

YAML config shape:
    type: parquet
    name: my_data
    path: data/output.parquet           # local file
    # or
    url: https://example.com/data.parquet  # downloaded and cached
    # or
    storage_key: jobs/123/result.parquet   # S3 or local artifact key
    fields: [...]                        # optional column mapping
"""
import os
from pathlib import Path

import pandas as pd


def fetch(spec: dict, **kwargs) -> pd.DataFrame:
    path = _resolve_path(spec)
    df = pd.read_parquet(path)
    return df


def _resolve_path(spec: dict) -> str:
    if "path" in spec:
        return spec["path"]

    if "url" in spec:
        return _download(spec["url"])

    if "storage_key" in spec:
        # Supports local artifact paths and S3 keys (s3://bucket/key)
        key = spec["storage_key"]
        if key.startswith("s3://"):
            return _download_s3(key)
        # Local artifact path written by storage_service
        if Path(key).exists():
            return key
        # Fall back to rail_cache_dir
        cache_dir = Path(os.environ.get("RAIL_CACHE_DIR", "cache"))
        candidate = cache_dir / Path(key).name
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(f"Parquet storage_key not found: {key}")

    raise ValueError("parquet source requires one of: path, url, storage_key")


def _download(url: str) -> str:
    import hashlib
    import requests

    cache_dir = Path(os.environ.get("RAIL_CACHE_DIR", "cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()
    dest = cache_dir / f"{key}.parquet"
    if dest.exists():
        return str(dest)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return str(dest)


def _download_s3(s3_url: str) -> str:
    try:
        import boto3
    except ImportError:
        raise ImportError("boto3 is required for S3 parquet sources: pip install boto3")

    import re
    m = re.match(r"s3://([^/]+)/(.+)", s3_url)
    if not m:
        raise ValueError(f"Invalid S3 URL: {s3_url}")
    bucket, key = m.group(1), m.group(2)

    cache_dir = Path(os.environ.get("RAIL_CACHE_DIR", "cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / Path(key).name

    s3 = boto3.client("s3")
    s3.download_file(bucket, key, str(dest))
    return str(dest)
