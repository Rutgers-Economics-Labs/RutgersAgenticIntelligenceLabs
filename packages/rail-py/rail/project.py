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

    def __repr__(self):
        mode = "cloud" if hasattr(self._backend, "base_url") else "local"
        return f"Project(slug={self.slug!r}, mode={mode!r})"