from __future__ import annotations

class Project:
    def __init__(self, slug: str, backend):
        self.slug = slug
        self._backend = backend

    def hydrate(self, pipeline_slug: str | None = None) -> dict:
        """Trigger hydration. Uses the project's default pipeline if not specified."""
        return self._backend.hydrate(pipeline_slug or self.slug)

    def query(self, sql: str) -> "pd.DataFrame":
        import pandas as pd
        result = self._backend.query_sql(sql)
        return pd.DataFrame(result["rows"], columns=result["columns"])

    def classes(self) -> list[dict]:
        return self._backend.get_classes()

    def entities(self, class_name: str, limit: int = 100) -> "pd.DataFrame":
        import pandas as pd
        result = self._backend.get_instances(class_name, limit=limit)
        return pd.DataFrame(result.get("items", []))

    def search(self, q: str) -> list[dict]:
        return self._backend.search_entities(q)

    def series(self, series_id: str) -> "pd.DataFrame":
        import pandas as pd
        data = self._backend.get_series(series_id)
        return pd.DataFrame(data)

    def execute(self, code: str, timeout: int = 60) -> dict:
        return self._backend.execute_python(code, timeout=timeout)

    def run_analysis(self, plugin_slug: str, **kwargs) -> dict:
        return self._backend.run_analysis(plugin_slug, config=kwargs)

    def discover(self, q: str, tags: list[str] | None = None) -> list[dict]:
        """Search for connector templates (Census, FRED, etc)."""
        return self._backend.discover_templates(q, tags=tags)

    def search_registry(self, q: str, provider: str | None = None, geography: str | None = None) -> list[dict]:
        """Search the platform's data catalog."""
        return self._backend.search_registry(q, provider=provider, geography=geography)

    def list_secrets(self) -> list[dict]:
        return self._backend.list_secrets(self.slug)

    def set_secret(self, key: str, value: str) -> dict:
        return self._backend.set_secret(self.slug, key, value)

    def delete_secret(self, key: str) -> dict:
        return self._backend.delete_secret(self.slug, key)

    @property
    def agent(self) -> "AgentClient":
        """Access the research agent for this project."""
        from rail.agent import AgentClient
        if not hasattr(self._backend, "base_url"):
            raise RuntimeError("Agent access requires cloud mode (rail.connect())")
        return AgentClient(
            base_url=self._backend.base_url,
            project_slug=self.slug,
            api_key=getattr(self._backend, "api_key", ""),
        )

    def ontology(self) -> "OntologyView":
        """Access the owlready2 ontology directly (local mode or local onto.db path)."""
        from rail.ontology import OntologyView
        if hasattr(self._backend, "artifact_db_path"):
            # Local mode — use manifest-driven .ontology/ path
            db_path = str(self._backend.artifact_db_path)
        else:
            raise RuntimeError("ontology() requires local mode or a local onto.db path")
        return OntologyView(db_path)

    def __repr__(self):
        mode = "cloud" if hasattr(self._backend, "base_url") else "local"
        return f"Project(slug={self.slug!r}, mode={mode!r})"
