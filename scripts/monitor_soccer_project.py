#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_API_ROOT = "http://127.0.0.1:8000/api/v1"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/health"
DEFAULT_PROJECT_SLUG = "european-soccer-competitive-ecosystem-analysis"
DEFAULT_STATE_DIR = (
    Path.home() / "Library" / "Application Support" / "RAIL" / "external-monitors"
)


@dataclass
class MonitorEvent:
    key: str
    title: str
    message: str


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _load_json(url: str, timeout: int) -> tuple[int | None, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "rail-soccer-monitor/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            payload = response.read().decode("utf-8")
        return status, json.loads(payload)
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read().decode("utf-8")
            body = json.loads(payload)
        except Exception:
            body = {"error": str(exc)}
        return exc.code, body
    except Exception as exc:
        return None, {"error": str(exc)}


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int | None, Any]:
    request = urllib.request.Request(
        url,
        data=_json_bytes(payload),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "rail-soccer-monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            body = response.read().decode("utf-8")
        return status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {"error": str(exc)}
        return exc.code, payload
    except Exception as exc:
        return None, {"error": str(exc)}


def _safe_title(task: dict[str, Any]) -> str:
    return str(task.get("title") or task.get("_id") or "unknown task")


def _summary_signature(summary: dict[str, Any]) -> str:
    return json.dumps(summary, sort_keys=True, separators=(",", ":"))


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def _send_notification(title: str, message: str) -> None:
    script = (
        'display notification "{}" with title "{}" sound name "Glass"'
    ).format(message.replace('"', '\\"'), title.replace('"', '\\"'))
    subprocess.run(["osascript", "-e", script], check=False)


def _fetch_summary(project_slug: str, api_root: str, health_url: str, timeout: int) -> dict[str, Any]:
    health_status, health = _load_json(health_url, timeout)
    project_root = f"{api_root}/projects/{project_slug}"
    hydration_status, hydration = _load_json(f"{project_root}/hydration/status", timeout)
    agents_status, agents = _load_json(f"{project_root}/agents/active", timeout)
    board_status, board = _load_json(f"{project_root}/planner/board", timeout)
    autopilot_status, autopilot = _load_json(f"{project_root}/autopilot/status", timeout)

    tasks = list(board.get("tasks") or []) if isinstance(board, dict) else []
    active_agents = list(agents.get("agents") or []) if isinstance(agents, dict) else []
    status_counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    ready_tasks = [_safe_title(task) for task in tasks if task.get("status") == "ready"][:3]
    blocked_tasks = [_safe_title(task) for task in tasks if task.get("status") == "blocked"][:3]
    awaiting_tasks = [
        _safe_title(task) for task in tasks if task.get("status") == "awaiting_approval"
    ][:3]
    suspicious_ready = [
        _safe_title(task)
        for task in tasks
        if task.get("status") == "ready"
        and any(token in _safe_title(task).lower() for token in ("diagnose", "repair", "hydrate", "verify"))
    ][:3]

    return {
        "checked_at": int(time.time()),
        "health_http": health_status,
        "health_status": health.get("status") if isinstance(health, dict) else None,
        "hydration_http": hydration_status,
        "hydration_state": hydration.get("state") if isinstance(hydration, dict) else None,
        "running_job_id": hydration.get("runningJobId") if isinstance(hydration, dict) else None,
        "agents_http": agents_status,
        "active_agents": [
            {
                "sessionId": agent.get("sessionId"),
                "role": agent.get("role"),
                "status": agent.get("status"),
                "title": agent.get("title"),
                "startedAt": agent.get("startedAt"),
                "currentFocus": agent.get("currentFocus"),
            }
            for agent in active_agents
        ],
        "board_http": board_status,
        "task_status_counts": status_counts,
        "ready_tasks": ready_tasks,
        "blocked_tasks": blocked_tasks,
        "awaiting_approval_tasks": awaiting_tasks,
        "suspicious_ready_tasks": suspicious_ready,
        "autopilot_http": autopilot_status,
        "autopilot_enabled": bool((autopilot or {}).get("enabled")) if isinstance(autopilot, dict) else False,
    }


def _build_events(current: dict[str, Any], previous: dict[str, Any], remind_after_minutes: int) -> list[MonitorEvent]:
    events: list[MonitorEvent] = []
    now_ts = int(current["checked_at"])
    previous_signature = previous.get("summary_signature")
    current_signature = _summary_signature(current)

    if current.get("health_status") != "ok":
        events.append(
            MonitorEvent(
                key="api-down",
                title="RAIL monitor: API down",
                message=f"Backend health is {current.get('health_status') or 'unreachable'}.",
            )
        )
        return events

    if previous and previous.get("health_status") != "ok":
        events.append(
            MonitorEvent(
                key="api-recovered",
                title="RAIL monitor: API recovered",
                message="Backend health returned to ok.",
            )
        )

    if current.get("hydration_state") != previous.get("hydration_state"):
        events.append(
            MonitorEvent(
                key="hydration-state",
                title="RAIL monitor: hydration state changed",
                message=f"Soccer project hydration is now {current.get('hydration_state')}.",
            )
        )

    prev_agents = previous.get("active_agents") or []
    curr_agents = current.get("active_agents") or []
    if len(curr_agents) != len(prev_agents):
        if curr_agents:
            first = curr_agents[0]
            role = first.get("role") or "agent"
            events.append(
                MonitorEvent(
                    key="agents-active",
                    title="RAIL monitor: agents active",
                    message=f"{len(curr_agents)} active session(s). First role: {role}.",
                )
            )
        else:
            events.append(
                MonitorEvent(
                    key="agents-idle",
                    title="RAIL monitor: agents idle",
                    message="No active sessions are currently running for the soccer project.",
                )
            )

    if curr_agents:
        first = curr_agents[0]
        first_started = first.get("startedAt")
        if first_started:
            age_minutes = max(0, int((now_ts * 1000 - float(first_started)) / 60000))
            prev_signature = json.dumps(prev_agents, sort_keys=True)
            curr_signature = json.dumps(curr_agents, sort_keys=True)
            if age_minutes >= 30 and curr_signature == prev_signature:
                events.append(
                    MonitorEvent(
                        key="agent-stuck",
                        title="RAIL monitor: active agent looks stuck",
                        message=(
                            f"{first.get('role') or 'Agent'} has been unchanged for about "
                            f"{age_minutes} minutes at {first.get('currentFocus') or 'unknown focus'}."
                        ),
                    )
                )

    prev_ready = previous.get("ready_tasks") or []
    curr_ready = current.get("ready_tasks") or []
    if curr_ready != prev_ready and curr_ready:
        events.append(
            MonitorEvent(
                key="ready-tasks",
                title="RAIL monitor: ready tasks changed",
                message=f"Top ready task: {curr_ready[0]}",
            )
        )

    if current.get("awaiting_approval_tasks") and current.get("awaiting_approval_tasks") != previous.get(
        "awaiting_approval_tasks"
    ):
        events.append(
            MonitorEvent(
                key="awaiting-approval",
                title="RAIL monitor: approval needed",
                message=f"Waiting on approval: {current['awaiting_approval_tasks'][0]}",
            )
        )

    if current.get("suspicious_ready_tasks") and current.get("suspicious_ready_tasks") != previous.get(
        "suspicious_ready_tasks"
    ):
        events.append(
            MonitorEvent(
                key="blocker-task",
                title="RAIL monitor: blocker surfaced",
                message=f"Needs attention: {current['suspicious_ready_tasks'][0]}",
            )
        )

    last_change_at = int(previous.get("last_change_at") or now_ts)
    if current_signature != previous_signature:
        last_change_at = now_ts

    stalled = (
        current.get("hydration_state") != "hydrated"
        and not current.get("active_agents")
        and (
            current.get("ready_tasks")
            or current.get("blocked_tasks")
            or current.get("awaiting_approval_tasks")
        )
    )
    remind_interval = max(remind_after_minutes, 1) * 60
    if stalled and now_ts - last_change_at >= remind_interval:
        events.append(
            MonitorEvent(
                key="stalled-reminder",
                title="RAIL monitor: soccer project still stalled",
                message=(
                    f"Hydration is {current.get('hydration_state')}; "
                    f"top ready task: {(current.get('ready_tasks') or ['none'])[0]}"
                ),
            )
        )
        last_change_at = now_ts

    current["last_change_at"] = last_change_at
    current["summary_signature"] = current_signature
    return events


def _should_restart_autopilot(current: dict[str, Any]) -> bool:
    if not current.get("autopilot_enabled"):
        return True
    if current.get("active_agents"):
        return False
    if current.get("hydration_state") == "hydrated":
        return False
    return bool(current.get("ready_tasks"))


def _advance_project(project_slug: str, api_root: str, timeout: int, current: dict[str, Any]) -> list[MonitorEvent]:
    events: list[MonitorEvent] = []
    autopilot_url = f"{api_root}/projects/{project_slug}/autopilot"

    if not current.get("health_status") == "ok":
        return events

    if _should_restart_autopilot(current):
        if current.get("autopilot_enabled"):
            _post_json(autopilot_url, {"enabled": False, "autoApprove": False}, timeout)
            time.sleep(1)
        status, body = _post_json(
            autopilot_url,
            {"enabled": True, "autoApprove": True},
            timeout,
        )
        if status == 200 and isinstance(body, dict) and body.get("status") == "started":
            action = "restarted" if current.get("autopilot_enabled") else "started"
            events.append(
                MonitorEvent(
                    key="autopilot-nudge",
                    title="RAIL monitor: nudged autopilot",
                    message=f"{action.capitalize()} autopilot to keep the soccer project moving.",
                )
            )
    return events


def _print_summary(summary: dict[str, Any], events: list[MonitorEvent]) -> None:
    print(json.dumps({"summary": summary, "events": [event.__dict__ for event in events]}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="External monitor for the soccer RAIL project that can notify outside the engine.",
    )
    parser.add_argument("--project-slug", default=DEFAULT_PROJECT_SLUG)
    parser.add_argument("--api-root", default=DEFAULT_API_ROOT)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--remind-after-minutes", type=int, default=90)
    parser.add_argument(
        "--advance",
        action="store_true",
        help="Actively re-enable or restart autopilot when the project looks stalled.",
    )
    parser.add_argument("--notify", action="store_true", help="Send macOS notifications for detected events.")
    parser.add_argument("--print-summary", action="store_true", help="Print the computed summary JSON.")
    args = parser.parse_args()

    state_path = Path(args.state_dir).expanduser() / f"{args.project_slug}.json"
    previous = _read_state(state_path)
    current = _fetch_summary(
        project_slug=args.project_slug,
        api_root=args.api_root.rstrip("/"),
        health_url=args.health_url,
        timeout=args.timeout,
    )
    events = _build_events(current, previous, args.remind_after_minutes)
    if args.advance:
        events.extend(
            _advance_project(
                project_slug=args.project_slug,
                api_root=args.api_root.rstrip("/"),
                timeout=args.timeout,
                current=current,
            )
        )
        current = _fetch_summary(
            project_slug=args.project_slug,
            api_root=args.api_root.rstrip("/"),
            health_url=args.health_url,
            timeout=args.timeout,
        )
    _write_state(state_path, current)

    if args.print_summary:
        _print_summary(current, events)

    if args.notify:
        delivered = set(previous.get("delivered_event_keys") or [])
        new_keys: list[str] = []
        for event in events:
            if event.key == "stalled-reminder" or event.key not in delivered:
                _send_notification(event.title, event.message)
            new_keys.append(event.key)
        current["delivered_event_keys"] = new_keys
        _write_state(state_path, current)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
