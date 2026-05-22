"""Kill switch — global and per-project autopilot/runner emergency stop.

The kill switch is the single durable "STOP EVERYTHING" lever for the platform.
It survives API restarts because the engaged state is persisted to disk.

Two scopes:

  - **Global kill.**  No autopilot loop will start or continue for any project.
    Engaging this also cancels every in-flight runner subprocess across all
    projects.  Use when something is misbehaving across the whole platform.

  - **Per-project kill.**  Autopilot loops for a specific project stop;
    in-flight runner sessions for that project get cancelled.  Other projects
    keep running.

The state file lives at $RAIL_KILL_SWITCH_PATH or, by default,
``packages/api/.rail_state/kill_switch.json``.  Schema:

    {
      "global": {
        "engaged": false,
        "reason": null,
        "engaged_at": null,
        "engaged_by": null
      },
      "projects": {
        "<project-slug>": {
          "engaged": true,
          "reason": "user pressed STOP",
          "engaged_at": "2026-05-22T22:14:03Z",
          "engaged_by": "operator"
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / ".rail_state" / "kill_switch.json"


def _state_path() -> Path:
    override = os.environ.get("RAIL_KILL_SWITCH_PATH")
    if override:
        return Path(override)
    return _DEFAULT_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, Any]:
    return {
        "global": {"engaged": False, "reason": None, "engaged_at": None, "engaged_by": None},
        "projects": {},
    }


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return _empty_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("kill_switch: failed to read %s (%s); treating as released", path, exc)
        return _empty_state()
    # Tolerate forward-compatible additions but pin required keys.
    out = _empty_state()
    if isinstance(raw.get("global"), dict):
        out["global"].update({k: raw["global"].get(k) for k in out["global"]})
    if isinstance(raw.get("projects"), dict):
        for slug, entry in raw["projects"].items():
            if isinstance(entry, dict):
                out["projects"][slug] = {
                    "engaged": bool(entry.get("engaged", False)),
                    "reason": entry.get("reason"),
                    "engaged_at": entry.get("engaged_at"),
                    "engaged_by": entry.get("engaged_by"),
                }
    return out


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Status queries — cheap, called from hot paths
# ---------------------------------------------------------------------------

def is_globally_killed() -> bool:
    state = _read_state()
    return bool(state["global"].get("engaged"))


def is_project_killed(project_slug: str) -> bool:
    state = _read_state()
    entry = state["projects"].get(project_slug)
    return bool(entry and entry.get("engaged"))


def is_killed(project_slug: str) -> bool:
    """True if either the global switch OR the project's switch is engaged."""
    state = _read_state()
    if state["global"].get("engaged"):
        return True
    entry = state["projects"].get(project_slug)
    return bool(entry and entry.get("engaged"))


def status() -> dict[str, Any]:
    """Full status snapshot for UI / CLI."""
    return _read_state()


# ---------------------------------------------------------------------------
# Engage / release — write the state, then propagate the cancel side-effects
# ---------------------------------------------------------------------------

async def engage_global(reason: str | None = None, engaged_by: str | None = None) -> dict[str, Any]:
    """Engage the global kill switch.

    Persists the flag, then stops every active autopilot loop and cancels every
    in-flight runner session across all projects. Safe to call repeatedly.
    """
    state = _read_state()
    state["global"] = {
        "engaged": True,
        "reason": reason or "global kill",
        "engaged_at": _now(),
        "engaged_by": engaged_by,
    }
    _write_state(state)
    cancelled = await _cancel_everything()
    logger.warning("kill_switch: GLOBAL KILL engaged (reason=%s); cancelled %d sessions", reason, cancelled["sessions_cancelled"])
    return {"engaged": True, **cancelled, **state["global"]}


async def release_global() -> dict[str, Any]:
    state = _read_state()
    state["global"] = {"engaged": False, "reason": None, "engaged_at": None, "engaged_by": None}
    _write_state(state)
    logger.info("kill_switch: global kill released")
    return state["global"]


