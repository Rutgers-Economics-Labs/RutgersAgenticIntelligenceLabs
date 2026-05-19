from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_env_files() -> tuple[Path, ...] | None:
    """Load env in order; later files override earlier.

    Repo root `.env` is loaded first, then `packages/api/.env`.
    Later files override the same variable name.
    """
    _core = Path(__file__).resolve().parent
    api_root = _core.parents[1]  # packages/api
    repo_root = _core.parents[3]  # repo root (parent of packages/)
    files: list[Path] = []
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

    # Keep CONVEX_URL and NEXT_PUBLIC_CONVEX_URL separate so server-side and future
    # client-side consumers can evolve independently.
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
    # Examples: "claude-sonnet-4-6", "gemini/gemini-flash-latest", "openrouter/anthropic/claude-3.5-sonnet", "gpt-4o"
    ai_model: str = "claude-opus-4-6"
    ai_temperature: float = 0.3
    ai_max_tokens: int = 8192
    embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = Field(default="", validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key"))
    openrouter_api_key: str = ""

    # GitHub App
    github_app_id: str = Field(default="", validation_alias="GITHUB_APP_ID")
    github_app_private_key_raw: str = Field(default="", validation_alias="GITHUB_APP_PRIVATE_KEY")
    github_webhook_secret: str = Field(default="", validation_alias="GITHUB_WEBHOOK_SECRET")
    github_app_org: str = Field(default="Rutgers-Economics-Labs", validation_alias="GITHUB_APP_ORG")

    @property
    def github_app_private_key(self) -> str:
        """Clean and unescape the RSA private key."""
        raw = self.github_app_private_key_raw or ""
        # Remove surrounding quotes if they exist
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        elif raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        # Unescape literal \n into actual newlines
        return raw.replace("\\n", "\n")

    # Jules runner
    jules_api_key: str = Field(default="", validation_alias="JULES_API_KEY")
    jules_api_url: str = Field(
        default="https://jules.googleapis.com/v1alpha",
        validation_alias="JULES_API_URL",
    )
    jules_source: str = Field(
        default="sources/github/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs",
        validation_alias="JULES_SOURCE",
    )
    claude_code_command: str = Field(default="claude", validation_alias="CLAUDE_CODE_COMMAND")
    gemini_cli_command: str = Field(default="gemini", validation_alias="GEMINI_CLI_COMMAND")
    cursor_cli_command: str = Field(default="agent", validation_alias="CURSOR_CLI_COMMAND")
    codex_cli_command: str = Field(default="codex", validation_alias="CODEX_CLI_COMMAND")
    copilot_cli_command: str = Field(default="gh copilot suggest", validation_alias="COPILOT_CLI_COMMAND")

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

    # Project secret encryption
    secret_encryption_key: str = Field(default="", validation_alias="RAIL_SECRET_FERNET_KEY")


settings = Settings()
