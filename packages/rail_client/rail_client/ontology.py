"""OntologyClient — wraps the RAIL /ontology/* endpoints."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from .client import RailClient


class OntologyClient:
    def __init__(self, client: "RailClient") -> None:
        self._c = client

    def _get(self, path: str, params: dict | None = None):
        return self._c._get(path, params=params)

    def classes(self) -> list[dict]:
        """List all ontology classes with instance counts."""
        return self._get("/ontology/classes")

    def instances(
        self,
        class_name: str,
        page: int = 1,
        limit: int = 50,
        search: str = "",
    ) -> "pd.DataFrame":
        """Fetch instances of a class as a pandas DataFrame."""
        import pandas as pd
        result = self._get(
            f"/ontology/classes/{class_name}/instances",
            params={"page": page, "limit": limit, "search": search},
        )
        items = result.get("items", [])
        if not items:
            return pd.DataFrame()
        rows = []
        for item in items:
            row = {"_id": item.get("id"), "_iri": item.get("iri"), "_class": item.get("class")}
            row.update(item.get("properties", {}))
            rows.append(row)
        return pd.DataFrame(rows)

    def entity(self, uri: str) -> dict:
        """Get a single entity with all properties and relationships."""
        from urllib.parse import quote
        return self._get(f"/ontology/entities/{quote(uri, safe='')}")

    def entity_graph(self, uri: str) -> dict:
        """Get the local graph around an entity."""
        from urllib.parse import quote
        return self._get(f"/ontology/entities/{quote(uri, safe='')}/graph")

    def graph(
        self,
        types: list[str] | None = None,
        state_fips: str | None = None,
        limit: int = 500,
    ) -> dict:
        """Fetch the full graph (nodes + links) with optional type filtering."""
        params: dict = {"limit": limit}
        if types:
            params["types"] = ",".join(types)
        if state_fips:
            params["state_fips"] = state_fips
        return self._get("/ontology/graph", params=params)

    def search(self, q: str, types: list[str] | None = None) -> list[dict]:
        """Text search across entities."""
        params: dict = {"q": q}
        if types:
            params["types"] = ",".join(types)
        return self._get("/ontology/search", params=params)

    def semantic_search(self, q: str, types: list[str] | None = None, limit: int = 20) -> list[dict]:
        """Embedding-based semantic search."""
        params: dict = {"q": q, "limit": limit}
        if types:
            params["types"] = ",".join(types)
        return self._get("/ontology/semantic-search", params=params)

    def series(self) -> list[str]:
        """List available time-series IDs."""
        return self._get("/ontology/series")

    def series_data(self, series_id: str) -> "pd.DataFrame":
        """Get time-series values as a pandas DataFrame."""
        import pandas as pd
        from urllib.parse import quote
        data = self._get(f"/ontology/series/{quote(series_id, safe='')}/data")
        return pd.DataFrame(data)
