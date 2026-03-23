"""
Thin async wrapper around Convex's HTTP API for server-side mutations/queries.
The deploy key is server-side only — never sent to the browser.
"""
import httpx
from app.core.config import settings


class ConvexBackendConfigurationError(RuntimeError):
    """Raised when CONVEX_URL / CONVEX_DEPLOY_KEY are missing so routes can return 503."""


class ConvexClient:
    """Reads URL/key from settings on each call so merged CONVEX_URL + NEXT_PUBLIC_* stays current."""

    @property
    def base_url(self) -> str:
        return settings.convex_url.strip().rstrip("/")

    @property
    def deploy_key(self) -> str:
        return settings.convex_deploy_key.strip()

    def _require_backend_convex(self) -> None:
        if not self.base_url or not self.base_url.startswith(("http://", "https://")):
            raise ConvexBackendConfigurationError(
                "Convex URL is not configured. Set CONVEX_URL in packages/api/.env, or ensure "
                "NEXT_PUBLIC_CONVEX_URL is set in packages/web/.env.local (same value as the Next app)."
            )
        if not self.deploy_key:
            raise ConvexBackendConfigurationError(
                "CONVEX_DEPLOY_KEY is not set. Add it to the repo root `.env` or `packages/api/.env` "
                "(Convex → Settings → Deploy keys). Server-only — never NEXT_PUBLIC_. "
                "Remove any empty CONVEX_DEPLOY_KEY= line from `packages/web/.env.local`."
            )

    @property
    def _headers(self):
        return {"Authorization": f"Convex {self.deploy_key}"}

    async def mutation(self, fn_path: str, args: dict):
        """Call a Convex mutation, e.g. mutation('jobs:create', {...})"""
        self._require_backend_convex()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/mutation",
                json={"path": fn_path, "args": args},
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", resp.json())

    async def query(self, fn_path: str, args: dict):
        """Call a Convex query, e.g. query('jobs:get', {'jobId': '...'})"""
        self._require_backend_convex()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/query",
                json={"path": fn_path, "args": args},
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", resp.json())


# Module-level singleton — created once at import time
convex = ConvexClient()
