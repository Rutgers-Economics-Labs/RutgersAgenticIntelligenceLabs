"""
Tests for engine.pipeline_runner — runs a minimal pipeline against an in-memory quadstore.
No network calls; uses a tiny inline YAML config and a synthetic DataFrame.
"""
import sys
import os
import tempfile
from pathlib import Path
import pytest
import yaml
import pandas as pd
from unittest.mock import patch, MagicMock

ENGINE_ROOT = Path(__file__).parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from engine.pipeline_runner import _sanitize, _resolve, run_pipeline


# ── unit helpers ──────────────────────────────────────────────────────────────

def test_sanitize_replaces_spaces():
    assert _sanitize("New Jersey") == "New_Jersey"


def test_sanitize_replaces_special_chars():
    assert _sanitize("foo/bar&baz") == "foo_bar_baz"


def test_sanitize_preserves_safe_chars():
    assert _sanitize("State_NJ-01.2") == "State_NJ-01.2"


def test_resolve_simple():
    assert _resolve("State_{fips}", {"fips": "34"}) == "State_34"


def test_resolve_multiple_placeholders():
    assert _resolve("{a}_{b}", {"a": "X", "b": "Y"}) == "X_Y"


def test_resolve_sanitize_mode():
    result = _resolve("State_{name}", {"name": "New Jersey"}, sanitize=True)
    assert " " not in result
    assert result == "State_New_Jersey"


def test_resolve_unknown_placeholder_left_as_is():
    result = _resolve("{unknown}", {"other": "x"})
    assert result == "{unknown}"


# ── integration: minimal pipeline run ────────────────────────────────────────

MINIMAL_ONTOLOGY = """
uri: http://example.org/test_minimal.owl
classes:
  - name: Item
data_properties:
  - name: hasName
    domain: [Thing]
    range: str
    functional: true
  - name: hasCode
    domain: [Item]
    range: str
    functional: true
"""

MINIMAL_PIPELINE = """
ontology: {onto_path}
output_owl: {output_owl}
db: {db_path}
steps:
  - name: load_items
    api: items
    class: Item
    uri: "Item_{{code}}"
    properties:
      hasName: "{{name}}"
      hasCode: "{{code}}"
"""

MINIMAL_API_YAML = """
name: items
type: csv
path: {csv_path}
fields:
  - source: name
    alias: name
  - source: code
    alias: code
"""


@pytest.fixture
def minimal_pipeline_dir(tmp_path, monkeypatch):
    """
    Create a self-contained pipeline in a temp directory and patch the
    engine's RAIL_API_CONFIG_DIR env var to point there.
    """
    # Write ontology YAML
    onto_path = tmp_path / "ontology.yaml"
    onto_path.write_text(MINIMAL_ONTOLOGY)

    # Write a CSV data source
    csv_path = tmp_path / "items.csv"
    df = pd.DataFrame({"name": ["Alpha", "Beta", "Gamma"], "code": ["A1", "B2", "C3"]})
    df.to_csv(csv_path, index=False)

    # Write the API YAML
    api_dir = tmp_path / "apis"
    api_dir.mkdir()
    api_yaml = tmp_path / "apis" / "items.yaml"
    api_yaml.write_text(MINIMAL_API_YAML.format(csv_path=str(csv_path)))

    # Paths for outputs
    output_owl = str(tmp_path / "out.owl")
    db_path = str(tmp_path / "onto.db")

    # Write the pipeline YAML
    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(MINIMAL_PIPELINE.format(
        onto_path=str(onto_path),
        output_owl=output_owl,
        db_path=db_path,
    ))

    # Point api_runner at our temp API config dir
    monkeypatch.setenv("RAIL_API_CONFIG_DIR", str(api_dir))
    monkeypatch.setenv("RAIL_CACHE_DIR", str(tmp_path / "cache"))

    # Reload api_runner constants (they are module-level Paths read from env)
    import importlib
    import engine.api_runner
    importlib.reload(engine.api_runner)

    return {
        "pipeline_path": str(pipeline_yaml),
        "db_path": db_path,
        "output_owl": output_owl,
    }


def _open_db(db_path: str):
    """Open the quadstore after forcing GC to release any exclusive locks from run_pipeline."""
    import gc
    gc.collect()
    from owlready2 import World
    w = World()
    w.set_backend(filename=db_path, exclusive=False)
    return w


def test_run_pipeline_creates_outputs(minimal_pipeline_dir):
    run_pipeline(minimal_pipeline_dir["pipeline_path"])
    assert Path(minimal_pipeline_dir["db_path"]).exists()
    assert Path(minimal_pipeline_dir["output_owl"]).exists()


def test_run_pipeline_populates_individuals(minimal_pipeline_dir):
    run_pipeline(minimal_pipeline_dir["pipeline_path"])

    w = _open_db(minimal_pipeline_dir["db_path"])
    onto = w.get_ontology("http://example.org/test_minimal.owl").load()

    item_cls = next((c for c in onto.classes() if c.name == "Item"), None)
    assert item_cls is not None

    items = list(item_cls.instances())
    assert len(items) == 3

    names = {getattr(i, "hasName", None) for i in items}
    assert "Alpha" in names
    assert "Beta" in names
    assert "Gamma" in names

    codes = {getattr(i, "hasCode", None) for i in items}
    assert "A1" in codes


