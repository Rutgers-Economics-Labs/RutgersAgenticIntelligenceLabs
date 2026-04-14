from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    key = (settings.secret_encryption_key or "").strip()
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


async def resolve_secrets_for_role(project_id: str, agent_role: str) -> dict[str, str]:
    """Return decrypted secrets the given agent role is allowed to access.

    Looks up the agent secret policy for the role, then returns only the
    project secrets whose key names are in the policy's allowlist.
    Returns an empty dict when no policy exists or no secrets match.
    """
    from app.services.convex_client import convex

    policy = await convex.query(
        "agentSecretPolicies:getByRole",
        {"projectId": project_id, "agentRole": agent_role},
    )
    if not policy:
        return {}

    allowed_names: list[str] = policy.get("allowedSecretNames") or []
    if not allowed_names:
        return {}

    all_secrets = await convex.query(
        "projectSecrets:listByProject",
        {"projectId": project_id},
    ) or []

    result: dict[str, str] = {}
    for secret in all_secrets:
        if secret["keyName"] in allowed_names:
            try:
                result[secret["keyName"]] = decrypt_secret_value(secret["encryptedValue"])
            except Exception:
                # Skip secrets that fail to decrypt rather than crashing the resolver.
                pass

    return result
