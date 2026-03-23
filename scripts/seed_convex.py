"""
Seed Convex with the engine's default YAML configs.
Run from the repo root: python scripts/seed_convex.py
"""
import os, sys, json, re
from pathlib import Path
import httpx, yaml

ROOT = Path(__file__).parents[1]
ENG  = ROOT / "packages" / "engine"

CONVEX_URL = os.environ.get("CONVEX_URL", "https://colorless-elephant-150.convex.cloud").strip().rstrip("/")
DEPLOY_KEY = os.environ.get("CONVEX_DEPLOY_KEY", "").strip()

if not DEPLOY_KEY:
    print("ERROR: set CONVEX_DEPLOY_KEY env var")
    sys.exit(1)

headers = {"Authorization": f"Convex {DEPLOY_KEY}"}

def call(fn: str, args: dict):
    r = httpx.post(f"{CONVEX_URL}/api/mutation",
                   json={"path": fn, "args": args}, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("value", r.json())

def query(fn: str, args: dict):
    r = httpx.post(f"{CONVEX_URL}/api/query",
                   json={"path": fn, "args": args}, headers=headers, timeout=30)
    r.raise_for_status()
    result = r.json()
    return result.get("value", result)

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", name.lower())

# ── Seed API configs ──────────────────────────────────────────────────────────
print("\n=== Seeding API configs ===")
existing_apis = {c["slug"] for c in (query("configs:listApis", {}) or [])}

for path in sorted((ENG / "configs" / "apis").glob("*.yaml")):
    content = path.read_text()
    try:
        spec = yaml.safe_load(content)
    except Exception as e:
        print(f"  SKIP {path.name}: {e}"); continue

    name = spec.get("name", path.stem)
    s    = slug(name)
    if s in existing_apis:
        print(f"  skip {s} (already exists)")
        continue

    call("configs:createApi", {
        "name": name,
        "slug": s,
        "content": content,
        "parsedSpec": spec,
        "sourceType": spec.get("type", "api"),
        "isPublic": True,
        "tags": [],
    })
    print(f"  ✓ {s}")

# ── Seed ontology config ──────────────────────────────────────────────────────
print("\n=== Seeding ontology configs ===")
existing_onto = {c["slug"] for c in (query("configs:listOntologies", {}) or [])}

for path in sorted((ENG / "configs" / "ontology").glob("*.yaml")):
    content = path.read_text()
    try:
        spec = yaml.safe_load(content)
    except Exception as e:
        print(f"  SKIP {path.name}: {e}"); continue

    name = path.stem
    s    = slug(name)
    if s in existing_onto:
        print(f"  skip {s} (already exists)")
        continue

    call("configs:createOntology", {
        "name": name,
        "slug": s,
        "content": content,
        "parsedSpec": spec,
        "ontologyUri": spec.get("uri", ""),
        "isPublic": True,
    })
    print(f"  ✓ {s}")

# ── Seed pipeline configs ─────────────────────────────────────────────────────
print("\n=== Seeding pipeline configs ===")
existing_pipes = {c["slug"] for c in (query("configs:listPipelines", {}) or [])}

for path in sorted((ENG / "configs" / "pipelines").glob("*.yaml")):
    content = path.read_text()
    try:
        spec = yaml.safe_load(content)
    except Exception as e:
        print(f"  SKIP {path.name}: {e}"); continue

    name = path.stem
    s    = slug(name)
    if s in existing_pipes:
        print(f"  skip {s} (already exists)")
        continue

    api_slugs = list({slug(step["api"]) for step in spec.get("steps", []) if "api" in step})

    call("configs:createPipeline", {
        "name": name,
        "slug": s,
        "content": content,
        "parsedSpec": spec,
        "referencedApiSlugs": api_slugs,
        "isPublic": True,
        "tags": [],
    })
    print(f"  ✓ {s}")

print("\nDone.")
