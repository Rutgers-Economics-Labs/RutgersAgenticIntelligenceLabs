from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml


ConfigKind = Literal["apis", "ontologies", "pipelines"]


@dataclass(frozen=True)
class RepoFile:
    path: str
    content: str


CURRENT_PATHS = {
    "ontology_root": ".ontology",
    "ontology_dir": ".ontology/ontologies",
    "sources_dir": ".ontology/sources",
    "pipelines_dir": ".ontology/pipelines",
    "transforms_dir": ".ontology/transforms",
}

LEGACY_PREFIXES = {
    "apis": "configs/apis",
    "ontologies": "configs/ontology",
    "pipelines": "configs/pipelines",
}


def infer_github_repo(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith("git@github.com:"):
        repo = normalized.removeprefix("git@github.com:").removesuffix(".git")
        return repo or None
    if normalized.startswith("https://github.com/") or normalized.startswith("http://github.com/"):
        parsed = urlparse(normalized)
        repo = parsed.path.strip("/").removesuffix(".git")
        parts = repo.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2])
    if normalized.count("/") == 1 and " " not in normalized:
        return normalized
    return None


def default_manifest(project: dict[str, Any]) -> dict[str, Any]:
    slug = project["slug"]
    return {
        "version": 1,
        "project": {
            "name": project["name"],
            "slug": slug,
            "default_branch": project.get("defaultBranch") or "main",
            "description": project.get("description") or "RAIL project",
            "mode": "ontology_first",
        },
        "repo_contract": {
            "required_paths": [".ontology", "specs", "research_plan", "topics", "agents", "skills"],
            "flexible_paths": ["artifacts", "topics/**"],
            "source_of_truth": "git",
        },
        "paths": {
            "ontology_root": CURRENT_PATHS["ontology_root"],
            "topics_root": "topics",
            "specs_root": "specs",
            "plan_root": "research_plan",
            "agents_root": "agents",
            "skills_root": "skills",
            "artifacts_root": "artifacts",
        },
        "hydration": {
            "ontology_file": f"{CURRENT_PATHS['ontology_dir']}/{project['ontologyConfigSlug']}.yaml"
            if project.get("ontologyConfigSlug")
            else f"{CURRENT_PATHS['ontology_root']}/ontology.yaml",
            "sources_dir": CURRENT_PATHS["sources_dir"],
            "pipelines_dir": CURRENT_PATHS["pipelines_dir"],
            "transforms_dir": CURRENT_PATHS["transforms_dir"],
            "default_pipeline": project.get("pipelineConfigSlug"),
            "linked_sources": project.get("apiConfigSlugs") or [],
            "hydration_mode": "full",
        },
        "research": {
            "brief_path": "topics/brief.md",
            "spec_path": "specs/research_question.yaml",
            "question_policy": {
                "allow_follow_up_generation": True,
                "allow_midstream_direction_change": True,
                "require_question_classification": True,
                "allowed_classifications": [
                    "answerable_now",
                    "answerable_after_requery",
                    "answerable_after_expansion",
                    "blocked_by_data",
                ],
            },
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
            "approval_required_for_write_runs": True,
            "planner_thread_mode": "project",
            "default_planner_role": "planner",
        },
        "auditors": {
            "enabled": True,
            "order": ["session", "planner", "ontology", "integrity", "closeout"],
            "fail_closed": True,
        },
        "autonomy": {
            "mode": "assisted",
            "require_human_for": [
                "publish_changes",
                "destructive_delete",
                "missing_source_data",
                "low_confidence_claims",
                "methodology_change_with_material_effect",
            ],
            "allow_without_human": [
                "plan_decomposition",
                "source_discovery",
                "data_ingestion",
                "analysis_scripts",
                "artifact_generation",
                "verification",
                "assumption_recording",
            ],
            "max_runtime_minutes": 180,
            "max_cost_usd": 20,
            "max_retries_per_task": 3,
        },
        "integrity": {
            "allow_synthetic_data": False,
            "require_source_for_datasets": True,
            "require_lineage_for_final_artifacts": True,
            "require_evidence_for_report_claims": True,
            "stale_outputs_block_promotion": True,
        },
        "verification": {
            "deterministic_command": "scripts/run-verification.sh",
            "require_integrity_gate_for": ["artifact_generation", "closeout"],
            "require_ontology_health_before": ["research", "artifact"],
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
            "phases": [
                "brief",
                "scoped",
                "source_discovery",
                "config_ready",
                "hydration_ready",
                "hydrated",
                "ontology_healthy",
                "research_active",
                "synthesis_ready",
                "closed",
            ],
            "closeout_requires": [
                "no_active_agents",
                "no_non_done_required_tasks",
                "clean_integrity_gate",
                "final_artifacts_present",
            ],
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


def _load_yaml_dict(content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    parsed = yaml.safe_load(content) or {}
    return parsed if isinstance(parsed, dict) else {}


def render_rail_manifest(project: dict[str, Any], existing_content: str | None = None) -> str:
    manifest = default_manifest(project)
    if existing_content:
        existing = _load_yaml_dict(existing_content)
        manifest = _deep_merge(manifest, existing)

    manifest.setdefault("project", {})
    manifest["project"]["name"] = project["name"]
    manifest["project"]["slug"] = project["slug"]
    manifest["project"]["default_branch"] = project.get("defaultBranch") or "main"
    manifest["project"].setdefault("mode", "ontology_first")
    if project.get("description"):
        manifest["project"]["description"] = project["description"]

    repo_contract = manifest.setdefault("repo_contract", {})
    repo_contract.setdefault("required_paths", [".ontology", "specs", "research_plan", "topics", "agents", "skills"])
    repo_contract.setdefault("flexible_paths", ["artifacts", "topics/**"])
    repo_contract.setdefault("source_of_truth", "git")

    manifest.setdefault("paths", {})
    manifest["paths"].setdefault("ontology_root", CURRENT_PATHS["ontology_root"])
    manifest["paths"].setdefault("topics_root", "topics")
    manifest["paths"].setdefault("specs_root", "specs")
    manifest["paths"].setdefault("plan_root", "research_plan")
    manifest["paths"].setdefault("agents_root", "agents")
    manifest["paths"].setdefault("skills_root", "skills")
    manifest["paths"].setdefault("artifacts_root", "artifacts")
    manifest["paths"].pop("scripts_root", None)

    hydration = manifest.setdefault("hydration", {})
    hydration["sources_dir"] = hydration.get("sources_dir") or CURRENT_PATHS["sources_dir"]
    hydration["pipelines_dir"] = hydration.get("pipelines_dir") or CURRENT_PATHS["pipelines_dir"]
    hydration["transforms_dir"] = hydration.get("transforms_dir") or CURRENT_PATHS["transforms_dir"]
    hydration["hydration_mode"] = hydration.get("hydration_mode") or "full"
    hydration["default_pipeline"] = project.get("pipelineConfigSlug")
    hydration["linked_sources"] = list(project.get("apiConfigSlugs") or [])
    if project.get("ontologyConfigSlug"):
        hydration["ontology_file"] = f"{CURRENT_PATHS['ontology_dir']}/{project['ontologyConfigSlug']}.yaml"
    else:
        hydration["ontology_file"] = hydration.get("ontology_file") or f"{CURRENT_PATHS['ontology_root']}/ontology.yaml"

    research = manifest.setdefault("research", {})
    research.setdefault("brief_path", "topics/brief.md")
    research.setdefault("spec_path", "specs/research_question.yaml")
    question_policy = research.setdefault("question_policy", {})
    question_policy.setdefault("allow_follow_up_generation", True)
    question_policy.setdefault("allow_midstream_direction_change", True)
    question_policy.setdefault("require_question_classification", True)
    question_policy.setdefault("allowed_classifications", [
        "answerable_now",
        "answerable_after_requery",
        "answerable_after_expansion",
        "blocked_by_data",
    ])

    planner = manifest.setdefault("planner", {})
    planner.setdefault("current_plan_path", "research_plan/current_plan.md")
    planner.setdefault("task_root", "research_plan/tasks")
    planner.setdefault("approval_root", "research_plan/approvals")
    planner.setdefault("decision_root", "research_plan/decisions")
    planner.setdefault("require_audit_before_advance", True)
    planner.setdefault("lane_policy", "single_active_worker")

    workspaces = manifest.setdefault("workspaces", {})
    workspaces.setdefault("mode", "isolated")
    workspaces.setdefault("root", ".rail/workspaces")
    workspaces.setdefault("setup_script", "scripts/setup-workspace.sh")
    workspaces.setdefault("verification_script", "scripts/run-verification.sh")
    workspaces.setdefault("archive_script", "scripts/archive-workspace.sh")
    workspaces.setdefault("nonconcurrent_run", True)
    workspaces.setdefault("checkpoint_mode", "git-ref")

    autonomy = manifest.setdefault("autonomy", {})
    autonomy.setdefault("mode", "assisted")
    autonomy.setdefault("require_human_for", [
        "publish_changes",
        "destructive_delete",
        "missing_source_data",
        "low_confidence_claims",
        "methodology_change_with_material_effect",
    ])
    autonomy.setdefault("allow_without_human", [
        "plan_decomposition",
        "source_discovery",
        "data_ingestion",
        "analysis_scripts",
        "artifact_generation",
        "verification",
        "assumption_recording",
    ])
    autonomy.setdefault("max_runtime_minutes", 180)
    autonomy.setdefault("max_cost_usd", 20)
    autonomy.setdefault("max_retries_per_task", 3)

    auditors = manifest.setdefault("auditors", {})
    auditors.setdefault("enabled", True)
    auditors.setdefault("order", ["session", "planner", "ontology", "integrity", "closeout"])
    auditors.setdefault("fail_closed", True)

    integrity = manifest.setdefault("integrity", {})
    integrity.setdefault("allow_synthetic_data", False)
    integrity.setdefault("require_source_for_datasets", True)
    integrity.setdefault("require_lineage_for_final_artifacts", True)
    integrity.setdefault("require_evidence_for_report_claims", True)
    integrity.setdefault("stale_outputs_block_promotion", True)

    verification = manifest.setdefault("verification", {})
    verification.setdefault("deterministic_command", "scripts/run-verification.sh")
    verification.setdefault("require_integrity_gate_for", ["artifact_generation", "closeout"])
    verification.setdefault("require_ontology_health_before", ["research", "artifact"])
    verification.setdefault("required_artifact_lineage", True)
    verification.setdefault("required_claim_evidence", True)

    secrets = manifest.setdefault("secrets", {})
    secrets.setdefault("project_scope", True)
    secrets.setdefault("per_agent_allowlists", True)
    secrets.setdefault("inject_at_session_start_only", True)
    secrets.setdefault("allowed", {})

    lifecycle = manifest.setdefault("lifecycle", {})
    lifecycle.setdefault("phases", [
        "brief",
        "scoped",
        "source_discovery",
        "config_ready",
        "hydration_ready",
        "hydrated",
        "ontology_healthy",
        "research_active",
        "synthesis_ready",
        "closed",
    ])
    lifecycle.setdefault("closeout_requires", [
        "no_active_agents",
        "no_non_done_required_tasks",
        "clean_integrity_gate",
        "final_artifacts_present",
    ])

    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=False)


def build_config_files(kind: ConfigKind, slug: str, content: str) -> list[RepoFile]:
    current_prefix = {
        "apis": CURRENT_PATHS["sources_dir"],
        "ontologies": CURRENT_PATHS["ontology_dir"],
        "pipelines": CURRENT_PATHS["pipelines_dir"],
    }[kind]
    legacy_prefix = LEGACY_PREFIXES[kind]
    return [
        RepoFile(path=f"{current_prefix}/{slug}.yaml", content=content),
        RepoFile(path=f"{legacy_prefix}/{slug}.yaml", content=content),
    ]


def parse_config_path(path: str) -> tuple[ConfigKind, str] | None:
    normalized = path.strip("/")
    prefixes: list[tuple[str, ConfigKind]] = [
        (f"{CURRENT_PATHS['sources_dir']}/", "apis"),
        (f"{CURRENT_PATHS['ontology_dir']}/", "ontologies"),
        (f"{CURRENT_PATHS['pipelines_dir']}/", "pipelines"),
        ("configs/apis/", "apis"),
        ("configs/ontology/", "ontologies"),
        ("configs/pipelines/", "pipelines"),
    ]
    for prefix, kind in prefixes:
        if normalized.startswith(prefix) and normalized.endswith(".yaml"):
            slug = normalized.removeprefix(prefix).removesuffix(".yaml")
            if slug:
                return kind, slug
    return None


def dedupe_changed_paths(paths: list[str]) -> list[str]:
    preferred: dict[tuple[str, str], str] = {}
    for path in paths:
        parsed = parse_config_path(path)
        if not parsed:
            preferred[(path, "")] = path
            continue
        kind, slug = parsed
        key = (kind, slug)
        existing = preferred.get(key)
        if existing is None or path.startswith(".ontology/"):
            preferred[key] = path
    unique = list(preferred.values())
    if "rail.yaml" in paths and "rail.yaml" not in unique:
        unique.append("rail.yaml")
    return unique


def manifest_updates_from_content(content: str) -> dict[str, Any]:
    parsed = _load_yaml_dict(content)
    project_section = parsed.get("project") or {}
    hydration = parsed.get("hydration") or {}
    updates: dict[str, Any] = {}

    if project_section.get("name"):
        updates["name"] = project_section["name"]
    if project_section.get("description") is not None:
        updates["description"] = project_section["description"]
    if project_section.get("default_branch"):
        updates["defaultBranch"] = project_section["default_branch"]

    default_pipeline = hydration.get("default_pipeline")
    if isinstance(default_pipeline, str) and default_pipeline.strip():
        updates["pipelineConfigSlug"] = default_pipeline.strip()

    ontology_file = hydration.get("ontology_file")
    ontology_slug = slug_from_ontology_file(ontology_file)
    if ontology_slug:
        updates["ontologyConfigSlug"] = ontology_slug

    linked_sources = hydration.get("linked_sources")
    if isinstance(linked_sources, list) and all(isinstance(item, str) for item in linked_sources):
        updates["apiConfigSlugs"] = linked_sources

    return updates


def slug_from_ontology_file(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip()
    if normalized.startswith(f"{CURRENT_PATHS['ontology_dir']}/") and normalized.endswith(".yaml"):
        return Path(normalized).stem
    if normalized.startswith("configs/ontology/") and normalized.endswith(".yaml"):
        return Path(normalized).stem
    return None


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
