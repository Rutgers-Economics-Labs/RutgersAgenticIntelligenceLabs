import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.asyncio

HTML = """
<html>
  <body>
    <table class="data-table">
      <tr><th>name</th><th>value</th></tr>
      <tr><td>A</td><td>1</td></tr>
      <tr><td>B</td><td>2</td></tr>
    </table>
  </body>
</html>
"""


async def test_scrape_preview_success(client):
    response = MagicMock()
    response.text = HTML
    response.raise_for_status.return_value = None

    with patch("app.services.scrape_service.requests.get", return_value=response):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={"url": "https://example.com/table", "table_selector": "table.data-table"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["name", "value"]
    assert body["rowCount"] == 2
    assert body["rows"][0]["name"] == "A"


async def test_scrape_preview_selector_not_found(client):
    response = MagicMock()
    response.text = HTML
    response.raise_for_status.return_value = None

    with patch("app.services.scrape_service.requests.get", return_value=response):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={"url": "https://example.com/table", "table_selector": "table.missing"},
        )

    assert resp.status_code == 422
    assert "No table found" in resp.json()["detail"]
