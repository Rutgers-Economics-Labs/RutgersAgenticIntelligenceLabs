from __future__ import annotations

import httpx
from typing import Any

class CloudClient:
    def __init__(self, base_url: str, api_key: str = "", timeout_seconds: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout_seconds)

    def get(self, path: str, **params) -> Any:
        with self._client() as client:
            r = client.get(f"{self.base_url}{path}", params=params, headers=self.headers)
            r.raise_for_status()
            return r.json()

    def post(self, path: str, data: dict) -> Any:
        with self._client() as client:
            r = client.post(f"{self.base_url}{path}", json=data, headers=self.headers)
            r.raise_for_status()
            return r.json()

    def hydrate(self, pipeline_slug: str) -> dict:
        return self.post("/jobs", {"pipeline_slug": pipeline_slug})

    def reconcile_project(self, project_slug: str) -> dict:
        return self.post(f"/projects/{project_slug}/command-center/reconcile", {})

    def query_sql(self, sql: str) -> dict:
        return self.post("/sql", {"query": sql})

    def get_classes(self) -> list[dict]:
        return self.get("/ontology/classes")

    def get_instances(self, class_name: str, limit: int = 100) -> dict:
        return self.get(f"/ontology/classes/{class_name}/instances", limit=limit)

    def search_entities(self, q: str) -> list[dict]:
        return self.get("/ontology/search", q=q)

    def get_series(self, series_id: str) -> list[dict]:
        return self.get(f"/ontology/series/{series_id}/data")

    def run_analysis(self, plugin_slug: str, config: dict = {}) -> dict:
        return self.post(f"/analysis/plugins/{plugin_slug}/run", {"config": config})

    def execute_python(self, code: str, timeout: int = 60) -> dict:
        return self.post("/execute", {"code": code, "timeout": timeout})

    def search_registry(self, q: str, provider: str | None = None, geography: str | None = None) -> list[dict]:
        params = {"query": q}
        if provider: params["provider"] = provider
        if geography: params["geography"] = geography
        return self.get("/registry/search", **params)

    def discover_templates(self, q: str, tags: list[str] | None = None) -> list[dict]:
        params = {"query": q}
        if tags: params["tags"] = ",".join(tags)
        return self.get("/connectors/templates", **params)

    def list_secrets(self, project_slug: str) -> list[dict]:
        return self.get(f"/projects/{project_slug}/settings/secrets")

    def set_secret(self, project_slug: str, key: str, value: str) -> dict:
        return self.post(f"/projects/{project_slug}/settings/secrets", {"keyName": key, "plaintextValue": value})

    def delete_secret(self, project_slug: str, key: str) -> dict:
        with self._client() as client:
            r = client.delete(f"{self.base_url}/projects/{project_slug}/settings/secrets/{key}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    def get_integrity_status(self, project_slug: str) -> dict:
        return self.get(f"/projects/{project_slug}/integrity")

    def get_integrity_assumptions(self, project_slug: str) -> list[dict]:
        res = self.get(f"/projects/{project_slug}/integrity/assumptions")
        return res.get("assumptions", [])

    def get_integrity_sources(self, project_slug: str) -> list[dict]:
        res = self.get(f"/projects/{project_slug}/integrity/sources")
        return res.get("sources", [])

    def get_integrity_claims(self, project_slug: str) -> list[dict]:
        res = self.get(f"/projects/{project_slug}/integrity/claims")
        return res.get("claims", [])

    def get_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        return self.post(f"/projects/{project_slug}/integrity/rerun-plan", {"assumptionKey": assumption_key})

    def apply_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        return self.post(f"/projects/{project_slug}/integrity/rerun-plan/apply", {"assumptionKey": assumption_key})

    def get_project_state(self, project_slug: str) -> dict:
        return self.get(f"/projects/{project_slug}/context")

    def get_work_order(self, project_slug: str, work_order_id: str) -> dict:
        return self.get(f"/projects/{project_slug}/work-orders/{work_order_id}")

    def submit_session_result(self, project_slug: str, session_id: str, result: dict) -> dict:
        return self.post(f"/projects/{project_slug}/sessions/{session_id}/result", result)

    def ask_question(self, project_slug: str, session_id: str, question: str) -> dict:
        return self.post(f"/projects/{project_slug}/sessions/{session_id}/ask", {"question": question})
