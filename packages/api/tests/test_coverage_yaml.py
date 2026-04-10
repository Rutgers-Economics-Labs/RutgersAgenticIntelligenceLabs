import pytest
from app.services import yaml_service

def test_validate_coverage_valid():
    yaml_str = """
project: test_project
overrides:
  - class: Person
    status: sparse
  - class: LaborIndicator
    status: verified
"""
    parsed = yaml_service.parse(yaml_str)
    errors = yaml_service._validate_coverage(parsed)
    assert not errors

def test_validate_coverage_missing_overrides():
    yaml_str = """
project: test_project
"""
    parsed = yaml_service.parse(yaml_str)
    errors = yaml_service._validate_coverage(parsed)
    assert "Missing required field: overrides" in errors

def test_validate_coverage_invalid_status():
    yaml_str = """
project: test_project
overrides:
  - class: Person
    status: unknown
"""
    parsed = yaml_service.parse(yaml_str)
    errors = yaml_service._validate_coverage(parsed)
    assert any("invalid status" in err and "must be sparse or verified" in err for err in errors)

def test_validate_coverage_unknown_field():
    yaml_str = """
project: test_project
extra_field: true
overrides:
  - class: Person
    status: sparse
"""
    parsed = yaml_service.parse(yaml_str)
    errors = yaml_service._validate_coverage(parsed)
    assert any("Unknown field: extra_field" in err for err in errors)
