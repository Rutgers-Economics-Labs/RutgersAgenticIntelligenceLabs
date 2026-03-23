"""Unit tests for resolve_quadstore_path (Convex + allowlist + default)."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.ontology_routing import resolve_quadstore_path

pytestmark = pytest.mark.asyncio


async def test_rejects_both_project_and_ontology_key():
    with pytest.raises(HTTPException) as ei:
        await resolve_quadstore_path("proj_123", "academic")
    assert ei.value.status_code == 400


async def test_project_chain_returns_resolved_file(tmp_path: Path):
    db_file = tmp_path / "quad.db"
    db_file.write_bytes(b"")

    mock_convex = AsyncMock(
        side_effect=[
            {"lastJobId": "job_1"},
            {"status": "success", "outputDbPath": str(db_file)},
        ]
    )

    with patch("app.services.ontology_routing.convex") as cx:
        cx.query = mock_convex
        path = await resolve_quadstore_path("k7abc123projects", None)

    assert path == str(db_file.resolve())
    assert mock_convex.query.await_count == 2


async def test_unknown_ontology_key():
    with pytest.raises(HTTPException) as ei:
        await resolve_quadstore_path(None, "not-a-real-key")
    assert ei.value.status_code == 404
    assert "Unknown ontology_key" in ei.value.detail


async def test_allowlisted_key_requires_file(tmp_path: Path):
    """When academic.db is missing, resolver returns 404 with helpful detail."""
    fake_root = tmp_path / "engine"
    (fake_root / "ontology").mkdir(parents=True)
    with patch.object(settings, "engine_root", fake_root):
        with pytest.raises(HTTPException) as ei:
            await resolve_quadstore_path(None, "academic")
    assert ei.value.status_code == 404
