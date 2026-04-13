from __future__ import annotations

import hashlib
import os
import platform
import socket
import uuid
from pathlib import Path


DEVICE_ID_ENV = "RAIL_DEVICE_ID"
DEVICE_ID_PATH_ENV = "RAIL_DEVICE_ID_PATH"
DEFAULT_DEVICE_ID_PATH = Path.home() / ".rail" / "device_id"


def _device_id_path() -> Path:
    raw = os.environ.get(DEVICE_ID_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_DEVICE_ID_PATH


def get_device_id() -> str:
    explicit = os.environ.get(DEVICE_ID_ENV)
    if explicit:
        return explicit.strip()

    path = _device_id_path()
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value

    base = f"{socket.gethostname()}::{platform.system()}::{platform.machine()}::{uuid.getnode()}"
    device_id = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(device_id, encoding="utf-8")
    return device_id


def get_device_metadata() -> dict[str, str]:
    return {
        "deviceId": get_device_id(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "label": os.environ.get("RAIL_DEVICE_LABEL") or socket.gethostname(),
    }