def test_run_pipeline_idempotent_uris(minimal_pipeline_dir):
    """Running the same pipeline twice should not duplicate individuals."""
    run_pipeline(minimal_pipeline_dir["pipeline_path"])
    run_pipeline(minimal_pipeline_dir["pipeline_path"])

    w = _open_db(minimal_pipeline_dir["db_path"])
    onto = w.get_ontology("http://example.org/test_minimal.owl").load()

    item_cls = next((c for c in onto.classes() if c.name == "Item"), None)
    assert len(list(item_cls.instances())) == 3


SCRAPE_API_YAML = """
name: items
type: scrape
url: https://example.com/table
table_selector: table.data-table
fields:
  - source: name
    alias: name
  - source: code
    alias: code
"""

SCRAPE_HTML = """
<html>
  <body>
    <table class="data-table">
      <tr><th>name</th><th>code</th></tr>
      <tr><td>Delta</td><td>D4</td></tr>
      <tr><td>Epsilon</td><td>E5</td></tr>
    </table>
  </body>
</html>
"""

PDF_API_YAML = """
name: items
type: pdf
path: /tmp/report.pdf
extraction_mode: tables
fields:
  - source: name
    alias: name
  - source: code
    alias: code
"""


def test_run_pipeline_with_scrape_source(tmp_path, monkeypatch):
    onto_path = tmp_path / "ontology.yaml"
    onto_path.write_text(MINIMAL_ONTOLOGY)

    api_dir = tmp_path / "apis"
    api_dir.mkdir()
    (api_dir / "items.yaml").write_text(SCRAPE_API_YAML)

    output_owl = str(tmp_path / "out.owl")
    db_path = str(tmp_path / "onto.db")
    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(MINIMAL_PIPELINE.format(
        onto_path=str(onto_path),
        output_owl=output_owl,
        db_path=db_path,
    ))

    monkeypatch.setenv("RAIL_API_CONFIG_DIR", str(api_dir))
    monkeypatch.setenv("RAIL_CACHE_DIR", str(tmp_path / "cache"))

    import importlib
    import engine.api_runner
    importlib.reload(engine.api_runner)

    response = MagicMock()
    response.text = SCRAPE_HTML
    response.raise_for_status.return_value = None

    with patch("engine.api_runner.requests.get", return_value=response):
        run_pipeline(str(pipeline_yaml))

    w = _open_db(db_path)
    onto = w.get_ontology("http://example.org/test_minimal.owl").load()
    item_cls = next((c for c in onto.classes() if c.name == "Item"), None)
    items = list(item_cls.instances())
    assert len(items) == 2
    names = {getattr(i, "hasName", None) for i in items}
    assert names == {"Delta", "Epsilon"}


def test_run_pipeline_with_javascript_scrape_source(tmp_path, monkeypatch):
    onto_path = tmp_path / "ontology.yaml"
    onto_path.write_text(MINIMAL_ONTOLOGY)

    api_dir = tmp_path / "apis"
    api_dir.mkdir()
    (api_dir / "items.yaml").write_text(
        SCRAPE_API_YAML.replace("table_selector: table.data-table\n", "table_selector: table.data-table\njavascript: true\n")
    )

    output_owl = str(tmp_path / "out.owl")
    db_path = str(tmp_path / "onto.db")
    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(MINIMAL_PIPELINE.format(
        onto_path=str(onto_path),
        output_owl=output_owl,
        db_path=db_path,
    ))

    monkeypatch.setenv("RAIL_API_CONFIG_DIR", str(api_dir))
    monkeypatch.setenv("RAIL_CACHE_DIR", str(tmp_path / "cache"))

    import importlib
    import engine.api_runner
    importlib.reload(engine.api_runner)

    with patch("engine.scrape_runner.render_html", return_value=SCRAPE_HTML):
        run_pipeline(str(pipeline_yaml))

    w = _open_db(db_path)
    onto = w.get_ontology("http://example.org/test_minimal.owl").load()
    item_cls = next((c for c in onto.classes() if c.name == "Item"), None)
    assert len(list(item_cls.instances())) == 2


def test_run_pipeline_with_pdf_source(tmp_path, monkeypatch):
    onto_path = tmp_path / "ontology.yaml"
    onto_path.write_text(MINIMAL_ONTOLOGY)

    api_dir = tmp_path / "apis"
    api_dir.mkdir()
    (api_dir / "items.yaml").write_text(PDF_API_YAML)

    output_owl = str(tmp_path / "out.owl")
    db_path = str(tmp_path / "onto.db")
    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(MINIMAL_PIPELINE.format(
        onto_path=str(onto_path),
        output_owl=output_owl,
        db_path=db_path,
    ))

    monkeypatch.setenv("RAIL_API_CONFIG_DIR", str(api_dir))
    monkeypatch.setenv("RAIL_CACHE_DIR", str(tmp_path / "cache"))

    import importlib
    import engine.api_runner
    importlib.reload(engine.api_runner)

    table_df = pd.DataFrame([
        {"name": "Report A", "code": "R1"},
        {"name": "Report B", "code": "R2"},
    ])

    with patch("engine.api_runner._extract_document_tables", return_value=table_df):
        run_pipeline(str(pipeline_yaml))

    w = _open_db(db_path)
    onto = w.get_ontology("http://example.org/test_minimal.owl").load()
    item_cls = next((c for c in onto.classes() if c.name == "Item"), None)
    items = list(item_cls.instances())
    assert len(items) == 2
    names = {getattr(i, "hasName", None) for i in items}
    assert names == {"Report A", "Report B"}
