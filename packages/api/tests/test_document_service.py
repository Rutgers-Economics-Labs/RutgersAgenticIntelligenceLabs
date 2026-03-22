from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services import document_service


def test_extract_document_tables_rejects_unsupported_suffix(tmp_path):
    bad_path = tmp_path / "report.txt"
    bad_path.write_text("not a document")

    try:
        document_service.extract_document_tables(bad_path)
    except ValueError as exc:
        assert "Unsupported document format" in str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported document format")


def test_download_document_uses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(document_service.settings, "rail_cache_dir", tmp_path)

    response = MagicMock()
    response.content = b"%PDF-1.4 fake"
    response.raise_for_status.return_value = None

    with patch("app.services.document_service.requests.get", return_value=response) as get_mock:
        first = document_service.download_document("https://example.com/report.pdf")
        second = document_service.download_document("https://example.com/report.pdf")

    assert first == second
    assert first.exists()
    assert get_mock.call_count == 1


def test_parse_pages_range():
    assert document_service._parse_pages("2-4") == [1, 2, 3]


def test_parse_pages_single():
    assert document_service._parse_pages("3") == [2]
