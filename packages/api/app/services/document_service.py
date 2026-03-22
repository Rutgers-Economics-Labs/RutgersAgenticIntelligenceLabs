from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd
import requests

from app.core.config import settings
from app.services.storage_service import storage


async def preview_document(
    storage_key: str,
    extraction_mode: str,
    pages: str | None = None,
) -> dict:
    if extraction_mode != "tables":
        raise ValueError("Only extraction_mode=tables is supported in this preview flow")

    suffix = Path(storage_key).suffix.lower() or ".bin"
    local_path = settings.rail_cache_dir / "doc-preview" / f"{hashlib.sha1(storage_key.encode()).hexdigest()}{suffix}"
    await storage.download(storage_key, local_path)
    df = extract_document_tables(local_path, pages=pages)
    return {
        "columns": [str(col) for col in df.columns.tolist()],
        "rows": df.head(5).fillna("").to_dict(orient="records"),
        "rowCount": int(len(df)),
    }


def extract_document_tables(path: str | Path, pages: str | None = None) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_tables(path, pages=pages)
    if suffix == ".docx":
        return _extract_docx_tables(path)
    raise ValueError(f"Unsupported document format: {suffix}")


def download_document(url: str, suffix: str | None = None) -> Path:
    cache_dir = settings.rail_cache_dir / "documents"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = suffix or Path(url).suffix or ".bin"
    local_path = cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}{ext}"
    if local_path.exists():
        return local_path
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(response.content)
    return local_path


def _extract_pdf_tables(path: Path, pages: str | None = None) -> pd.DataFrame:
    import pdfplumber

    selected_pages = _parse_pages(pages)
    frames: list[pd.DataFrame] = []
    with pdfplumber.open(path) as pdf:
        indices = selected_pages or list(range(len(pdf.pages)))
        for index in indices:
            if index < 0 or index >= len(pdf.pages):
                continue
            page = pdf.pages[index]
            for table in page.extract_tables() or []:
                if not table:
                    continue
                header = table[0]
                rows = table[1:] if len(table) > 1 else []
                if not rows:
                    continue
                frames.append(pd.DataFrame(rows, columns=header))
    if not frames:
        raise ValueError("No tables found in document")
    return pd.concat(frames, ignore_index=True)


def _extract_docx_tables(path: Path) -> pd.DataFrame:
    from docx import Document

    document = Document(path)
    frames: list[pd.DataFrame] = []
    for table in document.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if len(rows) < 2:
            continue
        header = rows[0]
        frames.append(pd.DataFrame(rows[1:], columns=header))
    if not frames:
        raise ValueError("No tables found in document")
    return pd.concat(frames, ignore_index=True)


def _parse_pages(pages: str | None) -> list[int]:
    if not pages:
        return []
    if "-" in pages:
        start_str, end_str = pages.split("-", 1)
        start = int(start_str)
        end = int(end_str)
        return list(range(start - 1, end))
    page = int(pages)
    return [page - 1]
