from pydantic import BaseModel, Field
from typing import List, Optional

class RunnerPolicy(BaseModel):
    default: str = "jules"
    approval_required: bool = True
    max_retries: Optional[int] = None
    timeout_minutes: Optional[int] = None
    bash_access: bool = True

class PathPolicy(BaseModel):
    read: List[str] = Field(default_factory=list)
    write: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)

class SecretPolicy(BaseModel):
    allow: List[str] = Field(default_factory=list)

class ToolPolicy(BaseModel):
    allow: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)

class CompletionPolicy(BaseModel):
    requires: List[str] = Field(default_factory=list)

class SkillPolicy(BaseModel):
    allow_use: bool = False

class RuntimePolicy(BaseModel):
    runner: RunnerPolicy
    paths: PathPolicy
    secrets: SecretPolicy
    tools: ToolPolicy
    completion: CompletionPolicy
    skills: SkillPolicy

def resolve_runner_policy(runner: dict | None) -> RunnerPolicy:
    if not runner:
        return RunnerPolicy()
    return RunnerPolicy(
        default=runner.get("default") or "jules",
        approval_required=runner.get("approval_required", True),
        max_retries=runner.get("max_retries"),
        timeout_minutes=runner.get("timeout_minutes"),
        bash_access=runner.get("bash_access", True),
    )

def resolve_path_policy(permissions: dict | None) -> PathPolicy:
    if not permissions:
        return PathPolicy()
    return PathPolicy(
        read=permissions.get("read") or [],
        write=permissions.get("write") or [],
        deny=permissions.get("deny") or []
    )

def resolve_secret_policy(secrets: dict | None) -> SecretPolicy:
    if not secrets:
        return SecretPolicy()
    return SecretPolicy(
        allow=secrets.get("allow") or []
    )

def resolve_tool_policy(tools: dict | None) -> ToolPolicy:
    if not tools:
        return ToolPolicy()
    return ToolPolicy(
        allow=tools.get("allow") or [],
        deny=tools.get("deny") or []
    )

def resolve_completion_policy(completion: dict | None) -> CompletionPolicy:
    if not completion:
        return CompletionPolicy()
    return CompletionPolicy(
        requires=completion.get("requires") or []
    )

def resolve_skill_policy(skills: dict | None, role: str | None = None) -> SkillPolicy:
    if not skills:
        return SkillPolicy(allow_use=(role == "planner"))
    return SkillPolicy(
        allow_use=skills.get("allow_use", role == "planner")
    )

def resolve_role_policy(agent_config: dict) -> RuntimePolicy:
    return RuntimePolicy(
        runner=resolve_runner_policy(agent_config.get("runner")),
        paths=resolve_path_policy(agent_config.get("permissions")),
        secrets=resolve_secret_policy(agent_config.get("secrets")),
        tools=resolve_tool_policy(agent_config.get("tools")),
        completion=resolve_completion_policy(agent_config.get("completion")),
        skills=resolve_skill_policy(agent_config.get("skills"), agent_config.get("role")),
    )
