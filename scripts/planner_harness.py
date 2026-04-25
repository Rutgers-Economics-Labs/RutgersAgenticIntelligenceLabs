#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "packages" / "api"
ENGINE_ROOT = ROOT / "packages" / "engine"
RAIL_PY_ROOT = ROOT / "packages" / "rail-py"

# api must stay ahead of engine on sys.path so `import app` resolves to
# packages/api/app rather than packages/engine/app.py.
ordered_paths = [str(API_ROOT), str(RAIL_PY_ROOT), str(ENGINE_ROOT)]
for path in reversed(ordered_paths):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)

from app.services.planner_harness import PlannerHarness, format_planner_result


async def _run_once(args: argparse.Namespace) -> int:
    if args.project_slug:
        harness = await PlannerHarness.from_project_slug(
            args.project_slug,
            model=args.model,
            persist=args.persist,
        )
    else:
        harness = PlannerHarness.from_local_repo(
            args.repo,
            model=args.model,
            persist=args.persist,
            git_repo_url=args.git_repo_url,
        )

    if args.message:
        result = await harness.ask(args.message)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_planner_result(result))
        return 0

    while True:
        try:
            user_message = input("planner> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not user_message:
            continue
        if user_message in {"exit", "quit"}:
            return 0

        result = await harness.ask(user_message)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(format_planner_result(result))
            print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the RAIL planner harness against a project slug or local repo.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project-slug", help="Existing platform project slug")
    target.add_argument("--repo", help="Path to a local repo containing rail.yaml")
    parser.add_argument("--message", help="Single-turn planner message")
    parser.add_argument("--model", help="Optional model override")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist planner thread messages through the operational backend",
    )
    parser.add_argument(
        "--git-repo-url",
        help="Optional git repo URL to attach when using --repo",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON instead of a terminal-friendly summary",
    )
    args = parser.parse_args()
    return asyncio.run(_run_once(args))


if __name__ == "__main__":
    raise SystemExit(main())
