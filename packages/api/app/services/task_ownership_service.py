"""Task ownership declarations for controlled parallelism.

Each task can be claimed by exactly one session at a time. Claims are backed
by a JSON file under .rail/locks/<task_id>.json so they survive process
restarts. A crashed session's claim will be detected as a zombie (M2) and
released during reconciliation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOCK_DIR = ".rail/locks"


def _lock_dir(project_root: Path | str) -> Path:
    return Path(project_root) / _LOCK_DIR


def _lock_path(project_root: Path | str, task_id: str) -> Path:
    return _lock_dir(project_root) / f"{task_id}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def declare_task_ownership(
    task_id: str,
    session_id: str,
    *,
    project_root: Path | str,
) -> dict[str, Any]:
    """Atomically declare that session_id owns task_id.

    Raises RuntimeError if the task is already owned by a different session.
    Returns the claim record on success.
    """
    lock_dir = _lock_dir(project_root)
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = _lock_path(project_root, task_id)

    existing = read_task_ownership(task_id, project_root=project_root)
    if existing and existing.get("sessionId") != session_id:
        raise RuntimeError(
            f"Task {task_id} is already owned by session {existing['sessionId']}. "
            "Release the existing claim before declaring a new one."
        )

    claim = {
        "taskId": task_id,
        "sessionId": session_id,
        "claimedAt": _utc_now_iso(),
    }
    path.write_text(json.dumps(claim, indent=2), encoding="utf-8")
    return claim


def read_task_ownership(
    task_id: str,
    *,
    project_root: Path | str,
) -> dict[str, Any] | None:
    """Return the current ownership claim for task_id, or None if unclaimed."""
    path = _lock_path(project_root, task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def release_task_ownership(
    task_id: str,
    session_id: str,
    *,
    project_root: Path | str,
) -> dict[str, Any]:
    """Release the ownership claim on task_id held by session_id.

    Raises RuntimeError if session_id does not own the task.
    Returns a dict with released (bool) and the prior claim.
    """
    existing = read_task_ownership(task_id, project_root=project_root)
    if existing is None:
        return {"released": False, "reason": "task_not_claimed", "priorClaim": None}
    if existing.get("sessionId") != session_id:
        raise RuntimeError(
            f"Session {session_id} cannot release task {task_id}: "
            f"it is owned by {existing.get('sessionId')}."
        )
    path = _lock_path(project_root, task_id)
    path.unlink(missing_ok=True)
    return {"released": True, "reason": None, "priorClaim": existing}


def list_owned_tasks(project_root: Path | str) -> list[dict[str, Any]]:
    """Return all current task ownership claims in the project."""
    lock_dir = _lock_dir(project_root)
    if not lock_dir.is_dir():
        return []
    claims: list[dict[str, Any]] = []
    for path in sorted(lock_dir.glob("*.json")):
        try:
            claim = json.loads(path.read_text(encoding="utf-8"))
            claims.append(claim)
        except Exception:
            continue
    return claims
