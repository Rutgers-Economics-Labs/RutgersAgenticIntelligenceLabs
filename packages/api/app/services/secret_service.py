from __future__ import annotations

import os

from cryptography.fernet import Fernet

from app.core.config import settings
from app.services.role_runtime_service import ROLE_ALIASES


def _fernet() -> Fernet:
    # Read the env var at call time so tests that set RAIL_SECRET_FERNET_KEY
    # after the app's Settings singleton has already loaded still pick up
    # the correct value. The Settings field is consulted as a fallback so
    # production callers — which do load settings first — keep working.
    key = (os.environ.get("RAIL_SECRET_FERNET_KEY") or settings.secret_encryption_key or "").strip()
    if not key:
        raise ValueError("RAIL_SECRET_FERNET_KEY is not configured")
    return Fernet(key.encode("utf-8"))


def encrypt_secret_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret_value(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret_value(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _canonicalize_role(agent_role: str | None) -> str:
    normalized = str(agent_role or "").strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def _policy_lookup_roles(agent_role: str | None) -> list[str]:
    canonical = _canonicalize_role(agent_role)
    aliases = sorted(alias for alias, target in ROLE_ALIASES.items() if target == canonical and alias != canonical)
    candidates = [canonical, *aliases]
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


async def resolve_secrets_for_role(project_id: str, agent_role: str) -> dict[str, str]:
    """Return decrypted secrets the given agent role is allowed to access.

    Looks up the agent secret policy for the role, then returns only the
    project secrets whose key names are in the policy's allowlist.
    Returns an empty dict when no policy exists or no secrets match.
    """
    from app.services.convex_client import convex

    policy = None
    for role_candidate in _policy_lookup_roles(agent_role):
        policy = await convex.query(
            "agentSecretPolicies:getByRole",
            {"projectId": project_id, "agentRole": role_candidate},
        )
        if policy:
            break
    if not policy:
        return {}

    allowed_names: list[str] = policy.get("allowedSecretNames") or []
    if not allowed_names:
        return {}
    allow_all = "*" in allowed_names

    all_secrets = await convex.query(
        "projectSecrets:listByProject",
        {"projectId": project_id},
    ) or []

    result: dict[str, str] = {}
    for secret in all_secrets:
        if allow_all or secret["keyName"] in allowed_names:
            try:
                result[secret["keyName"]] = decrypt_secret_value(secret["encryptedValue"])
            except Exception:
                # Skip secrets that fail to decrypt rather than crashing the resolver.
                pass

    return result
