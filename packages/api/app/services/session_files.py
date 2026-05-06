from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMPLETION_SUMMARY_FIELDS = (
    "assumptions_added",
    "assumptions_changed",
    "sources_used",
    "datasets_created",
    "artifacts_created",
    "claims_created",
    "verification_results",
    "open_questions",
    "blockers",
    "recommended_next_tasks",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].rstrip("-") or "session"


def session_root(project_root: str | Path, role: str, session_id: str) -> Path:
    return Path(project_root) / "research_plan" / "sessions" / role / session_id


def empty_completion_summary(*, status: str = "initialized") -> dict[str, Any]:
    return {
        "status": status,
        "assumptions_added": [],
        "assumptions_changed": [],
        "sources_used": [],
        "datasets_created": [],
        "artifacts_created": [],
        "claims_created": [],
        "verification_results": [],
        "open_questions": [],
        "blockers": [],
        "recommended_next_tasks": [],
    }


def normalize_completion_summary(summary: dict[str, Any] | None, *, status: str | None = None) -> dict[str, Any]:
    normalized = empty_completion_summary(status=status or (summary or {}).get("status") or "initialized")
    if not isinstance(summary, dict):
        return normalized
    for field in COMPLETION_SUMMARY_FIELDS:
        value = summary.get(field, [])
        if isinstance(value, list):
            normalized[field] = value
        elif value in (None, ""):
            normalized[field] = []
        else:
            normalized[field] = [value]
    normalized["status"] = status or summary.get("status") or normalized["status"]
    return normalized


def ensure_session_root(project_root: str | Path, role: str, session_id: str) -> Path:
    root = session_root(project_root, role, session_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "session.ndjson").touch(exist_ok=True)
    (root / "commands.ndjson").touch(exist_ok=True)
    if not (root / "state.json").exists():
        write_state(
            root,
            {
                "session_id": session_id,
                "role": role,
                "status": "initialized",
                "last_event_id": 0,
                "last_command_id": 0,
                "runner_event_cursor": 0,
                "updated_at": utc_now_iso(),
                "review_status": "pending",
                "workspace_path": None,
                "workspace_branch": None,
                "setup_status": None,
                "verification_status": None,
                "archive_status": None,
                "completion_summary": empty_completion_summary(),
            },
        )
    if not (root / "summary.md").exists():
        (root / "summary.md").write_text("# Session Summary\n\nNo events yet.\n", encoding="utf-8")
    for name, title in (
        ("diff.md", "# Diff Review\n\nDiff summary not generated yet.\n"),
        ("todos.md", "# Todos\n\nNo todos recorded.\n"),
        ("verification.md", "# Verification\n\nVerification has not run yet.\n"),
    ):
        path = root / name
        if not path.exists():
            path.write_text(title, encoding="utf-8")
    return root


def read_state(root: str | Path) -> dict[str, Any]:
    path = Path(root) / "state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(root: str | Path, state: dict[str, Any]) -> None:
    path = Path(root) / "state.json"
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def update_state(root: str | Path, **patch: Any) -> dict[str, Any]:
    state = read_state(root)
    state.update({k: v for k, v in patch.items() if v is not None})
    state["updated_at"] = utc_now_iso()
    write_state(root, state)
    return state


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")


def _lock_path(root: Path, name: str) -> Path:
    return root / f".{name}.lock"


def _acquire_lock(root: Path, name: str, timeout_seconds: float = 5.0) -> Path:
    path = _lock_path(root, name)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring lock {path.name}")
            time.sleep(0.02)
            continue
        os.close(fd)
        return path


def _release_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def append_event(root: str | Path, event_type: str, **payload: Any) -> dict[str, Any]:
    root = Path(root)
    lock_path = _acquire_lock(root, "session")
    try:
        state = read_state(root)
        next_id = int(state.get("last_event_id", 0)) + 1
        event = {
            "id": next_id,
            "timestamp": utc_now_iso(),
            "type": event_type,
            **payload,
        }
        _append_jsonl(root / "session.ndjson", event)
        update_state(root, last_event_id=next_id, status=payload.get("status") or state.get("status"))
        refresh_summary(root)
        return event
    finally:
        _release_lock(lock_path)


