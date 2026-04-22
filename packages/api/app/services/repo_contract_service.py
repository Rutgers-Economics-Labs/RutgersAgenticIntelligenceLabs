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
        "agents": {
            "roles_dir": "agents",
            "default_runner": "jules",
            "sequential_execution": True,
            "approval_required_for_write_runs": True,
            "planner_thread_mode": "project",
            "default_planner_role": "planner",
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
    if project.get("description"):
        manifest["project"]["description"] = project["description"]

    manifest.setdefault("paths", {})
    manifest["paths"].setdefault("ontology_root", CURRENT_PATHS["ontology_root"])
    manifest["paths"].setdefault("topics_root", "topics")
    manifest["paths"].setdefault("specs_root", "specs")
    manifest["paths"].setdefault("plan_root", "research_plan")
    manifest["paths"].setdefault("agents_root", "agents")
    manifest["paths"].setdefault("skills_root", "skills")
    manifest["paths"].setdefault("artifacts_root", "artifacts")

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
