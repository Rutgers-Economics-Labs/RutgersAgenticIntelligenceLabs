from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from app.services import planner_service, session_files
from app.services.integrity_service import evaluate_integrity_gate
from rail.manifest import load_manifest

_log = logging.getLogger(__name__)

# Fields that change on every audit write but do not reflect a real state change.
# Excluded from the payload hash so identical audits don't churn the repo.
_AUDIT_HASH_EXCLUDED_FIELDS = ("generatedAt", "payloadHash")


def _audit_root(project_root: Path) -> Path:
    return project_root / "research_plan" / "audits"


def _compute_payload_hash(payload: dict[str, Any]) -> str:
    """Stable identity for an audit payload, ignoring timestamp churn.

    Two audits with identical session/planner/integrity/auditor state but
    different generatedAt values produce the same hash, so reconciliation
    rewrites of an unchanged audit short-circuit before touching disk or git.
    """
    canonical = {k: v for k, v in payload.items() if k not in _AUDIT_HASH_EXCLUDED_FIELDS}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _existing_payload_hash(json_path: Path) -> str | None:
    if not json_path.is_file():
        return None
    try:
        existing = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    stored = existing.get("payloadHash")
    if isinstance(stored, str) and stored:
        return stored
    # Older audit files predate payloadHash. Recompute on the fly so we can
    # still detect "nothing changed" against them.
    try:
        return _compute_payload_hash(existing)
    except Exception:
        return None


