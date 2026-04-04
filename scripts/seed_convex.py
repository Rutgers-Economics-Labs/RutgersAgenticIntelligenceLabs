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

# ── Seed Connector Templates ──────────────────────────────────────────────────
print("\n=== Seeding Connector Templates ===")
existing_connectors = {c["slug"] for c in (query("connectors:list", {}) or [])}

SEED_CONNECTORS = [
    {
        "slug": "fred-observations",
        "name": "FRED Series Observations",
        "description": "Fetch observations for any FRED series via the St. Louis Fed API",
        "version": "1.0",
        "tags": ["economics", "time-series", "fred"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.stlouisfed.org/fred/series/observations",
            "params": {"api_key": "${FRED_API_KEY}", "file_type": "json"},
            "response_format": "json",
            "response_path": "observations",
            "fields": [{"source": "date", "alias": "date"}, {"source": "value", "alias": "value", "cast": "float"}]
        })
    },
    {
        "slug": "fred-series-info",
        "name": "FRED Series Metadata",
        "description": "Series metadata (units, frequency, title)",
        "version": "1.0",
        "tags": ["economics", "metadata", "fred"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.stlouisfed.org/fred/series",
            "params": {"api_key": "${FRED_API_KEY}", "file_type": "json"},
            "response_format": "json",
            "response_path": "seriess",
            "fields": [{"source": "id", "alias": "series_id"}, {"source": "title", "alias": "title"}, {"source": "units", "alias": "units"}]
        })
    },
    {
        "slug": "census-acs5-table",
        "name": "Census ACS 5-Year Estimates",
        "description": "ACS 5-year estimates, any table",
        "version": "1.0",
        "tags": ["demographics", "census"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.census.gov/data/2022/acs/acs5",
            "response_format": "census_array",
            "fields": []
        })
    },
    {
        "slug": "census-decennial",
        "name": "Census Decennial",
        "description": "Decennial population table",
        "version": "1.0",
        "tags": ["demographics", "census"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.census.gov/data/2020/dec/pl",
            "response_format": "census_array",
            "fields": []
        })
    },
    {
        "slug": "census-tigerweb-counties",
        "name": "Census TIGER/Web Counties",
        "description": "County geometry/FIPS list",
        "version": "1.0",
        "tags": ["geography", "census"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query",
            "params": {"f": "json", "where": "1=1", "outFields": "*"},
            "response_format": "json",
            "response_path": "features",
            "fields": []
        })
    },
    {
        "slug": "bls-series",
        "name": "BLS Time Series",
        "description": "Single time series from BLS API v2",
        "version": "1.0",
        "tags": ["economics", "bls"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            "response_format": "json",
            "response_path": "Results.series.0.data",
            "fields": [{"source": "year", "alias": "year"}, {"source": "period", "alias": "period"}, {"source": "value", "alias": "value", "cast": "float"}]
        })
    },
    {
        "slug": "bls-lau",
        "name": "BLS LAU",
        "description": "Local Area Unemployment Statistics",
        "version": "1.0",
        "tags": ["economics", "bls", "unemployment"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            "response_format": "json",
            "response_path": "Results.series.0.data",
            "fields": []
        })
    },
    {
        "slug": "worldbank-indicator",
        "name": "World Bank Indicator",
        "description": "Country indicator time series",
        "version": "1.0",
        "tags": ["economics", "global"],
        "content": yaml.dump({
            "type": "api",
            "url": "http://api.worldbank.org/v2/country/all/indicator/",
            "params": {"format": "json"},
            "response_format": "json",
            "fields": []
        })
    },
    {
        "slug": "worldbank-country-info",
        "name": "World Bank Country Info",
        "description": "Country metadata",
        "version": "1.0",
        "tags": ["geography", "global"],
        "content": yaml.dump({
            "type": "api",
            "url": "http://api.worldbank.org/v2/country",
            "params": {"format": "json"},
            "response_format": "json",
            "fields": []
        })
    },
    {
        "slug": "bea-regional",
        "name": "BEA Regional",
        "description": "Regional economic accounts",
        "version": "1.0",
        "tags": ["economics", "bea"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://apps.bea.gov/api/data",
            "params": {"ResultFormat": "json"},
            "response_format": "json",
            "response_path": "BEAAPI.Results.Data",
            "fields": []
        })
    },
    {
        "slug": "oecd-dataset",
        "name": "OECD Dataset",
        "description": "OECD SDMX-JSON dataset",
        "version": "1.0",
        "tags": ["economics", "global", "oecd"],
        "content": yaml.dump({
            "type": "api",
            "url": "https://stats.oecd.org/SDMX-JSON/data/",
            "response_format": "json",
            "fields": []
        })
    },
    {
        "slug": "csv-local",
        "name": "Local CSV File",
        "description": "Local CSV file",
        "version": "1.0",
        "tags": ["file", "csv"],
        "content": yaml.dump({
            "type": "csv",
            "path": "",
            "fields": []
        })
    },
    {
        "slug": "excel-local",
        "name": "Local Excel File",
        "description": "Local Excel file (.xlsx)",
        "version": "1.0",
        "tags": ["file", "excel"],
        "content": yaml.dump({
            "type": "excel",
            "path": "",
            "fields": []
        })
    },
    {
        "slug": "json-rest",
        "name": "Generic JSON REST API",
        "description": "Generic REST API returning JSON",
        "version": "1.0",
        "tags": ["generic", "api"],
        "content": yaml.dump({
            "type": "api",
            "url": "",
            "response_format": "json",
            "fields": []
        })
    },
    {
        "slug": "csv-url",
        "name": "CSV from URL",
        "description": "CSV served at a URL",
        "version": "1.0",
        "tags": ["generic", "csv"],
        "content": yaml.dump({
            "type": "api",
            "url": "",
            "response_format": "csv",
            "fields": []
        })
    }
]

for tmpl in SEED_CONNECTORS:
    if tmpl["slug"] in existing_connectors:
        print(f"  skip {tmpl['slug']} (already exists)")
        continue
    call("connectors:create", tmpl)
    print(f"  ✓ {tmpl['slug']}")

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
