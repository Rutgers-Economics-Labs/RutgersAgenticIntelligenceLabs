from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Convex
    convex_url: str = ""
    convex_deploy_key: str = ""

    # Engine
    engine_root: Path = Path(__file__).parents[3] / "engine"
    rail_cache_dir: Path = Path("/tmp/rail_cache")
    storage_backend: str = "local"   # "local" | "s3"

    # S3 / R2 (only needed when storage_backend="s3")
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # FRED
    fred_api_key: str = ""

    # Server
    api_cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