async def _commit_audit_to_git(project_root: Path, paths: list[Path]) -> None:
    """Stage and commit audit files as a durable record in the project repo."""
    if not (project_root / ".git").exists():
        return
    rel_paths = [str(p.relative_to(project_root)) for p in paths if p.exists()]
    if not rel_paths:
        return
    # Only create a dedicated audit-history commit the first time a session's
    # audit files appear in the repo. Rewrites of the same audit happen during
    # reconciliation and autopilot retries; committing every refresh floods the
    # project history with near-duplicate audit snapshots.
    new_rel_paths: list[str] = []
    for rel_path in rel_paths:
        probe = subprocess.run(
            ["git", "-C", str(project_root), "cat-file", "-e", f"HEAD:{rel_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            new_rel_paths.append(rel_path)
    if not new_rel_paths:
        return
    try:
        add = await asyncio.create_subprocess_exec(
            "git", "-C", str(project_root), "add", "--", *rel_paths,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(add.wait(), timeout=15)
        commit = await asyncio.create_subprocess_exec(
            "git", "-C", str(project_root), "commit", "--no-gpg-sign",
            "-m", f"audit: durable post-run certificates ({', '.join(rel_paths[:2])}{'…' if len(rel_paths) > 2 else ''})",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(commit.wait(), timeout=15)
    except Exception as exc:
        _log.debug("audit git commit skipped: %s", exc)


def _session_roots(project_root: Path) -> list[Path]:
    sessions_root = project_root / "research_plan" / "sessions"
    if not sessions_root.is_dir():
        return []
    return sorted(path for path in sessions_root.glob("*/*") if path.is_dir())


def read_latest_audit(project_root: Path) -> dict[str, Any] | None:
    audit_root = _audit_root(project_root)
    if not audit_root.is_dir():
        return None
    candidates = sorted(audit_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        payload["path"] = str(path.relative_to(project_root))
        return payload
    return None


def list_recent_audits(project_root: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    audit_root = _audit_root(project_root)
    if not audit_root.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    candidates = sorted(audit_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        if len(rows) >= limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        session = payload.get("session") or {}
        integrity = payload.get("integrity") or {}
        planner = payload.get("planner") or {}
        rows.append(
            {
                "generatedAt": payload.get("generatedAt"),
                "path": str(path.relative_to(project_root)),
                "currentBlocker": payload.get("currentBlocker"),
                "session": {
                    "id": session.get("id"),
                    "role": session.get("role"),
                    "status": session.get("status"),
                    "reviewStatus": session.get("reviewStatus"),
                    "verificationStatus": session.get("verificationStatus"),
                    "publishStatus": session.get("publishStatus"),
                },
                "integrity": {
                    "blocked": bool(integrity.get("blocked")),
                    "reason": (integrity.get("reasons") or [None])[0],
                },
                "planner": {
                    "blockedTaskCount": int((planner.get("taskCounts") or {}).get("blocked") or 0),
                    "readyTaskCount": int((planner.get("taskCounts") or {}).get("ready") or 0),
                },
            }
        )
    return rows


def _normalize_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("_id") or "Untitled task")


def _planner_snapshot(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    ready_titles = [_normalize_title(task) for task in tasks if task.get("status") == "ready"][:5]
    blocked_titles = [_normalize_title(task) for task in tasks if task.get("status") == "blocked"][:5]
    active_titles = [
        _normalize_title(task)
        for task in tasks
        if task.get("status") not in {"done", "cancelled", "blocked", "ready"}
    ][:5]
    return {
        "taskCounts": counts,
        "readyTasks": ready_titles,
        "blockedTasks": blocked_titles,
        "activeTasks": active_titles,
    }


def _derive_current_blocker(
    *,
    state: dict[str, Any],
    integrity_gate: dict[str, Any],
    planner_snapshot: dict[str, Any],
) -> str | None:
    blockers = state.get("completion_summary", {}).get("blockers") or []
    if blockers:
        return str(blockers[0])
    if state.get("publish_status") == "failed":
        return str(state.get("publish_error") or "Publish failed.")
    if state.get("verification_status") == "failed":
        reasons = integrity_gate.get("reasons") or []
        if reasons:
            return str(reasons[0])
        return "Verification failed."
    blocked_tasks = planner_snapshot.get("blockedTasks") or []
    if blocked_tasks:
        return f"Blocked planner task: {blocked_tasks[0]}"
    ready_tasks = planner_snapshot.get("readyTasks") or []
    if ready_tasks and state.get("review_status") != "review":
        return f"Ready planner task waiting on review: {ready_tasks[0]}"
    return None


def _render_audit_markdown(payload: dict[str, Any]) -> str:
    session = payload["session"]
    planner = payload["planner"]
    integrity = payload["integrity"]
    lines = [
        "# Post-Run Audit",
        "",
        f"- Session: `{session['id']}`",
        f"- Role: `{session['role']}`",
        f"- Status: `{session['status']}`",
        f"- Review: `{session['reviewStatus']}`",
        f"- Verification: `{session['verificationStatus']}`",
        f"- Publish: `{session['publishStatus']}`",
    ]
    if payload.get("currentBlocker"):
        lines.extend(["", "## Current Blocker", "", f"- {payload['currentBlocker']}"])
    lines.extend(
        [
            "",
            "## Planner Snapshot",
            "",
            f"- Task counts: `{json.dumps(planner['taskCounts'], sort_keys=True)}`",
            f"- Ready tasks: {', '.join(planner['readyTasks']) if planner['readyTasks'] else 'None'}",
            f"- Blocked tasks: {', '.join(planner['blockedTasks']) if planner['blockedTasks'] else 'None'}",
            f"- Active tasks: {', '.join(planner['activeTasks']) if planner['activeTasks'] else 'None'}",
            "",
            "## Integrity Snapshot",
            "",
            f"- Action: `{integrity['action']}`",
            f"- Blocked: `{integrity['blocked']}`",
            f"- Reasons: {', '.join(integrity['reasons']) if integrity['reasons'] else 'None'}",
        ]
    )
    changed_files = session.get("changedFiles") or []
    if changed_files:
        lines.extend(["", "## Changed Files", ""])
        lines.extend(f"- `{path}`" for path in changed_files)
    return "\n".join(lines) + "\n"


def audit_gate_status(project_root: Path) -> dict[str, Any]:
    latest = read_latest_audit(project_root)
    latest_generated_at = str((latest or {}).get("generatedAt") or "")
    stale_sessions: list[str] = []
    stale_details: list[dict[str, Any]] = []
    terminal_sessions: list[str] = []

    for session_root in _session_roots(project_root):
        state = session_files.read_state(session_root)
        status = str(state.get("status") or "")
        if status not in {"completed", "failed", "cancelled"}:
            continue
        session_id = str(state.get("session_id") or session_root.name)
        terminal_sessions.append(session_id)
        updated_at = str(state.get("updated_at") or "")
        if not latest:
            stale_sessions.append(session_id)
            stale_details.append(
                {
                    "sessionId": session_id,
                    "sessionStatus": status,
                    "updatedAt": updated_at,
                    "reason": "no_latest_audit",
                    "latestAuditSessionId": None,
                    "latestAuditGeneratedAt": latest_generated_at or None,
                }
            )
            continue
        audited_session_id = str((latest.get("session") or {}).get("id") or "")
        if session_id != audited_session_id and updated_at >= latest_generated_at:
            stale_sessions.append(session_id)
            stale_details.append(
                {
                    "sessionId": session_id,
                    "sessionStatus": status,
                    "updatedAt": updated_at,
                    "reason": "newer_than_latest_audit_for_different_session",
                    "latestAuditSessionId": audited_session_id or None,
                    "latestAuditGeneratedAt": latest_generated_at or None,
                }
            )
            continue
        if session_id == audited_session_id and updated_at > latest_generated_at:
            stale_sessions.append(session_id)
            stale_details.append(
                {
                    "sessionId": session_id,
                    "sessionStatus": status,
                    "updatedAt": updated_at,
                    "reason": "session_updated_after_its_latest_audit",
                    "latestAuditSessionId": audited_session_id or None,
                    "latestAuditGeneratedAt": latest_generated_at or None,
                }
            )

    if stale_details:
        _log.warning(
            "audit_gate_status detected stale terminal session audits for %s: %s",
            project_root,
            json.dumps(stale_details, sort_keys=True),
        )

    return {
        "blocked": bool(stale_sessions),
        "reason": (
            "Autopilot is waiting for audited truth to catch up with terminal session state."
            if stale_sessions
            else None
        ),
        "staleSessionIds": stale_sessions,
        "staleSessionDetails": stale_details,
        "latestAudit": latest,
        "latestAuditPath": (latest or {}).get("path") if latest else None,
        "terminalSessionIds": terminal_sessions,
    }


async def repair_stale_session_audits(project: dict[str, Any], project_root: Path) -> dict[str, Any]:
    gate = audit_gate_status(project_root)
    stale_session_ids = [str(item) for item in (gate.get("staleSessionIds") or []) if item]
    if not stale_session_ids:
        return {"repairedSessionIds": []}

    _log.info(
        "repair_stale_session_audits starting for %s: stale_session_ids=%s details=%s",
        project.get("slug") or project_root,
        stale_session_ids,
        json.dumps(gate.get("staleSessionDetails") or [], sort_keys=True),
    )

    repaired: list[str] = []
    for session_root in _session_roots(project_root):
        state = session_files.read_state(session_root)
        session_id = str(state.get("session_id") or session_root.name)
        if session_id not in stale_session_ids:
            continue
        status = str(state.get("status") or "")
        if status not in {"completed", "failed", "cancelled"}:
            continue
        events = session_files.list_events(session_root)
        changed_files = [
            item.get("path")
            for item in events
            if item.get("type") == "file_change_detected" and item.get("path")
        ]
        _log.info(
            "repair_stale_session_audits rewriting audit for session=%s role=%s status=%s updated_at=%s changed_files=%s",
            session_id,
            state.get("role") or session_root.parent.name,
            status,
            state.get("updated_at"),
            len(changed_files),
        )
        await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id=session_id,
            session={
                "_id": session_id,
                "role": state.get("role") or session_root.parent.name,
                "taskId": state.get("task_id"),
            },
            changed_files=list(dict.fromkeys(str(path) for path in changed_files)),
        )
        repaired.append(session_id)
    return {"repairedSessionIds": repaired}


async def write_post_run_audit(
    *,
    project: dict[str, Any],
    project_root: Path,
    session_root: Path,
    session_id: str,
    session: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    state = session_files.read_state(session_root)
    # Tolerate projects without a rail.yaml manifest — e.g., temp-dir sessions
    # constructed in tests, or projects mid-bootstrap. The audit still records
    # session/planner state; only the integrity gate is skipped.
    try:
        manifest = load_manifest(project_root)
    except FileNotFoundError:
        manifest = None
    integrity_gate: dict[str, Any]
    if manifest is None:
        integrity_gate = {"action": "artifact_generation", "blocked": False, "reasons": []}
    else:
        integrity_gate = evaluate_integrity_gate(project_root, manifest, action="artifact_generation")
    tasks: list[dict[str, Any]] = []
    if project.get("_id") or project.get("projectId"):
        try:
            board = await planner_service.ensure_main_board(project)
            tasks = await planner_service.list_tasks(board["_id"], project=project)
        except Exception:
            tasks = []
    planner = _planner_snapshot(tasks)

    auditors: dict[str, Any] = {}
    auditors_failed_reason: str | None = None
    try:
        from app.services.auditor_service import build_auditor_statuses
        auditors = await build_auditor_statuses(project, tasks=tasks)
    except Exception as exc:
        # Log the actual cause — silently swallowing it produced the audit-churn
        # bug where consecutive audit writes alternated between auditors={}
        # (transient failure) and auditors={...full...} (next iteration), each
        # committing because the payload hashes differed.
        auditors_failed_reason = f"{type(exc).__name__}: {exc}"
        _log.warning(
            "write_post_run_audit: build_auditor_statuses failed for session=%s — %s",
            session_id, auditors_failed_reason,
        )

    if not auditors:
        # Don't persist a half-baked audit when the auditors snapshot is empty.
        # The autopilot's next tick will retry; writing a partial here just
        # produces audit-commit churn when it later succeeds. The session
        # state on disk is unchanged; only the .json/.md sidecar is skipped.
        _log.info(
            "write_post_run_audit skipped (empty auditors snapshot) session=%s%s",
            session_id,
            f" — last_error={auditors_failed_reason}" if auditors_failed_reason else "",
        )
        return {
            "jsonPath": str(_audit_root(project_root) / f"{session_id}.json"),
            "markdownPath": str(_audit_root(project_root) / f"{session_id}.md"),
            "payload": None,
            "skipped": True,
            "reason": "empty_auditors",
        }

    payload = {
        "generatedAt": session_files.utc_now_iso(),
        "session": {
            "id": session_id,
            "role": session.get("role") or state.get("role") or "agent",
            "status": state.get("status") or "unknown",
            "reviewStatus": state.get("review_status") or "pending",
            "verificationStatus": state.get("verification_status") or "pending",
            "publishStatus": state.get("publish_status") or "not_started",
            "taskId": state.get("task_id") or session.get("taskId"),
            "changedFiles": list(changed_files),
        },
        "planner": planner,
        "integrity": {
            "action": integrity_gate.get("action") or "artifact_generation",
            "blocked": bool(integrity_gate.get("blocked")),
            "reasons": [str(item) for item in (integrity_gate.get("reasons") or [])],
        },
        "auditors": auditors,
        "completionSummary": state.get("completion_summary") or {},
    }
    payload["currentBlocker"] = _derive_current_blocker(
        state=state,
        integrity_gate=payload["integrity"],
        planner_snapshot=planner,
    )
    payload["payloadHash"] = _compute_payload_hash(payload)
    audit_root = _audit_root(project_root)
    json_path = audit_root / f"{session_id}.json"
    md_path = audit_root / f"{session_id}.md"
    # Skip the rewrite + git commit when the audit payload is byte-identical
    # to the one already on disk (ignoring timestamp churn). This is what
    # stops the autopilot/reconciliation loop from producing a fresh
    # "audit: durable post-run certificates" commit on every tick when
    # nothing about the session, planner, or integrity state has changed.
    if _existing_payload_hash(json_path) == payload["payloadHash"]:
        _log.debug(
            "write_post_run_audit skipped (payload unchanged) session=%s hash=%s",
            session_id,
            payload["payloadHash"],
        )
        return {
            "jsonPath": str(json_path),
            "markdownPath": str(md_path),
            "payload": payload,
            "skipped": True,
        }
    _log.info(
        "write_post_run_audit session=%s role=%s status=%s review=%s verification=%s publish=%s current_blocker=%s changed_files=%s",
        session_id,
        payload["session"]["role"],
        payload["session"]["status"],
        payload["session"]["reviewStatus"],
        payload["session"]["verificationStatus"],
        payload["session"]["publishStatus"],
        payload.get("currentBlocker"),
        len(changed_files),
    )
    audit_root.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_audit_markdown(payload), encoding="utf-8")
    await _commit_audit_to_git(project_root, [json_path, md_path])
    return {"jsonPath": str(json_path), "markdownPath": str(md_path), "payload": payload}
