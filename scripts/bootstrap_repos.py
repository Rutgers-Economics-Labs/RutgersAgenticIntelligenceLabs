#!/usr/bin/env python3
"""
Bootstrap RAIL project scaffolds for projects that have no localRepoPath,
initialize git, commit, push to the GitHub remote, and patch Convex.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

from rail.bootstrap import bootstrap_future_project

# ── Config ────────────────────────────────────────────────────────────────────

CONVEX_URL   = "https://animated-caterpillar-927.convex.cloud"
CONVEX_AUTH  = os.environ["CONVEX_DEPLOY_KEY"]
PROJECTS_DIR = Path("/Users/akashdubey/Documents/CodingProjects/RAIL")

PROJECTS = [
    {
        "id":       "js7ft61x6ejh0mfd7vz0kc3p5d83pzc6",
        "name":     "Synthetic Test",
        "slug":     "synthetic",
        "dir":      PROJECTS_DIR / "RAIL-synthetic-test",
        "remote":   "https://github.com/Rutgers-Economics-Labs/RAIL-synthetic-test",
    },
    {
        "id":       "js7f7e4frsq0np6havhasj1t5d83f7fz",
        "name":     "Academic",
        "slug":     "academic",
        "dir":      PROJECTS_DIR / "RAIL-academic",
        "remote":   "https://github.com/Rutgers-Economics-Labs/RAIL-academic",
    },
    {
        "id":       "js79vx3h9fsbbensnn06jg2j9183e0mc",
        "name":     "SAD",
        "slug":     "sad",
        "dir":      PROJECTS_DIR / "RAIL-sad",
        "remote":   "https://github.com/Rutgers-Economics-Labs/RAIL-sad",
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{result.stderr.strip()}")
    if result.stdout.strip():
        print(f"  › {result.stdout.strip()}")


def convex_mutation(path: str, args: dict) -> None:
    body = json.dumps({"path": path, "args": args}).encode()
    req = urllib.request.Request(
        f"{CONVEX_URL}/api/mutation",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Convex {CONVEX_AUTH}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "success":
        raise RuntimeError(f"Convex mutation failed: {data}")


# ── Main ──────────────────────────────────────────────────────────────────────

def bootstrap(p: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {p['name']}  ({p['slug']})")
    print(f"  → {p['dir']}")
    print(f"{'='*60}")

    # 1. Scaffold files
    print("  [1/5] Scaffolding project files…")
    bootstrap_future_project(p["dir"], name=p["name"], slug=p["slug"])

    # 2. git init (skip if already a repo)
    git_dir = p["dir"] / ".git"
    if not git_dir.exists():
        print("  [2/5] git init…")
        run(["git", "init", "-b", "main"], cwd=p["dir"])
    else:
        print("  [2/5] Already a git repo, skipping init.")

    # 3. Set remote
    print("  [3/5] Setting remote origin…")
    remotes = subprocess.run(
        ["git", "remote"], cwd=p["dir"], capture_output=True, text=True
    ).stdout.split()
    if "origin" in remotes:
        run(["git", "remote", "set-url", "origin", p["remote"]], cwd=p["dir"])
    else:
        run(["git", "remote", "add", "origin", p["remote"]], cwd=p["dir"])

    # 4. Commit
    print("  [4/5] Committing scaffold…")
    run(["git", "config", "user.email", "rel@rutgerseconomics.org"], cwd=p["dir"])
    run(["git", "config", "user.name",  "RAIL Bootstrap"], cwd=p["dir"])
    run(["git", "add", "."], cwd=p["dir"])
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=p["dir"]
    )
    if result.returncode != 0:
        run(
            ["git", "commit", "-m", "chore: initial RAIL project scaffold"],
            cwd=p["dir"],
        )
    else:
        print("  Nothing new to commit.")

    # 5. Push
    print("  [5/5] Pushing to GitHub…")
    run(["git", "push", "-u", "origin", "main"], cwd=p["dir"])

    # 6. Patch Convex
    print("  [6/6] Updating Convex localRepoPath…")
    convex_mutation("projects:updateById", {
        "projectId": p["id"],
        "localRepoPath": str(p["dir"]),
    })

    print(f"  ✓ Done → {p['remote']}")


if __name__ == "__main__":
    for project in PROJECTS:
        bootstrap(project)
    print("\n✓ All projects bootstrapped and pushed.")
