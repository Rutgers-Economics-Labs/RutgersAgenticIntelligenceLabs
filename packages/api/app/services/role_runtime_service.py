from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rail.manifest import load_manifest

from app.services.policy_resolver import RuntimePolicy, resolve_role_policy
from app.services.yaml_service import load_agent_prompts, parse


SUPPORTED_RUNNERS = {"jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli"}
ROLE_ALIASES = {
    "researcher": "research",
    "analyst": "data",
    "developer": "coding",
    "engineer": "coding",
    "auditor": "health",
}


@dataclass
class RoleRuntimeConfig:
    role: str
    label: str
    purpose: str
    policy: RuntimePolicy
    system_prompt: str
    checklist_prompt: str
    config_path: Path
    project_root: Path
    manifest: Any
    raw_config: dict[str, Any]


def _project_root(project: dict[str, Any]) -> Path:
    root = project.get("localRepoPath")
    if not root:
        raise ValueError("Project does not have a localRepoPath configured")
    path = Path(root).resolve()
    if not path.is_dir():
        raise ValueError(f"Project repo path does not exist: {path}")
    return path


def _role_path(project_root: Path, manifest: Any, role: str) -> Path:
    normalized_role = ROLE_ALIASES.get(role, role)
    return project_root / manifest.agents.roles_dir / f"{normalized_role}.yaml"


def _normalize_runner_name(name: str | None, default_name: str) -> str:
    normalized = (name or default_name or "jules").strip()
    if normalized not in SUPPORTED_RUNNERS:
        return default_name
    return normalized


def load_role_runtime_config(project: dict[str, Any], role: str) -> RoleRuntimeConfig:
    project_root = _project_root(project)
    manifest = load_manifest(project_root)
    canonical_role = ROLE_ALIASES.get(role, role)
    role_path = _role_path(project_root, manifest, role)
    if not role_path.is_file():
        raise FileNotFoundError(f"Role config not found: {role_path}")

    raw = parse(role_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Role config must be a YAML object: {role_path}")

    policy = resolve_role_policy(raw)
    policy.runner.default = _normalize_runner_name(policy.runner.default, manifest.agents.default_runner)
    system_prompt, checklist_prompt = load_agent_prompts(role_path.read_text(encoding="utf-8"), project_root)

    return RoleRuntimeConfig(
        role=raw.get("role") or canonical_role,
        label=raw.get("label") or canonical_role.title(),
        purpose=raw.get("purpose") or "",
        policy=policy,
        system_prompt=system_prompt,
        checklist_prompt=checklist_prompt,
        config_path=role_path,
        project_root=project_root,
        manifest=manifest,
        raw_config=raw,
    )


def list_role_runtime_configs(project: dict[str, Any]) -> list[RoleRuntimeConfig]:
    project_root = _project_root(project)
    manifest = load_manifest(project_root)
    roles_dir = project_root / manifest.agents.roles_dir
    configs: list[RoleRuntimeConfig] = []
    for path in sorted(roles_dir.glob("*.yaml")):
        try:
            configs.append(load_role_runtime_config(project, path.stem))
        except Exception:
            continue
    return configs


def summarize_role_config(config: RoleRuntimeConfig) -> dict[str, Any]:
    return {
        "role": config.role,
        "label": config.label,
        "purpose": config.purpose,
        "runner": {
            "default": config.policy.runner.default,
            "approval_required": config.policy.runner.approval_required,
            "bash_access": config.policy.runner.bash_access,
        },
        "permissions": {
            "read": config.policy.paths.read,
            "write": config.policy.paths.write,
            "deny": config.policy.paths.deny,
        },
        "tools": {
            "allow": config.policy.tools.allow,
            "deny": config.policy.tools.deny,
        },
        "skills": {
            "allow_use": config.policy.skills.allow_use,
        },
        "completion": {
            "requires": config.policy.completion.requires,
        },
        "promptFiles": {
            "system": str(config.raw_config.get("prompts", {}).get("system") or ""),
            "checklist": str(config.raw_config.get("prompts", {}).get("checklist") or ""),
        },
    }


def read_project_skills(project: dict[str, Any]) -> list[dict[str, str]]:
    project_root = _project_root(project)
    manifest = load_manifest(project_root)
    skills_dir = project_root / manifest.paths.skills_root
    if not skills_dir.is_dir():
        return []
    skills: list[dict[str, str]] = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        skills.append(
            {
                "name": path.name,
                "path": str(path.relative_to(project_root)),
                "content": content,
            }
        )
    return skills