def append_command(
    root: str | Path,
    command_type: str,
    *,
    content: str | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    root = Path(root)
    lock_path = _acquire_lock(root, "commands")
    try:
        if idempotency_key:
            for command in list_commands(root):
                if command.get("idempotency_key") == idempotency_key:
                    return {**command, "duplicate": True}

        state = read_state(root)
        next_id = int(state.get("last_command_id", 0)) + 1
        command = {
            "id": next_id,
            "timestamp": utc_now_iso(),
            "type": command_type,
            "processed": False,
            "content": content,
            "payload": payload or {},
            "idempotency_key": idempotency_key,
        }
        _append_jsonl(root / "commands.ndjson", command)
        update_state(root, last_command_id=next_id)
        return command
    finally:
        _release_lock(lock_path)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def list_events(root: str | Path) -> list[dict[str, Any]]:
    return read_jsonl(Path(root) / "session.ndjson")


def list_commands(root: str | Path) -> list[dict[str, Any]]:
    return read_jsonl(Path(root) / "commands.ndjson")


def unprocessed_commands(root: str | Path) -> list[dict[str, Any]]:
    return [item for item in list_commands(root) if not item.get("processed")]


def mark_command_processed(root: str | Path, command_id: int) -> None:
    root = Path(root)
    lock_path = _acquire_lock(root, "commands")
    try:
        commands = list_commands(root)
        changed = False
        for item in commands:
            if int(item.get("id", -1)) == int(command_id) and not item.get("processed"):
                item["processed"] = True
                item["processed_at"] = utc_now_iso()
                changed = True
        if not changed:
            return
        path = root / "commands.ndjson"
        with path.open("w", encoding="utf-8") as handle:
            for item in commands:
                handle.write(json.dumps(item, ensure_ascii=True, default=str) + "\n")
    finally:
        _release_lock(lock_path)


def _render_summary(events: list[dict[str, Any]], state: dict[str, Any]) -> str:
    role = state.get("role") or "agent"
    session_id = state.get("session_id") or "unknown"
    status = state.get("status") or "unknown"
    review_status = state.get("review_status") or "pending"
    workspace_path = state.get("workspace_path") or "none"
    workspace_branch = state.get("workspace_branch") or "none"
    publish_status = state.get("publish_status") or "not_started"
    publish_strategy = state.get("publish_strategy") or "none"
    publish_commit_sha = state.get("publish_commit_sha") or "none"
    completion_summary = normalize_completion_summary(
        state.get("completion_summary"),
        status=status,
    )
    lines = [
        "# Session Summary",
        "",
        f"- role: `{role}`",
        f"- session_id: `{session_id}`",
        f"- status: `{status}`",
        f"- review_status: `{review_status}`",
        f"- workspace_path: `{workspace_path}`",
        f"- workspace_branch: `{workspace_branch}`",
        f"- publish_status: `{publish_status}`",
        f"- publish_strategy: `{publish_strategy}`",
        f"- publish_commit_sha: `{publish_commit_sha}`",
        "",
        "## Recent Events",
        "",
    ]
    if not events:
        lines.append("- No events yet.")
        return "\n".join(lines) + "\n"
    for item in events[-20:]:
        label = item.get("type", "event")
        ts = item.get("timestamp", "")
        if label in {"assistant_message", "user_message"}:
            content = (item.get("content") or "").strip().replace("\n", " ")
            lines.append(f"- `{ts}` **{label}**: {content[:200] or '[empty]'}")
        elif label in {"tool_call", "tool_result"}:
            name = item.get("name") or item.get("tool_name") or "tool"
            lines.append(f"- `{ts}` **{label}**: `{name}`")
        elif label in {"question_asked", "approval_requested"}:
            content = (item.get("content") or item.get("prompt") or item.get("message") or "").strip().replace("\n", " ")
            lines.append(f"- `{ts}` **{label}**: {content[:200] or '[no details]'}")
        else:
            lines.append(f"- `{ts}` **{label}**")
    lines.extend(
        [
            "",
            "## Completion Summary",
            "",
            f"- status: `{completion_summary['status']}`",
        ]
    )
    for field in COMPLETION_SUMMARY_FIELDS:
        values = completion_summary.get(field) or []
        lines.append(f"- {field}: {len(values)}")
        if values:
            lines.extend(_format_summary_values(values))
    return "\n".join(lines) + "\n"


def _format_summary_values(values: list[Any]) -> list[str]:
    lines: list[str] = []
    for value in values[:20]:
        if isinstance(value, dict):
            compact = ", ".join(
                f"{key}={json.dumps(item, ensure_ascii=True)}"
                for key, item in value.items()
                if item not in (None, [], {}, "")
            )
            lines.append(f"  - {compact or '{}'}")
        else:
            lines.append(f"  - {value}")
    if len(values) > 20:
        lines.append(f"  - ... {len(values) - 20} more")
    return lines


def refresh_summary(root: str | Path) -> None:
    root = Path(root)
    events = list_events(root)
    state = read_state(root)
    (root / "summary.md").write_text(_render_summary(events, state), encoding="utf-8")
    refresh_review_files(root)


def refresh_review_files(root: str | Path) -> None:
    root = Path(root)
    state = read_state(root)
    events = list_events(root)
    completion_summary = normalize_completion_summary(
        state.get("completion_summary"),
        status=state.get("status") or "unknown",
    )
    workspace_path = state.get("workspace_path")
    workspace_root = Path(workspace_path) if workspace_path else None
    changed_files = [item.get("path") for item in events if item.get("type") == "file_change_detected" and item.get("path")]
    unique_files = list(dict.fromkeys(changed_files))

    git_status = ""
    git_diff = ""
    if workspace_root and workspace_root.exists() and (workspace_root / ".git").exists():
        try:
            git_status = subprocess.run(
                ["git", "-C", str(workspace_root), "status", "--short"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            git_diff = subprocess.run(
                ["git", "-C", str(workspace_root), "diff", "--stat", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if git_status:
                tracked = []
                for line in git_status.splitlines():
                    path = line[3:].strip()
                    if path:
                        tracked.append(path)
                unique_files = list(dict.fromkeys(unique_files + tracked))
        except Exception:
            git_status = ""
            git_diff = ""

    diff_lines = ["# Diff Review", ""]
    if unique_files:
        diff_lines.append("## Changed Files")
        diff_lines.append("")
        diff_lines.extend(f"- `{path}`" for path in unique_files)
    elif git_status:
        diff_lines.append("Workspace has git changes but no tracked file list was captured.")
    else:
        diff_lines.append("Diff summary not generated yet.")
    if git_status:
        diff_lines.extend(["", "## Git Status", "", "```text", git_status, "```"])
    if git_diff:
        diff_lines.extend(["", "## Diff Stat", "", "```text", git_diff, "```"])
    diff_lines.append("")
    (root / "diff.md").write_text("\n".join(diff_lines), encoding="utf-8")

    todo_lines = ["# Todos", ""]
    review_status = state.get("review_status") or "pending"
    if review_status == "pending":
        todo_lines.append("- Review not started.")
    elif review_status == "needs_changes":
        todo_lines.append("- Address review blockers before adoption.")
    else:
        todo_lines.append("- No open todos recorded.")
    if state.get("setup_status") == "failed":
        todo_lines.append("- Workspace setup failed.")
    if state.get("verification_status") == "failed":
        todo_lines.append("- Verification failed; inspect verification.md before adoption.")
    if state.get("archive_status") == "failed":
        todo_lines.append("- Workspace archive failed.")
    for blocker in completion_summary.get("blockers") or []:
        todo_lines.append(f"- Blocker: {blocker}")
    for question in completion_summary.get("open_questions") or []:
        todo_lines.append(f"- Open question: {question}")
    for task in completion_summary.get("recommended_next_tasks") or []:
        todo_lines.append(f"- Recommended next task: {task}")
    todo_lines.append("")
    (root / "todos.md").write_text("\n".join(todo_lines), encoding="utf-8")

    verification_lines = ["# Verification", ""]
    verification_status = state.get("verification_status")
    if verification_status:
        verification_lines.append(f"- status: `{verification_status}`")
    if state.get("verification_exit_code") is not None:
        verification_lines.append(f"- exit_code: `{state.get('verification_exit_code')}`")
    verification_events = [item for item in events if item.get("type") in {"verification_started", "verification_completed", "failed", "completed"}]
    if not verification_events:
        verification_lines.append("Verification has not run yet.")
    else:
        for item in verification_events[-10:]:
            verification_lines.append(f"- `{item.get('timestamp', '')}` **{item.get('type', 'event')}**")
    stdout_tail = state.get("verification_stdout_tail")
    stderr_tail = state.get("verification_stderr_tail")
    if stdout_tail:
        verification_lines.extend(["", "## Stdout", "", "```text", stdout_tail, "```"])
    if stderr_tail:
        verification_lines.extend(["", "## Stderr", "", "```text", stderr_tail, "```"])
    verification_results = completion_summary.get("verification_results") or []
    if verification_results:
        verification_lines.extend(["", "## Verification Results", ""])
        verification_lines.extend(_format_summary_values(verification_results))
    verification_lines.append("")
    (root / "verification.md").write_text("\n".join(verification_lines), encoding="utf-8")


def session_messages(root: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list_events(root):
        if item.get("type") == "user_message":
            rows.append({"role": "user", "content": item.get("content", ""), "timestamp": item.get("timestamp")})
        elif item.get("type") == "assistant_message":
            rows.append({"role": "assistant", "content": item.get("content", ""), "timestamp": item.get("timestamp")})
    return rows
