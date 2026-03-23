"""
RailClient — main entry point for the rail_client SDK.

Usage in a Jupyter notebook:
    from rail_client import RailClient

    client = RailClient(base_url="http://localhost:8000/api/v1", job_id="abc123")

    # Query the ontology
    classes = client.ontology.classes()
    df = client.ontology.instances("Person", limit=100)

    # Run SQL
    df = client.sql("SELECT * FROM State LIMIT 10")

    # Save outputs (auto-attached to the job)
    client.save_text("Analysis complete.", name="summary")
    client.save_figure(plt.gcf(), name="unemployment_plot")
    client.save_model(sklearn_model, name="regression")
"""
from __future__ import annotations

import requests
from typing import Any

from .ontology import OntologyClient
from .sql import SqlClient
from .artifacts import ArtifactSaver


class RailClient:
    """
    Client for the RAIL research platform API.

    Parameters
    ----------
    base_url : str
        Base URL of the RAIL API, e.g. "http://localhost:8000/api/v1".
    job_id : str | None
        If set, all save_* calls will attach artifacts to this job.
    api_key : str | None
        Optional API key sent as X-API-Key header.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api/v1",
        job_id: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._job_id = job_id
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key

        self.ontology = OntologyClient(self)
        self._sql_client = SqlClient(self)
        self._artifacts: ArtifactSaver | None = (
            ArtifactSaver(self, job_id) if job_id else None
        )

    # ------------------------------------------------------------------
    # Low-level HTTP helpers (used by sub-clients)
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        resp = self._session.get(f"{self._base}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> Any:
        resp = self._session.post(
            f"{self._base}{path}",
            json=body,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # SQL convenience — callable directly as client.sql("SELECT ...")
    # ------------------------------------------------------------------

    def sql(self, query: str):
        """Execute a SQL query and return results as a pandas DataFrame."""
        return self._sql_client.query(query)

    # ------------------------------------------------------------------
    # Artifact helpers — delegate to ArtifactSaver if job_id is set
    # ------------------------------------------------------------------

    def _require_job(self) -> ArtifactSaver:
        if self._artifacts is None:
            raise RuntimeError(
                "No job_id set. Pass job_id= to RailClient(...) to attach artifacts to a job."
            )
        return self._artifacts

    def save_text(self, text: str, name: str = "output.txt") -> dict:
        """Save a text/markdown string as a job artifact."""
        return self._require_job().save_text(text, name)

    def save_figure(self, fig, name: str = "figure") -> dict:
        """Save a matplotlib Figure as a PNG job artifact."""
        return self._require_job().save_figure(fig, name)

    def save_image(self, img, name: str = "image") -> dict:
        """Save a PIL Image as a PNG job artifact."""
        return self._require_job().save_image(img, name)

    def save_model(self, model, name: str = "model") -> dict:
        """Serialize a scikit-learn model and save as a job artifact."""
        return self._require_job().save_model(model, name)

    def save_file(self, path: str, name: str | None = None) -> dict:
        """Upload any local file as a job artifact."""
        return self._require_job().save_file(path, name)
