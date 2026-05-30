from __future__ import annotations

class Project:
    def __init__(self, slug: str, backend):
        self.slug = slug
        self._backend = backend

    def hydrate(self, pipeline_slug: str | None = None) -> dict:
        """Trigger hydration. Uses the project's default pipeline if not specified."""
        if hasattr(self._backend, "hydrate_project"):
            return self._backend.hydrate_project(self.slug, pipeline_slug)
        return self._backend.hydrate(pipeline_slug)

    def reconcile(self) -> dict:
        """Reconcile repo-backed planner/session/control-plane state."""
        if hasattr(self._backend, "reconcile_project"):
            return self._backend.reconcile_project(self.slug)
        if hasattr(self._backend, "reconcile"):
            return self._backend.reconcile()
        raise RuntimeError("This backend does not support reconcile()")

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

    def integrity_status(self) -> dict:
        """Fetch the full integrity state of the project."""
        return self._backend.get_integrity_status(self.slug)

    def integrity_assumptions(self) -> list[dict]:
        """Fetch recorded assumptions and their status."""
        return self._backend.get_integrity_assumptions(self.slug)

    def integrity_sources(self) -> list[dict]:
        """Fetch recorded evidence sources."""
        return self._backend.get_integrity_sources(self.slug)

    def integrity_claims(self) -> list[dict]:
        """Fetch recorded empirical claims."""
        return self._backend.get_integrity_claims(self.slug)

    def integrity_source_detail(self, source_key: str) -> dict:
        return self._backend.get_integrity_source_detail(self.slug, source_key)

    def integrity_claim_detail(self, claim_key: str) -> dict:
        return self._backend.get_integrity_claim_detail(self.slug, claim_key)

    def integrity_dependency_graph(self) -> dict:
        return self._backend.get_integrity_dependency_graph(self.slug)

    def integrity_stale_graph(self) -> dict:
        return self._backend.get_integrity_stale_graph(self.slug)

    def integrity_verification_runs(self) -> dict:
        return self._backend.get_integrity_verification_runs(self.slug)

    def integrity_rerun_plan(self, assumption_key: str) -> dict:
        """Preview the rerun plan for a given assumption change."""
        return self._backend.get_integrity_rerun_plan(self.slug, assumption_key)

    def apply_integrity_rerun_plan(self, assumption_key: str) -> dict:
        """Create rerun tasks based on the current rerun plan for an assumption change."""
        return self._backend.apply_integrity_rerun_plan(self.slug, assumption_key)

    def apply_integrity_reproducibility_rerun(self, artifact_path: str) -> dict:
        return self._backend.apply_integrity_reproducibility_rerun(self.slug, artifact_path)

    def apply_integrity_freshness_evaluation(self, *, as_of: str | None = None) -> dict:
        return self._backend.apply_integrity_freshness_evaluation(self.slug, as_of=as_of)

    def apply_integrity_artifact_promotion(self, artifact_path: str, *, target_state: str) -> dict:
        return self._backend.apply_integrity_artifact_promotion(self.slug, artifact_path, target_state=target_state)

    def apply_integrity_source_candidate_promotion(self, candidate_key: str, *, source_type: str = "dataset") -> dict:
        return self._backend.apply_integrity_source_candidate_promotion(self.slug, candidate_key, source_type=source_type)

    def apply_integrity_claim_candidate_promotion(self, candidate_key: str, *, status: str) -> dict:
        return self._backend.apply_integrity_claim_candidate_promotion(self.slug, candidate_key, status=status)

    def apply_integrity_conflict_resolution(self, conflict_key: str, *, resolution: str) -> dict:
        return self._backend.apply_integrity_conflict_resolution(self.slug, conflict_key, resolution=resolution)

    def integrity_retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        artifact_types: list[str] | None = None,
        claim_statuses: list[str] | None = None,
        source_freshness: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_stale: bool = False,
        include_blocked: bool = False,
    ) -> dict:
        return self._backend.integrity_retrieve(
            self.slug,
            query,
            limit=limit,
            artifact_types=artifact_types,
            claim_statuses=claim_statuses,
            source_freshness=source_freshness,
            date_from=date_from,
            date_to=date_to,
            include_stale=include_stale,
            include_blocked=include_blocked,
        )

    def get_state(self) -> dict:
        """Fetch a structured context snapshot (classes, schema, sources, pipelines)."""
        return self._backend.get_project_state(self.slug)

    def get_work_order(self, work_order_id: str | None = None) -> dict:
        """Fetch a typed WorkOrder. If work_order_id is None, tries to resolve from environment."""
        if work_order_id is None:
            import os
            work_order_id = os.environ.get("RAIL_WORK_ORDER_ID")
        if not work_order_id:
            raise ValueError("work_order_id is required or must be set in RAIL_WORK_ORDER_ID env var")
        return self._backend.get_work_order(self.slug, work_order_id)

    def submit_session_result(self, result: dict, session_id: str | None = None) -> dict:
        """Submit the final session result."""
        if session_id is None:
            import os
            session_id = os.environ.get("RAIL_SESSION_ID")
        if not session_id:
            raise ValueError("session_id is required or must be set in RAIL_SESSION_ID env var")
        return self._backend.submit_session_result(self.slug, session_id, result)

    def ask(self, question: str, session_id: str | None = None) -> dict:
        """Ask a question to the planner/human mid-session."""
        if session_id is None:
            import os
            session_id = os.environ.get("RAIL_SESSION_ID")
        if not session_id:
            raise ValueError("session_id is required or must be set in RAIL_SESSION_ID env var")
        return self._backend.ask_question(self.slug, session_id, question)

    def __repr__(self):
        mode = "cloud" if hasattr(self._backend, "base_url") else "local"
        return f"Project(slug={self.slug!r}, mode={mode!r})"
