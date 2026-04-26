import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any

from app.agents.scraping_agent import WebScrapingAgent

@pytest.fixture
def mock_playwright_html() -> str:
    return """
    <html>
        <body>
            <h1>Economic Indicators</h1>
            <!-- Direct download link we want the agent to find -->
            <a href="https://example.com/data.csv">Download Full Dataset (CSV)</a>
            <a href="https://example.com/data.zip">Download ZIP</a>
            <table id="data-table">
                <tr><th>Year</th><th>GDP</th></tr>
                <tr><td>2020</td><td>21.06</td></tr>
                <tr><td>2021</td><td>23.32</td></tr>
            </table>
        </body>
    </html>
    """

@pytest.fixture
def mock_playwright_page(mock_playwright_html: str):
    page_mock = AsyncMock()
    page_mock.content.return_value = mock_playwright_html
    return page_mock

@pytest.fixture
def mock_playwright_context(mock_playwright_page):
    context_mock = AsyncMock()
    context_mock.new_page.return_value = mock_playwright_page
    return context_mock

@pytest.fixture
def mock_playwright_browser(mock_playwright_context):
    browser_mock = AsyncMock()
    browser_mock.new_context.return_value = mock_playwright_context
    return browser_mock

@pytest.fixture
def mock_playwright(mock_playwright_browser):
    pw_mock = AsyncMock()
    pw_mock.chromium.launch.return_value = mock_playwright_browser
    
    # Context manager setup for async with async_playwright()
    ctx_mgr = AsyncMock()
    ctx_mgr.__aenter__.return_value = pw_mock
    return ctx_mgr

@pytest.mark.asyncio
async def test_agent_prioritizes_downloads(mock_playwright):
    """
    Ensure the agent finds large file downloads (CSV/ZIP) instead of trying to parse the table.
    """
    target_url = "https://example.com/data"
    
    agent = WebScrapingAgent()
    
    with patch("app.agents.scraping_agent.async_playwright", return_value=mock_playwright):
        config = await agent.generate_config(target_url)
    
    assert "source_type" in config
    assert config["source_type"] == "direct_download"
    assert "download_urls" in config
    assert "https://example.com/data.csv" in config["download_urls"]
    assert "https://example.com/data.zip" in config["download_urls"]

@pytest.mark.asyncio
async def test_agent_extracts_data_via_playwright(mock_playwright):
    """
    Ensure extract_data uses Playwright for execution.
    For direct downloads, extract_data should return a structured indicator pointing to the URLs.
    """
    target_url = "https://example.com/data"
    config = {
        "source_type": "direct_download",
        "url": target_url,
        "download_urls": ["https://example.com/data.csv"]
    }
    
    agent = WebScrapingAgent()
    
    with patch("app.agents.scraping_agent.async_playwright", return_value=mock_playwright):
        data = await agent.extract_data(target_url, config)
    
    assert len(data) == 1
    assert data[0]["url"] == "https://example.com/data.csv"
    assert data[0]["status"] == "pending_hydration_download"