async def engage_project(project_slug: str, reason: str | None = None, engaged_by: str | None = None) -> dict[str, Any]:
    state = _read_state()
    state["projects"][project_slug] = {
        "engaged": True,
        "reason": reason or "project kill",
        "engaged_at": _now(),
        "engaged_by": engaged_by,
    }
    _write_state(state)
    cancelled = await _cancel_for_project(project_slug)
    logger.warning("kill_switch: project kill engaged for %s (reason=%s); cancelled %d sessions", project_slug, reason, cancelled["sessions_cancelled"])
    return {"engaged": True, **cancelled, **state["projects"][project_slug]}


async def release_project(project_slug: str) -> dict[str, Any]:
    state = _read_state()
    if project_slug in state["projects"]:
        state["projects"].pop(project_slug, None)
        _write_state(state)
    logger.info("kill_switch: project kill released for %s", project_slug)
    return {"engaged": False, "project_slug": project_slug}


# ---------------------------------------------------------------------------
# Side-effects — cancel autopilots and runner sessions
# ---------------------------------------------------------------------------

async def _cancel_everything() -> dict[str, Any]:
    """Cancel every active autopilot loop and every active runner session."""
    from app.services import autopilot_service  # local import — avoid cycle

    sessions_cancelled = 0
    autopilots_signaled = 0

    # Flip every active autopilot's in-memory flag so the loop terminates on
    # next iteration.  The persisted desired_enabled is left alone — kill is
    # different from "disable", and release_global() should be enough to
    # resume normal operation.
    for slug in list(autopilot_service._active_autopilots.keys()):
        if autopilot_service._active_autopilots.get(slug):
            autopilot_service._active_autopilots[slug] = False
            autopilots_signaled += 1
            # Wake the loop so it observes the flag immediately.
            try:
                autopilot_service.trigger_wake(slug)
            except Exception:
                pass

    # Cancel any active runner subprocess for each known project.
    try:
        from app.services import planner_service, running_agent_service
        from app.runners import session_lifecycle

        # We only know slugs that autopilot has touched recently.  This is
        # the right scope: the kill switch's job is to stop work that's
        # running, not to enumerate every project in Convex.
        slugs = set(autopilot_service._active_autopilots.keys()) | set(autopilot_service._autopilot_configs.keys())
        for slug in slugs:
            try:
                project = await planner_service.get_project_by_slug(slug)
            except Exception:
                continue
            if not project:
                continue
            try:
                worker = await running_agent_service.find_active_worker(project["_id"])
            except Exception:
                worker = None
            if worker and worker.get("agentSessionId"):
                try:
                    await session_lifecycle.cancel_runner_session(
                        worker["agentSessionId"],
                        reason="global kill switch engaged",
                    )
                    sessions_cancelled += 1
                except Exception as exc:
                    logger.warning("kill_switch: failed to cancel session %s: %s", worker.get("agentSessionId"), exc)
    except Exception as exc:
        logger.warning("kill_switch: cancellation loop hit an unexpected error: %s", exc)

    return {"autopilots_signaled": autopilots_signaled, "sessions_cancelled": sessions_cancelled}


async def _cancel_for_project(project_slug: str) -> dict[str, Any]:
    """Cancel the autopilot loop + active runner session for one project."""
    from app.services import autopilot_service

    sessions_cancelled = 0
    autopilots_signaled = 0

    if autopilot_service._active_autopilots.get(project_slug):
        autopilot_service._active_autopilots[project_slug] = False
        autopilots_signaled = 1
        try:
            autopilot_service.trigger_wake(project_slug)
        except Exception:
            pass

    try:
        from app.services import planner_service, running_agent_service
        from app.runners import session_lifecycle

        project = await planner_service.get_project_by_slug(project_slug)
        if project:
            worker = await running_agent_service.find_active_worker(project["_id"])
            if worker and worker.get("agentSessionId"):
                try:
                    await session_lifecycle.cancel_runner_session(
                        worker["agentSessionId"],
                        reason=f"project kill switch engaged for {project_slug}",
                    )
                    sessions_cancelled = 1
                except Exception as exc:
                    logger.warning("kill_switch: failed to cancel session %s: %s", worker.get("agentSessionId"), exc)
    except Exception as exc:
        logger.warning("kill_switch: project cancellation hit an unexpected error: %s", exc)

    return {"autopilots_signaled": autopilots_signaled, "sessions_cancelled": sessions_cancelled}
