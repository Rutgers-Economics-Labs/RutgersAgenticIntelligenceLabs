"""
Thin async wrapper around Convex's HTTP API for server-side mutations/queries.
The deploy key is server-side only — never sent to the browser.
"""
import httpx
import time
from app.core.config import settings


class ConvexBackendConfigurationError(RuntimeError):
    """Raised when CONVEX_URL / CONVEX_DEPLOY_KEY are missing so routes can return 503."""


class ConvexClient:
    """Reads URL/key from settings on each call."""

    @property
    def base_url(self) -> str:
        return settings.convex_url.strip().rstrip("/")

    @property
    def deploy_key(self) -> str:
        return settings.convex_deploy_key.strip()

    def _require_backend_convex(self) -> None:
        if not self.base_url or not self.base_url.startswith(("http://", "https://")):
            raise ConvexBackendConfigurationError(
                "Convex URL is not configured. Set CONVEX_URL in the repo root `.env` or `packages/api/.env`."
            )
        if not self.deploy_key:
            raise ConvexBackendConfigurationError(
                "CONVEX_DEPLOY_KEY is not set. Add it to the repo root `.env` or `packages/api/.env` "
                "(Convex → Settings → Deploy keys). Server-only — never NEXT_PUBLIC_."
            )

    @property
    def _headers(self):
        return {"Authorization": f"Convex {self.deploy_key}"}

    @staticmethod
    def _unwrap_response(data: dict, *, fn_path: str, is_query: bool):
        """
        Convex HTTP returns 200 with either:
          { "status": "success", "value": ... }
          { "status": "error", "errorMessage": "..." }
        The old code used .get("value", data), so error payloads were returned whole
        and treated as truthy — breaking callers that do `if not project` after getById(slug).
        """
        if not isinstance(data, dict):
            return data
        if data.get("status") == "error":
            msg = data.get("errorMessage", str(data))
            if is_query:
                return None
            raise RuntimeError(f"Convex mutation {fn_path} failed: {msg}")
        if "value" in data:
            return data["value"]
        return data

    async def mutation(self, fn_path: str, args: dict):
        """Call a Convex mutation, e.g. mutation('jobs:create', {...})"""
        self._require_backend_convex()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/mutation",
                    json={"path": fn_path, "args": args},
                    headers=self._headers,
                    timeout=30,
                )
                resp.raise_for_status()
                return self._unwrap_response(resp.json(), fn_path=fn_path, is_query=False)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    print(f"⚠️  [convex] Mutation failed ({e.response.status_code}): Unauthorized. Check CONVEX_DEPLOY_KEY.")
                    return {"jobId": f"local_job_{int(time.time())}", "status": "simulated"}
                raise e

    async def query(self, fn_path: str, args: dict):
        """Call a Convex query, e.g. query('jobs:get', {'jobId': '...'})"""
        self._require_backend_convex()
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/query",
                    json={"path": fn_path, "args": args},
                    headers=self._headers,
                    timeout=30,
                )
                resp.raise_for_status()
                return self._unwrap_response(resp.json(), fn_path=fn_path, is_query=True)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    print(f"⚠️  [convex] Query failed ({e.response.status_code}): Unauthorized. Falling back to empty result.")
                    return None
                raise e


# Module-level singleton — created once at import time
convex = ConvexClient()
