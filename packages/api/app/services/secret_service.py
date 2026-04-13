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
