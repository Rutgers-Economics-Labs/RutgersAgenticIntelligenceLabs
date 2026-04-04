# WO-0.1 — Ontology Kernel YAML

**Status:** ready  
**Spec:** `specs/ontology-kernel.md`  
**Depends on:** nothing  
**Blocks:** WO-0.2, WO-1.2, platform-objects template  

---

## Goal

Create the kernel YAML file and inject it into every project ontology at hydration time, so all individuals automatically carry the 6 universal provenance properties.

---

## Files

| File | Action | Notes |
|------|--------|-------|
| `packages/engine/ontology/kernel.yaml` | **Create** | The kernel definition |
| `packages/api/app/services/hydration_worker.py` | **Modify** | Prepend kernel before writing tmpdir configs |
| `packages/api/app/services/yaml_service.py` | **Modify** | Allow kernel property names in project configs without raising duplicate errors |

---

## Steps

### 1. Create `packages/engine/ontology/kernel.yaml`

```yaml
uri: http://rail.rutgers.edu/ontology/kernel
data_properties:
  - name: hasName
    domain: [Thing]
    range: str
    functional: true
  - name: hasSource
    domain: [Thing]
    range: str
    functional: true
  - name: hasSourceURL
    domain: [Thing]
    range: str
    functional: true
  - name: hasIngestDate
    domain: [Thing]
    range: str
    functional: true
  - name: hasPipelineID
    domain: [Thing]
    range: str
    functional: true
  - name: hasCreatedAt
    domain: [Thing]
    range: str
    functional: true
```

### 2. Add kernel merge helper in `hydration_worker.py`

Add a `_merge_kernel(ontology_yaml: str) -> str` function:

```python
def _merge_kernel(project_onto_yaml: str) -> str:
    """Prepend kernel data_properties to the project ontology."""
    kernel_path = Path(__file__).parent.parent.parent.parent / "engine/ontology/kernel.yaml"
    # also check settings.engine_root
    kernel = yaml.safe_load(kernel_path.read_text())
    project = yaml.safe_load(project_onto_yaml)
    
    kernel_props = kernel.get("data_properties", [])
    project_props = project.get("data_properties", [])
    
    # Kernel takes precedence — remove any project property with same name as kernel
    kernel_names = {p["name"] for p in kernel_props}
    filtered_project_props = [p for p in project_props if p["name"] not in kernel_names]
    
    project["data_properties"] = kernel_props + filtered_project_props
    return yaml.dump(project, default_flow_style=False)
```

In `hydration_worker.run()`, call this on each ontology config before writing to tmpdir:

```python
# Existing: write onto config to tmpdir
# Change to:
merged_onto = _merge_kernel(onto_content)
(tmpdir / "configs/ontology" / f"{slug}.yaml").write_text(merged_onto)
```

### 3. Update `yaml_service.validate()` for `"ontology"` type

In the ontology validation block, after parsing `data_properties`, do not raise an error if a property name matches one of the 6 kernel names. Log a warning instead:

```python
KERNEL_PROPERTY_NAMES = {"hasName", "hasSource", "hasSourceURL", "hasIngestDate", "hasPipelineID", "hasCreatedAt"}

# In validate(), ontology section:
for prop in data_properties:
    if prop.get("name") in KERNEL_PROPERTY_NAMES:
        # Don't error — but note that kernel version takes precedence at runtime
        warnings.append(f"Property '{prop['name']}' is a kernel property and will be overridden at hydration time.")
```

---

## Acceptance

- [ ] `packages/engine/ontology/kernel.yaml` exists and is valid YAML
- [ ] Running a hydration writes a merged ontology YAML to tmpdir that includes all 6 kernel properties
- [ ] The engine builds individuals with `hasName`, `hasSource`, etc. available
- [ ] `yaml_service.validate()` does not error on ontology configs that include kernel property names
- [ ] `make hydrate` against the existing NJ pipeline completes without errors
