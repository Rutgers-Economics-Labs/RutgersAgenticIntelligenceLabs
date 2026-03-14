"""
Shared pytest fixtures for the RAIL FastAPI test suite.
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
import respx

# api package must come BEFORE engine on sys.path so Python picks up
# packages/api/app/ (FastAPI) rather than packages/engine/app.py (Streamlit)
API_ROOT = Path(__file__).parents[1]
ENGINE_ROOT = Path(__file__).parents[2] / "engine"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
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


@pytest.fixture
def convex_mock():
    """
    Intercept all Convex HTTP API calls and return empty/minimal responses.
    Tests can override specific endpoints by calling respx_mock.route() inside the test.
    """
    with respx.mock(base_url=CONVEX_URL, assert_all_called=False) as mock:
        # Default: queries return empty list, mutations return {}
        mock.post("/api/query").mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        mock.post("/api/mutation").mock(
            return_value=httpx.Response(200, json={"value": {}})
        )
        yield mock


@pytest_asyncio.fixture
async def client(convex_mock):
    """AsyncClient wired to the FastAPI app with Convex calls mocked."""
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
