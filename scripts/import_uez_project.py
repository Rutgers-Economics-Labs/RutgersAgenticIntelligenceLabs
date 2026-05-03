import os, sys, json
from pathlib import Path
import httpx, yaml

PROJECT_ROOT = Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs")
UEZ_DIR = PROJECT_ROOT / "generated_projects" / "assessing-the-economic-impact-of-the-urban-enterprise-zone-program-reform"
RAIL_YAML = UEZ_DIR / "rail.yaml"

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
    result = r.json()
    return result.get("value", result)

def import_project():
    if not RAIL_YAML.exists():
        print(f"Error: {RAIL_YAML} not found")
        return

    manifest = yaml.safe_load(RAIL_YAML.read_text())
    p_meta = manifest["project"]
    slug = p_meta["slug"]

    # 1. Create API configs
    api_slugs = []
    sources_dir = UEZ_DIR / ".ontology" / "sources"
    for path in sources_dir.glob("*.yaml"):
        content = path.read_text()
        spec = yaml.safe_load(content)
        s = path.stem
        print(f"Creating API config: {s}")
        call("configs:createApi", {
            "name": spec["name"],
            "slug": s,
            "content": content,
            "parsedSpec": spec,
            "isPublic": False,
            "tags": [],
        })
        api_slugs.append(s)

    # 2. Create Ontology config
    onto_path = UEZ_DIR / ".ontology" / "ontologies" / f"{slug}-ontology.yaml"
    if onto_path.exists():
        content = onto_path.read_text()
        spec = yaml.safe_load(content)
        print(f"Creating Ontology config: {slug}-ontology")
        call("configs:createOntology", {
            "name": f"{p_meta['name']} Ontology",
            "slug": f"{slug}-ontology",
            "content": content,
            "parsedSpec": spec,
            "ontologyUri": spec.get("uri", ""),
            "isPublic": False,
        })

    # 3. Create Pipeline config
    pipe_path = UEZ_DIR / ".ontology" / "pipelines" / f"{slug}-pipeline.yaml"
    if pipe_path.exists():
        content = pipe_path.read_text()
        spec = yaml.safe_load(content)
        print(f"Creating Pipeline config: {slug}-pipeline")
        call("configs:createPipeline", {
            "name": f"{p_meta['name']} Pipeline",
            "slug": f"{slug}-pipeline",
            "content": content,
            "parsedSpec": spec,
            "referencedApiSlugs": api_slugs,
            "isPublic": False,
            "tags": [],
        })

    # 4. Create Project
    print(f"Creating Project: {slug}")
    create_payload = {
        "name": p_meta["name"],
        "slug": slug,
        "description": p_meta.get("description", ""),
        "approach": "ontology-first",
        "localRepoPath": str(UEZ_DIR),
        "manifestPath": "rail.yaml",
    }
    result = call("projects:create", create_payload)
    if isinstance(result, dict) and result.get("status") == "error":
        print(f"Error creating project: {result['errorMessage']}")
        return
    
    project_id = result
    print(f"Project created with ID: {project_id}")

    # 5. Update Project with configs
    print(f"Updating Project with configs...")
    update_payload = {
        "projectId": project_id,
        "ontologyConfigSlug": f"{slug}-ontology",
        "pipelineConfigSlug": f"{slug}-pipeline",
        "apiConfigSlugs": api_slugs,
    }
    call("projects:updateById", update_payload)
    print("Project updated.")

if __name__ == "__main__":
    import_project()
