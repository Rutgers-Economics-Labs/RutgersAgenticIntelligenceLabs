# WO-6.1 — rail-py Package Skeleton

**Status:** ready  
**Spec:** `specs/rail-py.md`  
**Depends on:** nothing (but cloud mode works better after WO-0.3)  
**Blocks:** WO-6.2  

---

## Goal

Create the `packages/rail-py/` package with entry points, `CloudClient`, `LocalEngine`, and the unified `Project` interface.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/rail-py/pyproject.toml` | **Create** | Package metadata + deps |
| `packages/rail-py/rail/__init__.py` | **Create** | `connect()` and `local()` entry points |
| `packages/rail-py/rail/client.py` | **Create** | `CloudClient` — wraps FastAPI HTTP |
| `packages/rail-py/rail/local.py` | **Create** | `LocalEngine` — imports engine directly |
| `packages/rail-py/rail/project.py` | **Create** | `Project` — unified interface |
| `packages/rail-py/rail/models.py` | **Create** | Pydantic models for API responses |
| `packages/rail-py/rail/exceptions.py` | **Create** | `RailError`, `HydrationError`, etc. |

---

## Steps

### 1. Create `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "rail"
version = "0.1.0"
description = "RAIL platform client — cloud and local modes"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2",
]

[project.optional-dependencies]
analysis = ["numpy", "pandas", "statsmodels", "matplotlib"]
local = ["owlready2", "duckdb", "pyyaml"]

[tool.setuptools.packages.find]
where = ["."]
include = ["rail*"]
```

### 2. Create `rail/__init__.py`

```python
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
```

### 3. Create `rail/client.py` — CloudClient

```python
import httpx
from typing import Any

class CloudClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    
    def get(self, path: str, **params) -> Any:
        with httpx.Client() as client:
            r = client.get(f"{self.base_url}{path}", params=params, headers=self.headers)
            r.raise_for_status()
            return r.json()
    
    def post(self, path: str, data: dict) -> Any:
        with httpx.Client() as client:
            r = client.post(f"{self.base_url}{path}", json=data, headers=self.headers)
            r.raise_for_status()
            return r.json()
    
    def hydrate(self, pipeline_slug: str) -> dict:
        return self.post("/jobs", {"pipeline_slug": pipeline_slug})
    
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
```

### 4. Create `rail/local.py` — LocalEngine

```python
import sys
from pathlib import Path
import yaml

class LocalEngine:
    def __init__(self, project_path: str, engine_path: str | None = None):
        self.project_path = Path(project_path).resolve()
        
        # Find engine — either explicit or by traversing up to monorepo
        if engine_path:
            self.engine_path = Path(engine_path).resolve()
        else:
            # Try monorepo layout: project is in packages/engine, we're at packages/rail-py
            candidate = Path(__file__).parent.parent.parent / "engine"
            self.engine_path = candidate if candidate.exists() else None
        
        if self.engine_path:
            sys.path.insert(0, str(self.engine_path))
    
    def read_rail_yaml(self) -> dict:
        rail_yaml = self.project_path / "rail.yaml"
        if not rail_yaml.exists():
            raise FileNotFoundError(f"rail.yaml not found in {self.project_path}")
        return yaml.safe_load(rail_yaml.read_text())
    
    def hydrate(self, pipeline_slug: str) -> dict:
        from engine.pipeline_runner import run_pipeline
        pipeline_path = self.project_path / f"configs/pipelines/{pipeline_slug}.yaml"
        return run_pipeline(str(pipeline_path))
    
    def query_sql(self, sql: str) -> dict:
        import duckdb
        onto_duckdb = self.project_path / "ontology/onto.duckdb"
        conn = duckdb.connect(str(onto_duckdb), read_only=True)
        result = conn.execute(sql).fetchdf()
        conn.close()
        return {"columns": list(result.columns), "rows": result.values.tolist()}
    
    def get_classes(self) -> list[dict]:
        import duckdb
        onto_duckdb = self.project_path / "ontology/onto.duckdb"
        conn = duckdb.connect(str(onto_duckdb), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchdf()
        classes = []
        for t in tables["name"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            classes.append({"name": t, "instance_count": count})
        conn.close()
        return classes
```

### 5. Create `rail/project.py` — Unified Project interface

```python
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
```

---

## Acceptance

- [ ] `pip install -e packages/rail-py` succeeds
- [ ] `import rail; p = rail.connect("nj-economics")` works when the API is running
- [ ] `p.query("SELECT COUNT(*) FROM County")` returns a DataFrame
- [ ] `p.classes()` returns the class list
- [ ] `rail.local("./nj-economics")` works when `onto.duckdb` exists locally
- [ ] `p.execute("print(sql('SELECT * FROM State LIMIT 5'))") ` returns stdout
