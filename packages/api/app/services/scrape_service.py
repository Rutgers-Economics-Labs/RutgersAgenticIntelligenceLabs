from __future__ import annotations

import sys
from pathlib import Path

engine_root = Path(__file__).resolve().parents[3] / "engine"
if str(engine_root) not in sys.path:
    sys.path.insert(0, str(engine_root))

from engine.scrape_runner import extract_table, fetch_html


def preview_table(
    url: str,
    table_selector: str | None = None,
    javascript: bool = False,
    encoding: str | None = None,
) -> dict:
    html = fetch_html(url, table_selector=table_selector, javascript=javascript, encoding=encoding)
    df = extract_table(html, table_selector=table_selector)
    return {
        "columns": [str(col) for col in df.columns.tolist()],
        "rows": df.head(5).fillna("").to_dict(orient="records"),
        "rowCount": int(len(df)),
    }
