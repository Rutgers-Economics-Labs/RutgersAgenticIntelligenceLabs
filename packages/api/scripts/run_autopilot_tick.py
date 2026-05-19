#!/usr/bin/env python3
"""Run one or more autopilot iterations for a registered Convex project.

Example (from packages/api/):
  python scripts/run_autopilot_tick.py --slug nj-housing-affordability --iterations 3
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).parents[1]
REPO_ROOT = Path(__file__).parents[3]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


async def _run(slug: str, iterations: int) -> int:
    from app.services import autopilot_service, planner_service

    project = await planner_service.get_project_by_slug(slug)
    if not project:
        print(f"ERROR: project not found: {slug}")
        return 1
    if not project.get("localRepoPath"):
        print(f"ERROR: project {slug} has no localRepoPath — run register_validation_project.py first")
        return 1

    autopilot_service._active_autopilots[slug] = True
    try:
        await autopilot_service.run_autopilot_loop(slug, max_iterations=iterations)
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
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    return asyncio.run(_run(args.slug, args.iterations))


if __name__ == "__main__":
    raise SystemExit(main())
