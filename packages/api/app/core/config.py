from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_env_files() -> tuple[Path, ...] | None:
    """Load env in order; later files override earlier.

    Web `.env.local` is loaded first, then repo root `.env`, then `packages/api/.env`.
    Later files override the same variable name. A blank `CONVEX_DEPLOY_KEY=` in
    `.env.local` cannot wipe a real key from the root `.env`.
    `CONVEX_URL` and `NEXT_PUBLIC_CONVEX_URL` are separate settings fields so an empty
    `CONVEX_URL=` in root does not erase a valid `NEXT_PUBLIC_CONVEX_URL` from the web env.
    """
    _core = Path(__file__).resolve().parent
    api_root = _core.parents[1]  # packages/api
    repo_root = _core.parents[3]  # repo root (parent of packages/)
    packages_dir = _core.parents[2]
    files: list[Path] = []
    web_local = packages_dir / "web" / ".env.local"
    if web_local.is_file():
        files.append(web_local)
    root_env = repo_root / ".env"
    if root_env.is_file():
        files.append(root_env)
    api_env = api_root / ".env"
    if api_env.is_file():
        files.append(api_env)
    return tuple(files) if files else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Convex — keep CONVEX_URL and NEXT_PUBLIC_CONVEX_URL as separate env keys so a blank
    # `CONVEX_URL=` in root `.env` does not wipe a valid NEXT_PUBLIC_* from `web/.env.local`
    # (both previously mapped to one field; later files won and produced an empty URL → httpx 500).
    convex_url_env: str = Field(default="", validation_alias="CONVEX_URL")
    next_public_convex_url: str = Field(
        default="",
        validation_alias="NEXT_PUBLIC_CONVEX_URL",
    )
    convex_deploy_key: str = ""

    @property
    def convex_url(self) -> str:
        raw = (self.convex_url_env or "").strip() or (
            self.next_public_convex_url or ""
        ).strip()
        if not raw:
            return ""
        if not raw.startswith(("http://", "https://")):
            raw = f"https://{raw.lstrip('/')}"
        return raw

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

    # AI / LLM (provider-agnostic via LiteLLM)
    # Examples: "claude-sonnet-4-6", "gemini/gemini-2.0-flash", "openrouter/anthropic/claude-3.5-sonnet", "gpt-4o"
    ai_model: str = "gemini/gemini-3-flash-preview"
    ai_temperature: float = 0.3
    ai_max_tokens: int = 8192
    embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""

    # Server
    # In production set API_CORS_ORIGINS="https://your-app.vercel.app,https://custom-domain.com"
    # Include 127.0.0.1: browsers treat localhost vs 127.0.0.1 as different origins for CORS.
    api_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    # Any dev port (e.g. 3001 when 3000 is busy). Set to empty string to disable.
    api_cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # Python execution (POST /api/v1/execute, agent execute_python)
    # RAIL_EXECUTE_ENABLED=false disables those entrypoints (403).
    # RAIL_EXECUTE_MODE=subprocess runs user code in a child process (see engine/code_subprocess_cli.py).
    # RAIL_EXECUTE_DOCKER_IMAGE=myimage:tag runs that subprocess inside Docker on Linux/macOS (--network none).
    execute_python_enabled: bool = Field(default=True, validation_alias="RAIL_EXECUTE_ENABLED")
    execute_python_mode: Literal["inproc", "subprocess"] = Field(
        default="inproc",
        validation_alias="RAIL_EXECUTE_MODE",
    )
    execute_docker_image: str = Field(default="", validation_alias="RAIL_EXECUTE_DOCKER_IMAGE")


settings = Settings()
