import pytest
import requests
from unittest.mock import patch

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
    with patch("app.services.scrape_service.fetch_html", return_value=HTML):
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
    with patch("app.services.scrape_service.fetch_html", return_value=HTML):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={"url": "https://example.com/table", "table_selector": "table.missing"},
        )

    assert resp.status_code == 422
    assert "No table found" in resp.json()["detail"]


async def test_scrape_preview_fetch_failure(client):
    with patch(
        "app.services.scrape_service.fetch_html",
        side_effect=requests.RequestException("timeout"),
    ):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={"url": "https://example.com/table"},
        )

    assert resp.status_code == 502
    assert "Failed to fetch URL" in resp.json()["detail"]


async def test_scrape_preview_javascript_success(client):
    with patch("engine.scrape_runner.render_html", return_value=HTML):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={
                "url": "https://example.com/table",
                "table_selector": "table.data-table",
                "javascript": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["name", "value"]
    assert body["rowCount"] == 2


async def test_scrape_preview_javascript_requires_playwright(client):
    with patch(
        "engine.scrape_runner.render_html",
        side_effect=ValueError("JavaScript-rendered scraping requires Playwright. Install it before using javascript: true."),
    ):
        resp = await client.post(
            "/api/v1/configs/scrape-preview",
            json={"url": "https://example.com/table", "javascript": True},
        )

    assert resp.status_code == 422
    assert "Playwright" in resp.json()["detail"]
