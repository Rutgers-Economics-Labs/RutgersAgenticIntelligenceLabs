"""
Tests for app.services.yaml_service — validation and parsing.
No external dependencies; all inputs are inline strings.
"""
import pytest
import sys
from pathlib import Path

# Ensure packages/api is on path BEFORE engine so FastAPI app/ wins over engine app.py
API_ROOT = str(Path(__file__).parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from pathlib import Path

from app.services.yaml_service import validate, parse, validate_pipeline_runnable

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "engine"
CORE_ONTOLOGY_YAML = (ENGINE_ROOT / "configs" / "ontology" / "core.yaml").read_text(encoding="utf-8")


# ── parse ─────────────────────────────────────────────────────────────────────

def test_parse_valid_yaml():
    result = parse("key: value\nlist:\n  - a\n  - b")
    assert result == {"key": "value", "list": ["a", "b"]}


def test_parse_invalid_yaml_raises():
    with pytest.raises(ValueError, match="Invalid YAML"):
        parse("key: [unclosed")


# ── validate api ──────────────────────────────────────────────────────────────

VALID_API_YAML = """
name: my_api
type: api
url: https://example.com/data
response_format: json
fields:
  - source: id
    alias: id
"""

def test_validate_api_valid():
    errors = validate("api", VALID_API_YAML)
    assert errors == []


def test_validate_api_missing_name():
    yaml = VALID_API_YAML.replace("name: my_api\n", "")
    errors = validate("api", yaml)
    assert any("name" in e for e in errors)


def test_validate_api_missing_type():
    yaml = VALID_API_YAML.replace("type: api\n", "")
    errors = validate("api", yaml)
    assert any("type" in e for e in errors)


def test_validate_api_invalid_type():
    yaml = VALID_API_YAML.replace("type: api", "type: graphql")
    errors = validate("api", yaml)
    assert any("Invalid type" in e for e in errors)


def test_validate_api_missing_url_for_api_type():
    yaml = VALID_API_YAML.replace("url: https://example.com/data\n", "")
    errors = validate("api", yaml)
    assert any("url" in e for e in errors)


def test_validate_api_missing_response_format():
    yaml = VALID_API_YAML.replace("response_format: json\n", "")
    errors = validate("api", yaml)
    assert any("response_format" in e for e in errors)


def test_validate_api_invalid_response_format():
    yaml = VALID_API_YAML.replace("response_format: json", "response_format: xml")
    errors = validate("api", yaml)
    assert any("Invalid response_format" in e for e in errors)


def test_validate_api_csv_requires_path():
    yaml = "name: my_csv\ntype: csv\n"
    errors = validate("api", yaml)
    assert any("path" in e for e in errors)


def test_validate_api_scrape_requires_url():
    yaml = "name: scraped\ntype: scrape\n"
    errors = validate("api", yaml)
    assert any("url" in e for e in errors)


def test_validate_api_scrape_javascript_must_be_bool():
    yaml = "name: scraped\ntype: scrape\nurl: https://example.com\njavascript: \"yes\"\n"
    errors = validate("api", yaml)
    assert any("javascript" in e for e in errors)


def test_validate_api_pdf_requires_exactly_one_of_path_or_url():
    yaml = "name: report\ntype: pdf\nextraction_mode: tables\n"
    errors = validate("api", yaml)
    assert any("exactly one of path, url, or storage_key" in e for e in errors)


def test_validate_api_docx_rejects_bad_pages_pattern():
    yaml = "name: report\ntype: docx\npath: /tmp/report.docx\nextraction_mode: tables\npages: first-three\n"
    errors = validate("api", yaml)
    assert any("pages must match pattern" in e for e in errors)


def test_validate_api_foreach_requires_source_and_field():
    yaml = VALID_API_YAML + "foreach:\n  inject_param: x\n"
    errors = validate("api", yaml)
    assert any("foreach.source" in e for e in errors)
    assert any("foreach.field" in e for e in errors)


def test_validate_api_computed_field_requires_alias():
    yaml = VALID_API_YAML + "  - computed: \"{a}_{b}\"\n"
    errors = validate("api", yaml)
    assert any("alias" in e for e in errors)


def test_validate_api_invalid_cast():
    yaml = VALID_API_YAML + "  - source: x\n    alias: x\n    cast: datetime\n"
    errors = validate("api", yaml)
    assert any("cast" in e for e in errors)


# ── validate ontology ─────────────────────────────────────────────────────────

VALID_ONTOLOGY_YAML = """
uri: http://example.org/test.owl
classes:
  - name: Thing
data_properties:
  - name: hasName
    range: str
"""

def test_validate_ontology_valid():
    errors = validate("ontology", VALID_ONTOLOGY_YAML)
    assert errors == []


def test_validate_ontology_missing_uri():
    yaml = VALID_ONTOLOGY_YAML.replace("uri: http://example.org/test.owl\n", "")
    errors = validate("ontology", yaml)
    assert any("uri" in e for e in errors)


def test_validate_ontology_class_missing_name():
    yaml = "uri: http://example.org/t.owl\nclasses:\n  - label: X\n"
    errors = validate("ontology", yaml)
    assert any("name" in e for e in errors)


def test_validate_ontology_invalid_range():
    yaml = VALID_ONTOLOGY_YAML.replace("range: str", "range: datetime")
    errors = validate("ontology", yaml)
    assert any("range" in e for e in errors)


# ── validate pipeline ─────────────────────────────────────────────────────────

VALID_PIPELINE_YAML = """
ontology: configs/ontology/core.yaml
steps:
  - name: load_things
    api: my_api
    class: Thing
    uri: "Thing_{id}"
    properties:
      hasName: "{name}"
"""

def test_validate_pipeline_valid():
    errors = validate("pipeline", VALID_PIPELINE_YAML)
    assert errors == []


def test_validate_pipeline_missing_ontology():
    yaml = VALID_PIPELINE_YAML.replace("ontology: configs/ontology/core.yaml\n", "")
    errors = validate("pipeline", yaml)
    assert any("ontology" in e for e in errors)


def test_validate_pipeline_missing_steps():
    yaml = "ontology: configs/ontology/core.yaml\n"
    errors = validate("pipeline", yaml)
    assert any("steps" in e for e in errors)


def test_validate_pipeline_step_missing_required_fields():
    yaml = "ontology: x\nsteps:\n  - name: s\n    api: a\n"
    errors = validate("pipeline", yaml)
    assert any("class" in e for e in errors)
    assert any("uri" in e for e in errors)


def test_validate_pipeline_relationship_missing_fields():
    yaml = (
        "ontology: x\nsteps:\n"
        "  - name: s\n    api: a\n    class: C\n    uri: 'X_{id}'\n"
        "    relationships:\n      - property: p\n"
    )
    errors = validate("pipeline", yaml)
    assert any("target_class" in e for e in errors)
    assert any("target_uri" in e for e in errors)


# ── bad YAML propagates through validate ─────────────────────────────────────

def test_validate_returns_parse_error_on_bad_yaml():
    errors = validate("api", "key: [unclosed")
    assert len(errors) == 1
    assert "Invalid YAML" in errors[0]


# ── validate_pipeline_runnable (deep) ─────────────────────────────────────────

_MIN_CSV_API = """
name: child_api
type: csv
path: sources/child.csv
foreach:
  source: parent_api
  field: id
fields:
  - source: x
    alias: x
"""

_MIN_PARENT_API = """
name: parent_api
type: csv
path: sources/parent.csv
fields:
  - source: id
    alias: id
"""


def test_validate_pipeline_runnable_ok():
    pipe = """
ontology: core
steps:
  - name: first
    api: parent_api
    class: State
    uri: "State_{id}"
    properties:
      hasName: "{id}"
  - name: second
    api: child_api
    class: County
    uri: "County_{id}"
"""
    errs = validate_pipeline_runnable(
        pipe,
        {"parent_api": _MIN_PARENT_API, "child_api": _MIN_CSV_API},
        ontology_yaml=CORE_ONTOLOGY_YAML,
        engine_root=ENGINE_ROOT,
        transform_dir=ENGINE_ROOT / "transforms",
    )
    assert errs == []


def test_validate_pipeline_runnable_foreach_order():
    pipe = """
ontology: core
steps:
  - name: second_first
    api: child_api
    class: State
    uri: "State_{id}"
  - name: parent_late
    api: parent_api
    class: State
    uri: "State_{id}"
"""
    errs = validate_pipeline_runnable(
        pipe,
        {"parent_api": _MIN_PARENT_API, "child_api": _MIN_CSV_API},
        ontology_yaml=CORE_ONTOLOGY_YAML,
        engine_root=ENGINE_ROOT,
        transform_dir=ENGINE_ROOT / "transforms",
    )
    assert any("foreach source" in e for e in errs)


def test_validate_pipeline_runnable_unknown_class():
    pipe = """
ontology: core
steps:
  - name: s
    api: parent_api
    class: NotInOntology
    uri: "X_{id}"
"""
    errs = validate_pipeline_runnable(
        pipe,
        {"parent_api": _MIN_PARENT_API},
        ontology_yaml=CORE_ONTOLOGY_YAML,
        engine_root=ENGINE_ROOT,
        transform_dir=ENGINE_ROOT / "transforms",
    )
    assert any("NotInOntology" in e for e in errs)


def test_validate_pipeline_runnable_missing_api_yaml():
    pipe = """
ontology: core
steps:
  - name: s
    api: missing_slug
    class: State
    uri: "State_{id}"
"""
    errs = validate_pipeline_runnable(
        pipe,
        {},
        ontology_yaml=CORE_ONTOLOGY_YAML,
        engine_root=ENGINE_ROOT,
        transform_dir=ENGINE_ROOT / "transforms",
    )
    assert any("missing_slug" in e for e in errs)
