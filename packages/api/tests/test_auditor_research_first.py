"""Ontology auditor behavior for research_first projects."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml


def test_research_first_project_skips_ontology_hydration_gate(tmp_path: Path):
    from app.services.auditor_service import audit_ontology_health, build_auditor_statuses

    project_root = tmp_path / "lit"
    project_root.mkdir()
    (project_root / "artifacts").mkdir()
    (project_root / "artifacts" / "literature_review.md").write_text("# Review\n", encoding="utf-8")
    rail = {
        "version": 1,
        "project": {
            "name": "Lit",
            "slug": "lit-review",
            "default_branch": "main",
            "mode": "research_first",
        },
        "repo_contract": {
            "required_paths": ["research_plan", "artifacts", "agents", "skills", "specs", "topics"],
            "flexible_paths": [],
            "source_of_truth": "git",
        },
        "paths": {
            "ontology_root": ".ontology",
            "topics_root": "topics",
            "specs_root": "specs",
            "plan_root": "research_plan",
            "agents_root": "agents",
            "skills_root": "skills",
            "artifacts_root": "artifacts",
        },
        "hydration": {
            "ontology_file": ".ontology/ontology.yaml",
            "sources_dir": ".ontology/sources",
            "pipelines_dir": ".ontology/pipelines",
            "transforms_dir": ".ontology/transforms",
            "default_pipeline": "project-default",
            "hydration_mode": "full",
        },
        "planner": {
            "current_plan_path": "research_plan/current_plan.md",
            "task_root": "research_plan/tasks",
            "approval_root": "research_plan/approvals",
            "decision_root": "research_plan/decisions",
            "require_audit_before_advance": True,
            "lane_policy": "single_active_worker",
        },
        "agents": {
            "roles_dir": "agents",
            "default_runner": "codex_cli",
            "sequential_execution": True,
            "planner_thread_mode": "project",
            "default_planner_role": "planner",
        },
        "auditors": {
            "enabled": True,
            "order": ["session", "planner", "ontology", "integrity", "closeout"],
            "fail_closed": True,
        },
        "autonomy": {"mode": "assisted", "require_human_for": [], "allow_without_human": []},
        "integrity": {
            "allow_synthetic_data": False,
            "require_source_for_datasets": True,
            "require_lineage_for_final_artifacts": True,
            "require_evidence_for_report_claims": True,
            "stale_outputs_block_promotion": True,
        },
        "verification": {
            "deterministic_command": "scripts/run-verification.sh",
            "require_integrity_gate_for": ["closeout"],
            "require_ontology_health_before": [],
            "required_artifact_lineage": True,
            "required_claim_evidence": True,
        },
        "secrets": {
            "project_scope": True,
            "per_agent_allowlists": True,
            "inject_at_session_start_only": True,
            "allowed": {},
        },
        "lifecycle": {
            "phases": ["brief", "scoped", "research_active", "closed"],
            "closeout_requires": ["final_artifacts_present"],
        },
        "workspaces": {
            "mode": "isolated",
            "root": ".rail/workspaces",
            "setup_script": "scripts/setup-workspace.sh",
            "verification_script": "scripts/run-verification.sh",
            "archive_script": "scripts/archive-workspace.sh",
            "nonconcurrent_run": True,
            "checkpoint_mode": "git-ref",
        },
        "frontend": {
            "topic_index_mode": "filesystem",
            "artifact_index_mode": "filesystem",
            "show_repo_tree": True,
            "show_task_board_snapshot": True,
            "default_home_view": "project_home",
        },
    }
    (project_root / "rail.yaml").write_text(yaml.safe_dump(rail), encoding="utf-8")
    for rel in ["research_plan", "research_plan/state", "research_plan/tasks", "agents", "skills", "specs", "topics"]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)
    (project_root / "research_plan" / "state" / "sources.json").write_text("[]", encoding="utf-8")
    (project_root / "research_plan" / "state" / "claims.json").write_text("[]", encoding="utf-8")
    (project_root / "research_plan" / "state" / "artifact_lineage.json").write_text("[]", encoding="utf-8")

    project = {"_id": "p1", "localRepoPath": str(project_root), "slug": "lit-review"}

    health = asyncio.run(audit_ontology_health(project))
    assert health["state"] == "not_applicable"
    assert health["healthy"] is True
    assert health["blockers"] == []

    statuses = asyncio.run(
        build_auditor_statuses(
            project,
            tasks=[{"_id": "t1", "title": "Write review", "status": "done"}],
            active_sessions=[],
        )
    )
    assert statuses["ontology"]["status"] == "ready"
