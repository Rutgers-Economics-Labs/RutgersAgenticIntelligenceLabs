"""
Shared pytest fixtures for the RAIL FastAPI test suite.
"""
import sys
from pathlib import Path

import pytest
import httpx

try:
    import pytest_asyncio
except ModuleNotFoundError:  # pragma: no cover - local fallback for lightweight environments
    pytest_asyncio = None

try:
    import respx
except ModuleNotFoundError:  # pragma: no cover - local fallback for lightweight environments
    respx = None

# api package must come BEFORE engine on sys.path so Python picks up
# packages/api/app/ (FastAPI) rather than packages/engine/app.py (Streamlit)
API_ROOT = Path(__file__).parents[1]
ENGINE_ROOT = Path(__file__).parents[2] / "engine"
RAIL_PY_ROOT = Path(__file__).parents[2] / "rail-py"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.append(str(RAIL_PY_ROOT))
if str(ENGINE_ROOT) not in sys.path:
    sys.path.append(str(ENGINE_ROOT))

# Override settings before importing the app
import os
os.environ.setdefault("CONVEX_URL", "https://colorless-elephant-150.convex.cloud")
os.environ.setdefault("CONVEX_DEPLOY_KEY", "test-key")
os.environ.setdefault("ENGINE_ROOT", str(ENGINE_ROOT))
os.environ.setdefault("RAIL_ANALYSIS_DIR", str(ENGINE_ROOT / "analysis"))
os.environ.setdefault("RAIL_TRANSFORM_DIR", str(ENGINE_ROOT / "transforms"))


CONVEX_URL = os.environ["CONVEX_URL"]


def seed_workflow_scaffolding(root):
    """Materialize the workflow files most integrity tests reference in lineage.

    Shared between test_integrity_service.py and test_integrity_router.py.
    The artifact-lineage normalizer (commit 7ad66b6) strips inputs, scripts,
    and verification_commands that don't exist on disk; the verification-run
    normalizer additionally downgrades passed → pending when no artifact
    paths resolve. Tests written before those hardening commits land on
    stale `draft` artifacts and empty verification-run lookups.
    """
    files = {
        # Many tests reference artifacts/report.md as a verification target.
        # The verification-run normalizer strips artifact_paths that don't
        # exist AND downgrades status from "passed" to "pending" when all
        # paths are stripped — the file must exist on disk for seeded runs
        # to survive.
        "artifacts/report.md": "# stable report placeholder\n",
        "topics/analyze.py": "# analysis script placeholder\n",
        "topics/labor/notes.md": "# labor evidence notes placeholder\n",
        "topics/data.csv": "id,value\n1,100\n",
        "topics/scripts/transform.py": "# transform script placeholder\n",
        "topics/analysis.csv": "id,value\n1,100\n",
        "topics/analysis/analyze.py": "# analysis pipeline placeholder\n",
        "topics/analysis/notes.md": "# analysis notes placeholder\n",
        "topics/analysis/queue_notes.md": "# queue evidence notes placeholder\n",
        "topics/analysis/fell.md": "# fell evidence notes placeholder\n",
        "topics/analysis/rose.md": "# rose evidence notes placeholder\n",
        "topics/briefing.md": "# briefing note placeholder\n",
        "topics/notes.md": "# evidence notes placeholder\n",
        "topics/lit/synthesis.md": "# literature synthesis placeholder\n",
        "scripts/run-verification.sh": "#!/usr/bin/env bash\nexit 0\n",
        "scripts/run-rerun.sh": "#!/usr/bin/env bash\nexit 0\n",
        "pipelines/hydrate.py": "# hydrate pipeline script placeholder\n",
        ".ontology/pipelines/default.yaml": "ontology: .ontology/ontology.yaml\nsteps: []\n",
    }
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    # Many reproducibility-rerun tests reference `.ontology/onto.duckdb` as
    # an input. Create a valid (empty) DuckDB file unless the test has
    # already written one (some tests open it as a real DuckDB connection).
    # Seed a placeholder lineage entry for artifacts/report.md so the
    # integrity auditor's artifact-registry drift detector doesn't flag it
    # as untracked. Tests that need their own promotion_state overwrite this
    # via write_artifact_lineage (the writer replaces, not merges).
    try:
        from rail.integrity import ResearchIntegrityRepo as _Repo

        repo = _Repo(Path(root))
        existing = {
            item.artifact_path
            for item in repo.load_artifact_lineage()
        }
        if "artifacts/report.md" not in existing:
            repo.upsert_artifact_lineage(
                {
                    "artifact_path": "artifacts/report.md",
                    "artifact_type": "report",
                    "title": "Placeholder Report",
                    "promotion_state": "exploratory",
                }
            )
    except Exception:
        pass

    duckdb_path = Path(root) / ".ontology" / "onto.duckdb"
    if not duckdb_path.exists():
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import duckdb as _duckdb

            conn = _duckdb.connect(str(duckdb_path))
            # The promotion gate (commit 10aa3fa) requires populated rows.
            # Seed a tiny table so the gate doesn't block promotion in
            # router-level integration tests.
            conn.execute("CREATE TABLE sample (id INTEGER, value INTEGER)")
            conn.execute("INSERT INTO sample VALUES (1, 100)")
            conn.close()
        except Exception:
            duckdb_path.write_bytes(b"")
    # Bootstrap sets project.mode=ontology_first by default but doesn't
    # create the hydration meta file. Write one so the ontology auditor
    # reports state=hydrated_on_this_device for integration tests.
    hydration_meta = Path(root) / ".ontology" / ".rail_hydration.json"
    if not hydration_meta.exists():
        import json as _json

        hydration_meta.write_text(
            _json.dumps(
                {
                    "pipelineSlug": "default",
                    "hydrationMode": "full",
                    "hydratedAt": "2026-05-14T00:00:00Z",
                    "deviceId": "test-device",
                }
            ),
            encoding="utf-8",
        )


@pytest.fixture
def convex_mock():
    """
    Intercept all Convex HTTP API calls and return empty/minimal responses.
    Tests can override specific endpoints by calling respx_mock.route() inside the test.
    """
    if respx is None:
        yield None
        return

    with respx.mock(base_url=CONVEX_URL, assert_all_called=False) as mock:
        mock.post("/api/query").mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        mock.post("/api/mutation").mock(
            return_value=httpx.Response(200, json={"value": {"jobId": "test_job_123"}})
        )
        yield mock


if pytest_asyncio is not None:
    @pytest_asyncio.fixture
    async def client(convex_mock):
        """AsyncClient wired to the FastAPI app with Convex calls mocked."""
        from app.main import app
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
else:
    @pytest.fixture
    async def client(convex_mock):
        """AsyncClient wired to the FastAPI app with Convex calls mocked."""
        from app.main import app
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture(autouse=True)
def mock_ensure_workspace_rail_cli(monkeypatch):
    """Avoid pip installs during test execution."""
    from app.runners import session_lifecycle
    async def _mock_ensure(project_root, workspace_root):
        return {"status": "passed", "returncode": 0, "stdout": "rail ok", "stderr": ""}
    monkeypatch.setattr(session_lifecycle, "_ensure_workspace_rail_cli", _mock_ensure)

