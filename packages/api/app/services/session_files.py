from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80].rstrip("-") or "session"


def session_root(project_root: str | Path, role: str, session_id: str) -> Path:
    return Path(project_root) / "research_plan" / "sessions" / role / session_id


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
                "updated_at": utc_now_iso(),
            },
        )
    if not (root / "summary.md").exists():
        (root / "summary.md").write_text("# Session Summary\n\nNo events yet.\n", encoding="utf-8")
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


def append_event(root: str | Path, event_type: str, **payload: Any) -> dict[str, Any]:
    root = Path(root)
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


def append_command(root: str | Path, command_type: str, **payload: Any) -> dict[str, Any]:
    root = Path(root)
    state = read_state(root)
    next_id = int(state.get("last_command_id", 0)) + 1
    command = {
        "id": next_id,
        "timestamp": utc_now_iso(),
        "type": command_type,
        "processed": False,
        **payload,
    }
    _append_jsonl(root / "commands.ndjson", command)
    update_state(root, last_command_id=next_id)
    return command


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
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
    commands = list_commands(root)
    changed = False
    for item in commands:
        if int(item.get("id", -1)) == int(command_id):
            item["processed"] = True
            item["processed_at"] = utc_now_iso()
            changed = True
    if not changed:
        return
    path = root / "commands.ndjson"
    with path.open("w", encoding="utf-8") as handle:
        for item in commands:
            handle.write(json.dumps(item, ensure_ascii=True, default=str) + "\n")


def _render_summary(events: list[dict[str, Any]], state: dict[str, Any]) -> str:
    role = state.get("role") or "agent"
    session_id = state.get("session_id") or "unknown"
    status = state.get("status") or "unknown"
    lines = [
        "# Session Summary",
        "",
        f"- role: `{role}`",
        f"- session_id: `{session_id}`",
        f"- status: `{status}`",
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
    return "\n".join(lines) + "\n"


def refresh_summary(root: str | Path) -> None:
    root = Path(root)
    events = list_events(root)
    state = read_state(root)
    (root / "summary.md").write_text(_render_summary(events, state), encoding="utf-8")


def session_messages(root: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list_events(root):
        if item.get("type") == "user_message":
            rows.append({"role": "user", "content": item.get("content", ""), "timestamp": item.get("timestamp")})
        elif item.get("type") == "assistant_message":
            rows.append({"role": "assistant", "content": item.get("content", ""), "timestamp": item.get("timestamp")})
    return rows
