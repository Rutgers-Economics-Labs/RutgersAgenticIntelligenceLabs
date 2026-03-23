"""
Thin async wrapper around Convex's HTTP API for server-side mutations/queries.
The deploy key is server-side only — never sent to the browser.
"""
import httpx
from app.core.config import settings


class ConvexClient:
    def __init__(self):
        self.base_url = settings.convex_url.strip().rstrip("/")
        self.deploy_key = settings.convex_deploy_key.strip()

    @property
    def _headers(self):
        return {"Authorization": f"Convex {self.deploy_key}"}

    async def mutation(self, fn_path: str, args: dict):
        """Call a Convex mutation, e.g. mutation('jobs:create', {...})"""
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
