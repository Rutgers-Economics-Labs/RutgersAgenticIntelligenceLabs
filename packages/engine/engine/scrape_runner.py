from __future__ import annotations

from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup


def fetch_html(
    url: str,
    *,
    table_selector: str | None = None,
    javascript: bool = False,
    encoding: str | None = None,
    timeout: int = 30,
) -> str:
    if javascript:
        return render_html(url, wait_for_selector=table_selector, timeout=timeout)

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    if encoding:
        response.encoding = encoding
    return response.text


def render_html(url: str, *, wait_for_selector: str | None = None, timeout: int = 30) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError(
            "JavaScript-rendered scraping requires Playwright. Install it before using javascript: true."
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            if wait_for_selector:
                page.wait_for_selector(wait_for_selector, timeout=timeout * 1000)
            return page.content()
        finally:
            browser.close()


def extract_table(html: str, table_selector: str | None = None) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")

    if table_selector:
        table = soup.select_one(table_selector)
        if table is None:
            raise ValueError(f"No table found for selector '{table_selector}'")
        return _table_to_dataframe(table)

    parsed_tables = _read_html_tables(html)
    if parsed_tables:
        return max(parsed_tables, key=len)

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No HTML tables found on page")

    return _table_to_dataframe(max(tables, key=lambda current: len(current.find_all("tr"))))


def _read_html_tables(html: str) -> list[pd.DataFrame]:
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return []
    return [table for table in tables if not table.empty]


def _table_to_dataframe(table) -> pd.DataFrame:
    rows: list[list[str]] = []
    headers: list[str] = []

    for tr in table.find_all("tr"):
        header_cells = tr.find_all("th")
        if header_cells and not headers:
            headers = [_cell_text(cell) for cell in header_cells]
            continue

        cells = tr.find_all(["td", "th"])
        if cells:
            rows.append([_cell_text(cell) for cell in cells])

    if not rows and headers:
        return pd.DataFrame(columns=headers)
    if not rows:
        raise ValueError("Selected table is empty")

    width = max(len(row) for row in rows)
    if not headers:
        headers = [f"column_{i + 1}" for i in range(width)]
    elif len(headers) < width:
        headers = headers + [f"column_{i + 1}" for i in range(len(headers), width)]

    normalized = [row + [""] * (len(headers) - len(row)) for row in rows]
    return pd.DataFrame(normalized, columns=headers)


def _cell_text(cell) -> str:
    return " ".join(cell.get_text(" ", strip=True).split())
