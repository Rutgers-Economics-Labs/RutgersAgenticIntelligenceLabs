from __future__ import annotations

import pandas as pd
import requests
from bs4 import BeautifulSoup


def preview_table(url: str, table_selector: str | None = None) -> dict:
    html = fetch_html(url)
    df = extract_table(html, table_selector=table_selector)
    return {
        "columns": [str(col) for col in df.columns.tolist()],
        "rows": df.head(5).fillna("").to_dict(orient="records"),
        "rowCount": int(len(df)),
    }


def fetch_html(url: str, encoding: str | None = None, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    if encoding:
        response.encoding = encoding
    return response.text


def extract_table(html: str, table_selector: str | None = None) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")

    if table_selector:
        table = soup.select_one(table_selector)
        if table is None:
            raise ValueError(f"No table found for selector '{table_selector}'")
        return _table_to_dataframe(table)

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No HTML tables found on page")

    best_table = max(tables, key=lambda table: len(table.find_all("tr")))
    return _table_to_dataframe(best_table)


def _table_to_dataframe(table) -> pd.DataFrame:
    rows = []
    headers = []

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
