#!/usr/bin/env python3
"""Register or update a local validation checkout in Convex for API/autopilot testing.

Run from packages/api/:

  python scripts/register_validation_project.py
  python scripts/register_validation_project.py --slug nj-housing-affordability \\
      --path ../../docs/validation/nj-housing-affordability

Requires CONVEX_URL and CONVEX_DEPLOY_KEY in the repo root `.env`.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
RAIL_PY_ROOT = REPO_ROOT / "packages" / "rail-py"

for path in (str(API_ROOT), str(RAIL_PY_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Register a validation project in Convex")
    parser.add_argument("--slug", default="nj-housing-affordability")
    parser.add_argument(
        "--path",
        type=Path,
        default=REPO_ROOT / "docs" / "validation" / "nj-housing-affordability",
    )
    args = parser.parse_args()

    root = args.path.expanduser().resolve()
    manifest_path = root / "rail.yaml"
    if not manifest_path.is_file():
        print(f"ERROR: rail.yaml not found at {manifest_path}")
        return 1

    import yaml
    from app.services.convex_client import convex, ConvexBackendConfigurationError
    from app.services.repo_contract_service import ensure_project_boot

    try:
        convex._require_backend_convex()
    except ConvexBackendConfigurationError as exc:
        print(f"ERROR: {exc}")
        return 1

    ensure_project_boot(root)

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    project_meta = raw.get("project") if isinstance(raw.get("project"), dict) else {}
    hydration = raw.get("hydration") if isinstance(raw.get("hydration"), dict) else {}
    slug = str(project_meta.get("slug") or args.slug).strip()

    payload: dict = {
        "name": project_meta.get("name") or slug,
        "slug": slug,
        "description": project_meta.get("description") or "RAIL validation project",
        "approach": "ontology-first",
        "localRepoPath": str(root),
        "manifestPath": "rail.yaml",
    }

    existing = await convex.query("projects:getBySlug", {"slug": slug})
    if existing:
        project_id = existing["_id"]
        await convex.mutation(
            "projects:updateById",
            {
                "projectId": project_id,
                **{key: value for key, value in payload.items() if key != "slug"},
            },
        )
        print(f"Updated Convex project '{slug}' (id={project_id})")
        print(f"  localRepoPath={root}")
    else:
        project_id = await convex.mutation("projects:create", payload)
        print(f"Created Convex project '{slug}' (id={project_id})")
        print(f"  localRepoPath={root}")

    print("\nSmoke-test when API is running:")
    print(f"  curl -s http://127.0.0.1:8000/api/v1/projects/{slug}/reality | python -m json.tool")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
