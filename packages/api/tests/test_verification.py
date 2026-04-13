import pytest
from pathlib import Path
from app.services.verification import verify_config, verify_path_policy, verify_execution, verify_artifact
from app.services.policy_resolver import RuntimePolicy, PathPolicy, SecretPolicy, ToolPolicy, CompletionPolicy

def test_verify_config():
    res = verify_config("api", "invalid yaml [")
    assert res.passed is False
    assert len(res.errors) > 0

    valid_api = """
name: test
type: api
url: http://test.com
description: a test api
response_format: json
"""
    res = verify_config("api", valid_api)
    assert res.passed is True
    assert len(res.errors) == 0

def test_verify_path_policy():
    policy = RuntimePolicy(
        paths=PathPolicy(write=[".ontology/sources", "artifacts"], deny=["agents"]),
        secrets=SecretPolicy(),
        tools=ToolPolicy(),
        completion=CompletionPolicy()
    )

    # Valid write
    res = verify_path_policy([".ontology/sources/source1.yaml"], policy)
    assert res.passed is True

    # Invalid write (outside allowed)
    res = verify_path_policy(["specs/something.md"], policy)
    assert res.passed is False
    assert "Path modified outside allowed write locations: specs/something.md" in res.errors

    # Invalid write (denied location)
    res = verify_path_policy(["agents/data.yaml"], policy)
    assert res.passed is False
    assert "Path modified in denied location: agents/data.yaml" in res.errors

def test_verify_execution(tmp_path):
    policy = RuntimePolicy(
        paths=PathPolicy(write=["outputs"]),
        secrets=SecretPolicy(),
        tools=ToolPolicy(),
        completion=CompletionPolicy()
    )

    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs/result.txt").write_text("done")

    # Missing output
    res = verify_execution("script.py", ["outputs/missing.txt"], tmp_path, policy)
    assert res.passed is False
    assert "Expected output file not found: outputs/missing.txt" in res.errors

    # Good output
    res = verify_execution("script.py", ["outputs/result.txt"], tmp_path, policy)
    assert res.passed is True

def test_verify_artifact(tmp_path):
    policy = RuntimePolicy(
        paths=PathPolicy(write=["artifacts"]),
        secrets=SecretPolicy(),
        tools=ToolPolicy(),
        completion=CompletionPolicy()
    )

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/data.json").write_text("{}")

    res = verify_artifact(["artifacts/data.json"], tmp_path, policy)
    assert res.passed is True

    res = verify_artifact(["artifacts/missing.json"], tmp_path, policy)
    assert res.passed is False
    assert "Required artifact file not found: artifacts/missing.json" in res.errors
