"""
Seed Convex with the built-in data source registry catalog.
Run from the repo root: python scripts/seed_registry.py
"""
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parents[1]
API_ROOT = ROOT / "packages" / "api"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.registry_service import default_registry_entries

CONVEX_URL = os.environ.get("CONVEX_URL", "https://colorless-elephant-150.convex.cloud")
DEPLOY_KEY = os.environ.get("CONVEX_DEPLOY_KEY", "")

if not DEPLOY_KEY:
    print("ERROR: set CONVEX_DEPLOY_KEY env var")
    sys.exit(1)

HEADERS = {"Authorization": f"Convex {DEPLOY_KEY}"}


def query(fn: str, args: dict):
    response = httpx.post(
        f"{CONVEX_URL}/api/query",
        json={"path": fn, "args": args},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    return body.get("value", body)


def mutate(fn: str, args: dict):
    response = httpx.post(
        f"{CONVEX_URL}/api/mutation",
        json={"path": fn, "args": args},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    existing = {
        (item["provider"], item["sourceId"])
        for item in (query("registry:list", {"limit": 1000}) or [])
    }
    created = 0
    skipped = 0

    for entry in default_registry_entries():
        key = (entry["provider"], entry["id"])
        if key in existing:
            skipped += 1
            continue
        mutate("registry:create", {
            "provider": entry["provider"],
            "sourceId": entry["id"],
            "name": entry["name"],
            "description": entry["description"],
            "unit": entry["unit"],
            "frequency": entry["frequency"],
            "geography": entry["geography"],
            "tags": entry["tags"],
            "exampleYaml": entry["exampleYaml"],
            "updatedAt": entry["updatedAt"],
        })
        created += 1

    print(f"Seeded {created} registry entries ({skipped} already present).")
    counts: dict[str, int] = {}
    for entry in default_registry_entries():
        counts[str(entry["provider"])] = counts.get(str(entry["provider"]), 0) + 1
    print("Catalog counts:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
