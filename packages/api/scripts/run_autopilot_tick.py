#!/usr/bin/env python3
"""Run one or more autopilot iterations for a registered Convex project.

Example (from packages/api/):
  python scripts/run_autopilot_tick.py --slug nj-housing-affordability --iterations 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).parents[1]
REPO_ROOT = Path(__file__).parents[3]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"
for path in (API_ROOT, RAIL_PY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


def _file_backed_active_worker(project: dict) -> dict | None:
    root_value = project.get("localRepoPath")
    if not root_value:
        return None
    sessions_root = Path(str(root_value)) / "research_plan" / "sessions"
    if not sessions_root.exists():
        return None
    terminal = {"completed", "done", "failed", "cancelled", "review", "needs_changes"}
    candidates: list[tuple[float, dict]] = []
    for state_path in sessions_root.glob("*/*/state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        status = str(state.get("status") or "").strip().lower()
        if not status or status in terminal:
            continue
        runner_pid = state_path.parent / ".runner" / "pid.txt"
        if not runner_pid.exists() and status not in {"running", "queued", "initialized"}:
            continue
        candidates.append(
            (
                state_path.stat().st_mtime,
                {
                    "_id": str(state.get("session_id") or state_path.parent.name),
                    "role": str(state.get("role") or state_path.parent.parent.name),
                    "status": status,
                },
            )
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[-1][1]


async def _convex_preflight() -> str | None:
    """Return a backend error string when Convex is reachable but disabled."""
    import httpx
    from app.core.config import settings

    base_url = settings.convex_url.strip().rstrip("/")
    deploy_key = settings.convex_deploy_key.strip()
    if not base_url or not deploy_key:
        return "Convex is not configured; set CONVEX_URL and CONVEX_DEPLOY_KEY."

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/api/query",
                json={"path": "projects:getBySlug", "args": {"slug": "__rail_preflight__"}},
                headers={"Authorization": f"Convex {deploy_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"Convex preflight failed: {exc}"

    if isinstance(data, dict) and data.get("status") == "error":
        return str(data.get("errorMessage") or data)
    return None


async def _run(
    slug: str,
    iterations: int,
    *,
    auto_approve: bool,
    worker_timeout_seconds: int | None,
    loop_timeout_seconds: int | None,
) -> int:
    from app.services import autopilot_service, planner_service, running_agent_service

    project = await planner_service.get_project_by_slug(slug)
    if not project:
        print(f"ERROR: project not found: {slug}")
        return 1
    if not project.get("localRepoPath"):
        print(f"ERROR: project {slug} has no localRepoPath — run register_validation_project.py first")
        return 1

    is_local_project = str(project.get("_id") or "").startswith("local:")
    backend_error = None if is_local_project else await _convex_preflight()
    if backend_error:
        print("ERROR: autopilot requires an available Convex backend for session/task state.")
        print(f"  {backend_error}")
        return 1

    autopilot_service._active_autopilots[slug] = True
    autopilot_service._autopilot_configs.setdefault(slug, {})
    autopilot_service._autopilot_configs[slug].update(
        {
            "auto_approve": auto_approve,
            "dispatch_approval_required": False,
            "desired_enabled": True,
            "worker_timeout_seconds": worker_timeout_seconds,
        }
    )
    try:
        try:
            loop_coro = autopilot_service.run_autopilot_loop(slug, max_iterations=iterations)
            if loop_timeout_seconds and loop_timeout_seconds > 0:
                await asyncio.wait_for(loop_coro, timeout=loop_timeout_seconds)
            else:
                await loop_coro
        except asyncio.TimeoutError:
            print(f"ERROR: autopilot loop did not finish within {loop_timeout_seconds}s")
            active_worker = await running_agent_service.find_active_worker(project["_id"])
            if not active_worker:
                active_worker = _file_backed_active_worker(project)
            if active_worker:
                await autopilot_service._poll_active_worker_if_present(project, active_worker, slug)
            return 2
        active_worker = await running_agent_service.find_active_worker(project["_id"])
        if not active_worker:
            active_worker = _file_backed_active_worker(project)
        if active_worker:
            await autopilot_service._poll_active_worker_if_present(project, active_worker, slug)
    finally:
        autopilot_service._active_autopilots[slug] = False

    config = autopilot_service.get_autopilot_config(slug)
    print(f"Autopilot tick complete for {slug} ({iterations} iteration(s))")
    print(f"  last_action: {config.get('last_action')}")
    print(f"  last_turn_result: {config.get('last_turn_result')}")
    print(f"  status: {config.get('status')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded autopilot iterations")
    parser.add_argument("--slug", default="nj-housing-affordability")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Grant eligible pending task approvals during the bounded tick.",
    )
    parser.add_argument(
        "--worker-timeout-seconds",
        type=int,
        default=None,
        help="Cancel an active worker if it does not finish within this bounded tick timeout.",
    )
    parser.add_argument(
        "--loop-timeout-seconds",
        type=int,
        default=None,
        help="Fail the bounded tick if the autopilot loop itself does not return within this timeout.",
    )
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.worker_timeout_seconds is not None and args.worker_timeout_seconds < 5:
        parser.error("--worker-timeout-seconds must be >= 5")
    if args.loop_timeout_seconds is not None and args.loop_timeout_seconds < 5:
        parser.error("--loop-timeout-seconds must be >= 5")
    loop_timeout_seconds = args.loop_timeout_seconds
    if loop_timeout_seconds is None and args.worker_timeout_seconds:
        loop_timeout_seconds = args.worker_timeout_seconds + 30
    return asyncio.run(
        _run(
            args.slug,
            args.iterations,
            auto_approve=args.auto_approve,
            worker_timeout_seconds=args.worker_timeout_seconds,
            loop_timeout_seconds=loop_timeout_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
