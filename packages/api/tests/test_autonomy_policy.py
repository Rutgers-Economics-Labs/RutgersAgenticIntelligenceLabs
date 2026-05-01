from __future__ import annotations

import pytest

from app.services.autonomy_policy import activity_key_for_role, evaluate_autonomy_policy, is_write_capable
from app.services.role_runtime_service import load_role_runtime_config
from rail.bootstrap import bootstrap_future_project


def test_assisted_mode_requires_approval_for_write_capable_worker(tmp_path):
    bootstrap_future_project(tmp_path, name="Policy Project")
    project = {"slug": "policy-project", "localRepoPath": str(tmp_path)}
    role_config = load_role_runtime_config(project, "research")

    decision = evaluate_autonomy_policy(
        role_config.manifest,
        action=activity_key_for_role(role_config.role),
        write_capable=is_write_capable(role_policy=role_config.policy),
    )

    assert decision.requires_human_approval is True
    assert decision.status == "awaiting_approval"
    assert decision.boundary == "write_capable_run"


def test_supervised_autopilot_allows_routine_worker_run(tmp_path):
    bootstrap_future_project(tmp_path, name="Policy Project")
    rail_yaml = (tmp_path / "rail.yaml").read_text(encoding="utf-8").replace(
        '  mode: "assisted"',
        '  mode: "supervised_autopilot"',
    )
    (tmp_path / "rail.yaml").write_text(rail_yaml, encoding="utf-8")
    project = {"slug": "policy-project", "localRepoPath": str(tmp_path)}
    role_config = load_role_runtime_config(project, "coding")

    decision = evaluate_autonomy_policy(
        role_config.manifest,
        action=activity_key_for_role(role_config.role),
        write_capable=is_write_capable(role_policy=role_config.policy),
    )

    assert decision.allowed is True
    assert decision.requires_human_approval is False
    assert decision.status == "ready"


def test_autopilot_escalates_when_action_is_policy_boundary(tmp_path):
    bootstrap_future_project(tmp_path, name="Policy Project")
    rail_yaml = (tmp_path / "rail.yaml").read_text(encoding="utf-8").replace(
        '  mode: "assisted"',
        '  mode: "autopilot"',
    )
    (tmp_path / "rail.yaml").write_text(rail_yaml, encoding="utf-8")
    project = {"slug": "policy-project", "localRepoPath": str(tmp_path)}
    role_config = load_role_runtime_config(project, "artifact")

    decision = evaluate_autonomy_policy(
        role_config.manifest,
        action="publish_changes",
        write_capable=is_write_capable(role_policy=role_config.policy),
    )

    assert decision.requires_human_approval is True
    assert decision.boundary == "publish_changes"


def test_autopilot_blocks_when_budget_exceeded(tmp_path):
    bootstrap_future_project(tmp_path, name="Policy Project")
    rail_yaml = (tmp_path / "rail.yaml").read_text(encoding="utf-8").replace(
        '  mode: "assisted"',
        '  mode: "autopilot"',
    )
    (tmp_path / "rail.yaml").write_text(rail_yaml, encoding="utf-8")
    project = {"slug": "policy-project", "localRepoPath": str(tmp_path)}
    role_config = load_role_runtime_config(project, "data")

    decision = evaluate_autonomy_policy(
        role_config.manifest,
        action=activity_key_for_role(role_config.role),
        write_capable=is_write_capable(role_policy=role_config.policy),
        budget_exceeded=True,
    )

    assert decision.blocked is True
    assert decision.status == "blocked"
    assert decision.boundary == "budget_exceeded"
