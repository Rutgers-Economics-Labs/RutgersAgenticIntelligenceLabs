from rail.project import Project
from rail.client import CloudClient
from rail.local import LocalEngine
from rail.exceptions import RailError

def connect(
    slug: str,
    api_url: str | None = None,
    api_key: str | None = None,
) -> Project:
    """Connect to a RAIL project via the platform API (cloud mode)."""
    import os
    url = api_url or os.environ.get("RAIL_API_URL", "http://localhost:8000/api/v1")
    key = api_key or os.environ.get("RAIL_API_KEY", "")
    client = CloudClient(base_url=url, api_key=key)
    return Project(slug=slug, backend=client)

def local(
    path: str = ".",
    engine_path: str | None = None,
) -> Project:
    """Load a RAIL project from a local repo directory (local mode)."""
    engine = LocalEngine(project_path=path, engine_path=engine_path)
    slug = engine.read_rail_yaml()["slug"]
    return Project(slug=slug, backend=engine)