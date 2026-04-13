#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "rail-py"))

from rail.bootstrap import bootstrap_future_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a future RAIL project repository.")
    parser.add_argument("target_dir", help="Target project directory")
    parser.add_argument("--name", required=True, help="Project display name")
    parser.add_argument("--slug", default=None, help="Project slug (optional)")
    parser.add_argument("--default-branch", default="main", help="Default git branch")
    args = parser.parse_args()

    root = bootstrap_future_project(
        args.target_dir,
        name=args.name,
        slug=args.slug,
        default_branch=args.default_branch,
    )
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
