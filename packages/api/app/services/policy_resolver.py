from pydantic import BaseModel, Field
from typing import List, Optional

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

class RuntimePolicy(BaseModel):
    paths: PathPolicy
    secrets: SecretPolicy
    tools: ToolPolicy
    completion: CompletionPolicy

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

def resolve_role_policy(agent_config: dict) -> RuntimePolicy:
    return RuntimePolicy(
        paths=resolve_path_policy(agent_config.get("permissions")),
        secrets=resolve_secret_policy(agent_config.get("secrets")),
        tools=resolve_tool_policy(agent_config.get("tools")),
        completion=resolve_completion_policy(agent_config.get("completion"))
    )
