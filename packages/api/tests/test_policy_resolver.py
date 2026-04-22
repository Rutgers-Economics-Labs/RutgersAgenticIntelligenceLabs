import pytest

from app.services.policy_resolver import (
    resolve_runner_policy,
    resolve_path_policy,
    resolve_secret_policy,
    resolve_skill_policy,
    resolve_tool_policy,
    resolve_completion_policy,
    resolve_role_policy,
    RunnerPolicy,
    PathPolicy,
    SecretPolicy,
    SkillPolicy,
    ToolPolicy,
    CompletionPolicy,
    RuntimePolicy
)

def test_resolve_runner_policy():
    policy = resolve_runner_policy(None)
    assert isinstance(policy, RunnerPolicy)
    assert policy.default == "jules"
    assert policy.approval_required is True
    assert policy.bash_access is True

    policy = resolve_runner_policy({"default": "gemini_cli", "approval_required": False, "bash_access": False})
    assert policy.default == "gemini_cli"
    assert policy.approval_required is False
    assert policy.bash_access is False

def test_resolve_path_policy():
    # Empty
    policy = resolve_path_policy(None)
    assert policy.read == []
    assert policy.write == []
    assert policy.deny == []

    # Partial
    policy = resolve_path_policy({"read": ["a"], "deny": ["b"]})
    assert policy.read == ["a"]
    assert policy.write == []
    assert policy.deny == ["b"]

    # Full
    policy = resolve_path_policy({"read": ["a"], "write": ["b"], "deny": ["c"]})
    assert policy.read == ["a"]
    assert policy.write == ["b"]
    assert policy.deny == ["c"]

def test_resolve_secret_policy():
    # Empty
    policy = resolve_secret_policy(None)
    assert policy.allow == []

    # Full
    policy = resolve_secret_policy({"allow": ["FRED_API_KEY"]})
    assert policy.allow == ["FRED_API_KEY"]

def test_resolve_tool_policy():
    # Empty
    policy = resolve_tool_policy(None)
    assert policy.allow == []
    assert policy.deny == []

    # Partial
    policy = resolve_tool_policy({"allow": ["read_repo"]})
    assert policy.allow == ["read_repo"]
    assert policy.deny == []

    # Full
    policy = resolve_tool_policy({"allow": ["read_repo"], "deny": ["publish_changes"]})
    assert policy.allow == ["read_repo"]
    assert policy.deny == ["publish_changes"]

def test_resolve_completion_policy():
    # Empty
    policy = resolve_completion_policy(None)
    assert policy.requires == []

    # Full
    policy = resolve_completion_policy({"requires": ["yaml_valid"]})
    assert policy.requires == ["yaml_valid"]

def test_resolve_skill_policy():
    policy = resolve_skill_policy(None, "planner")
    assert isinstance(policy, SkillPolicy)
    assert policy.allow_use is True

    policy = resolve_skill_policy({"allow_use": False}, "planner")
    assert policy.allow_use is False

def test_resolve_role_policy():
    # Empty
    policy = resolve_role_policy({})
    assert isinstance(policy, RuntimePolicy)
    assert policy.runner.default == "jules"
    assert policy.paths.read == []
    assert policy.secrets.allow == []
    assert policy.tools.allow == []
    assert policy.completion.requires == []
    assert policy.skills.allow_use is False

    # Full config
    config = {
        "role": "planner",
        "runner": {
            "default": "claude_code",
            "approval_required": True,
            "bash_access": True,
        },
        "permissions": {
            "read": [".ontology"],
            "write": [".ontology/sources"],
            "deny": ["agents"]
        },
        "secrets": {
            "allow": ["FRED_API_KEY"]
        },
        "tools": {
            "allow": ["read_repo"],
            "deny": ["publish_changes"]
        },
        "completion": {
            "requires": ["yaml_valid"]
        },
        "skills": {
            "allow_use": True
        }
    }

    policy = resolve_role_policy(config)
    assert policy.runner.default == "claude_code"
    assert policy.paths.read == [".ontology"]
    assert policy.paths.write == [".ontology/sources"]
    assert policy.paths.deny == ["agents"]
    assert policy.secrets.allow == ["FRED_API_KEY"]
    assert policy.tools.allow == ["read_repo"]
    assert policy.tools.deny == ["publish_changes"]
    assert policy.completion.requires == ["yaml_valid"]
    assert policy.skills.allow_use is True
