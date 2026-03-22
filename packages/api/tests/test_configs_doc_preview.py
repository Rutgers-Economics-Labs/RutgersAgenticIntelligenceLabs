import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


async def test_doc_preview_success(client):
    preview = {
        "columns": ["metric", "value"],
        "rows": [{"metric": "Population", "value": "100"}],
        "rowCount": 1,
    }

    with patch("app.routers.configs.preview_document", new=AsyncMock(return_value=preview)) as preview_mock:
        resp = await client.post(
            "/api/v1/configs/doc-preview",
            json={"storage_key": "inputs/report.pdf", "extraction_mode": "tables", "pages": "1-2"},
        )

    assert resp.status_code == 200
    assert resp.json() == preview
    preview_mock.assert_awaited_once_with("inputs/report.pdf", "tables", "1-2")


async def test_doc_preview_rejects_unsupported_mode(client):
    with patch(
        "app.routers.configs.preview_document",
        new=AsyncMock(side_effect=ValueError("Only extraction_mode=tables is supported in this preview flow")),
    ):
        resp = await client.post(
            "/api/v1/configs/doc-preview",
            json={"storage_key": "inputs/report.pdf", "extraction_mode": "prose"},
        )

    assert resp.status_code == 422
    assert "Only extraction_mode=tables is supported" in resp.json()["detail"]
