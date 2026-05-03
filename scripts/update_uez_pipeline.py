import os, sys, json
from pathlib import Path
import httpx, yaml

PROJECT_ROOT = Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs")
UEZ_DIR = PROJECT_ROOT / "generated_projects" / "assessing-the-economic-impact-of-the-urban-enterprise-zone-program-reform"
PIPE_PATH = UEZ_DIR / ".ontology" / "pipelines" / "assessing-the-economic-impact-of-the-urban-enterprise-zone-program-reform-pipeline.yaml"

CONVEX_URL = "https://animated-caterpillar-927.convex.cloud"
DEPLOY_KEY = "prod:animated-caterpillar-927|eyJ2MiI6IjZlODZlNGJlM2Q2NTQzYTZiYjhkZmNjZGI2OGIzZWI4In0="

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
    return r.json().get("value", r.json())

def update_pipeline():
    content = PIPE_PATH.read_text()
    spec = yaml.safe_load(content)
    slug = PIPE_PATH.stem
    
    print(f"Updating Pipeline config: {slug}")
    # We need to find the ID first
    pipes = query("configs:listPipelines", {})
    pipe = next((p for p in pipes if p["slug"] == slug), None)
    if not pipe:
        print(f"Pipeline {slug} not found in Convex")
        return
    
    call("configs:updatePipeline", {
        "id": pipe["_id"],
        "content": content,
        "parsedSpec": spec,
        "referencedApiSlugs": [step["api"] for step in spec.get("steps", []) if "api" in step],
    })
    print("Pipeline updated in Convex.")

if __name__ == "__main__":
    update_pipeline()
