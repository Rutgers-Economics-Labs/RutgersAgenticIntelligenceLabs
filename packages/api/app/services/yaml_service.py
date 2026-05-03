"""
YAML config validation and parsing.
Validates that a YAML string conforms to the expected shape for its config type.
"""
from __future__ import annotations

import importlib.util
import yaml
from pathlib import Path
from typing import Literal


ConfigType = Literal["api", "ontology", "pipeline", "agent"]


def parse(content: str) -> dict:
    """Parse a YAML string; raises ValueError with a clean message on failure."""
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")


def validate(config_type: ConfigType, content: str) -> list[str]:
    """
    Validate a YAML string for the given config type.
    Returns a list of error strings (empty = valid).
    """
    errors = []
    try:
        spec = parse(content)
    except ValueError as e:
        return [str(e)]

    if config_type == "api":
        errors.extend(_validate_api(spec))
    elif config_type == "ontology":
        ont_errors, warnings = _validate_ontology(spec)
        errors.extend(ont_errors)
        if warnings:
            import logging
            logger = logging.getLogger("rail.yaml_service")
            for w in warnings:
                logger.warning(w)
    elif config_type == "pipeline":
        errors.extend(_validate_pipeline(spec))
    elif config_type == "agent":
        errors.extend(_validate_agent(spec))

    return errors


def validate_agent_runnable(content: str, project_root: Path) -> list[str]:
    """
    Validate that an agent config is structurally sound and that its referenced
    prompt/checklist files exist and use allowed repo-relative paths.
    """
    errors: list[str] = []
    errors.extend(validate("agent", content))
    if errors:
        return errors

    try:
        spec = parse(content)
    except ValueError as e:
        return [str(e)]

    role = spec.get("role")

    # Check that paths are repo-relative
    permissions = spec.get("permissions") or {}
    all_paths = (
        (permissions.get("read") or []) +
        (permissions.get("write") or []) +
        (permissions.get("deny") or [])
    )
    for p in all_paths:
        if str(p).startswith("/") or ".." in str(p):
            errors.append(f"Configured path '{p}' is not strictly repo-relative")

    prompts = spec.get("prompts", {})
    system_path = prompts.get("system")
    checklist_path = prompts.get("checklist")

    for name, p in [("system", system_path), ("checklist", checklist_path)]:
        if p:
            if str(p).startswith("/") or ".." in str(p):
                errors.append(f"Prompt path '{p}' is not strictly repo-relative")
            else:
                full_path = project_root / str(p)
                if not full_path.is_file():
                    errors.append(f"Referenced {name} prompt file does not exist: {p}")

    return errors


def load_agent_prompts(content: str, project_root: Path) -> tuple[str, str]:
    """
    Given a valid agent yaml config, loads and returns the system prompt and checklist contents.
    Returns (system_prompt_text, checklist_text).
    """
    spec = parse(content)
    prompts = spec.get("prompts", {})

    sys_val = prompts.get("system")
    chk_val = prompts.get("checklist")

    system_text = ""
    checklist_text = ""

    if sys_val:
        system_path = project_root / str(sys_val)
        system_text = system_path.read_text(encoding="utf-8") if system_path.is_file() else ""

    if chk_val:
        checklist_path = project_root / str(chk_val)
        checklist_text = checklist_path.read_text(encoding="utf-8") if checklist_path.is_file() else ""

    return system_text, checklist_text


ALLOWED_TOP_LEVEL_API_FIELDS = {
    "name", "type", "url", "path", "params", "headers", "response_format",
    "response_path", "fields", "foreach", "cache_ttl", "extends", "fields_append",
    "description", "version", "tags", "slug", "isPublic", "cache", "drop_na",
    "storage_key", "javascript", "extraction_mode", "pages",
    # metadata sandbox — ignored by engine, safe for agent/researcher notes
    "meta",
    # column contract for hallucination prevention
    "schema_contract",
    # connection fields for sql_mirror handler
    "connection_string", "query", "table",
}

def _validate_api(spec: dict) -> list[str]:
    errors = []

    for key in spec.keys():
        if key not in ALLOWED_TOP_LEVEL_API_FIELDS:
            errors.append(f"Unknown field: {key}")

    is_extends = "extends" in spec

    if "name" not in spec and not is_extends:
        errors.append("Missing required field: name")
    if "type" not in spec and not is_extends:
        errors.append("Missing required field: type")
    elif "type" in spec and spec["type"] not in (
        "api", "http_json", "csv", "excel", "uploaded", "scrape",
        "pdf", "docx", "parquet", "sql_mirror",
    ):
        errors.append(
            f"Invalid type '{spec['type']}': must be one of "
            "api, http_json, csv, excel, uploaded, scrape, pdf, docx, parquet, sql_mirror"
        )

    if spec.get("type") == "api":
        if "url" not in spec and not is_extends:
            errors.append("Missing required field: url (required for type: api)")
        if "response_format" not in spec and not is_extends:
            errors.append("Missing required field: response_format (required for type: api)")
        elif "response_format" in spec and spec["response_format"] not in ("json", "census_array"):
            errors.append(f"Invalid response_format '{spec['response_format']}': must be json or census_array")
        foreach = spec.get("foreach")
        if foreach:
            if "source" not in foreach:
                errors.append("foreach.source is required")
            if "field" not in foreach:
                errors.append("foreach.field is required")

    if spec.get("type") in ("csv", "excel") and not is_extends:
        if "path" not in spec:
            errors.append(f"Missing required field: path (required for type: {spec['type']})")

    if spec.get("type") == "parquet" and not is_extends:
        if "path" not in spec and "url" not in spec and "storage_key" not in spec:
            errors.append("type: parquet requires exactly one of path, url, or storage_key")

    if spec.get("type") == "sql_mirror" and not is_extends:
        if "connection_string" not in spec:
            errors.append("type: sql_mirror requires connection_string")
        if "query" not in spec and "table" not in spec:
            errors.append("type: sql_mirror requires either query or table")

    if spec.get("type") == "uploaded" and not is_extends:
        has_path = "path" in spec
        has_storage_key = "storage_key" in spec
        if sum(bool(x) for x in (has_path, has_storage_key)) != 1:
            errors.append("type: uploaded requires exactly one of path or storage_key")

    if spec.get("type") == "scrape":
        if "url" not in spec and not is_extends:
            errors.append("Missing required field: url (required for type: scrape)")
        if "javascript" in spec and not isinstance(spec["javascript"], bool):
            errors.append("javascript must be a boolean for type: scrape")

    if spec.get("type") in ("pdf", "docx") and not is_extends:
        has_path = "path" in spec
        has_url = "url" in spec
        has_storage_key = "storage_key" in spec
        if sum(bool(option) for option in (has_path, has_url, has_storage_key)) != 1:
            errors.append(f"type: {spec['type']} requires exactly one of path, url, or storage_key")
        mode = spec.get("extraction_mode")
        if mode not in ("tables", "prose", "both"):
            errors.append("extraction_mode must be one of tables, prose, or both")
        page_spec = spec.get("pages")
        if page_spec is not None and not isinstance(page_spec, str):
            errors.append("pages must be a string like '1' or '1-3'")
        elif isinstance(page_spec, str):
            import re
            if not re.fullmatch(r"\d+(-\d+)?", page_spec):
                errors.append("pages must match pattern \\d+(-\\d+)?")

    for i, field in enumerate(spec.get("fields", [])):
        if "computed" not in field and "source" not in field:
            errors.append(f"fields[{i}]: must have either 'source' or 'computed'")
        if "computed" in field and "alias" not in field:
            errors.append(f"fields[{i}]: computed fields require an 'alias'")
        if "cast" in field and field["cast"] not in ("int", "float", "str"):
            errors.append(f"fields[{i}]: invalid cast '{field['cast']}': must be int, float, or str")

    return errors


def _validate_ontology(spec: dict) -> tuple[list[str], list[str]]:
    KERNEL_PROPERTY_NAMES = {"hasName", "hasSource", "hasSourceURL", "hasIngestDate", "hasPipelineID", "hasCreatedAt"}
    errors = []
    warnings = []
    if "uri" not in spec:
        errors.append("Missing required field: uri")
    for i, cls in enumerate(spec.get("classes", [])):
        if "name" not in cls:
            errors.append(f"classes[{i}]: missing name")
    for i, prop in enumerate(spec.get("object_properties", [])):
        if "name" not in prop:
            errors.append(f"object_properties[{i}]: missing name")
    for i, prop in enumerate(spec.get("data_properties", [])):
        if "name" not in prop:
            errors.append(f"data_properties[{i}]: missing name")
        elif prop["name"] in KERNEL_PROPERTY_NAMES:
            warnings.append(f"Property '{prop['name']}' is a kernel property and will be overridden at hydration time.")

        if "range" in prop and prop["range"] not in ("str", "int", "float", "bool"):
            errors.append(f"data_properties[{i}]: invalid range '{prop['range']}'")
    return errors, warnings


PIPELINE_ALLOWED_MODES = {"full", "incremental"}
ALLOWED_TOP_LEVEL_PIPELINE_FIELDS = {
    "ontology", "steps", "hydration_mode", "schedule", "post_hydration_transforms",
    "output_owl", "db", "duckdb",
    # metadata sandbox — ignored by engine, safe for agent/researcher notes
    "meta",
}

def _validate_agent(spec: dict) -> list[str]:
    errors = []

    if not isinstance(spec, dict):
        return ["Agent config must be an object"]

    if "role" not in spec:
        errors.append("Missing required field: role")

    # validate threading
    threading = spec.get("threading", {})
    if not isinstance(threading, dict):
        errors.append("threading must be an object")
    else:
        mode = threading.get("mode")
        if mode and mode not in ("project_scoped", "task_scoped"):
            errors.append(f"Invalid threading.mode '{mode}': must be project_scoped or task_scoped")

    # validate permissions
    permissions = spec.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append("permissions must be an object")
    else:
        writes = set(permissions.get("write") or [])
        denies = set(permissions.get("deny") or [])
        overlap = writes.intersection(denies)
        if overlap:
            errors.append(f"Paths cannot be both allowed writes and denied: {sorted(overlap)}")

    # validate prompts
    prompts = spec.get("prompts")
    if not prompts:
        errors.append("Missing required field: prompts")
    elif not isinstance(prompts, dict):
        errors.append("prompts must be an object")
    else:
        if not prompts.get("system"):
            errors.append("Missing required field: prompts.system")
        if not prompts.get("checklist"):
            errors.append("Missing required field: prompts.checklist")

    # validate completion for write roles
    has_writes = bool(spec.get("permissions", {}).get("write", []))
    if has_writes:
        completion = spec.get("completion", {})
        if not isinstance(completion, dict):
            errors.append("completion must be an object for write-capable roles")
        elif not completion.get("requires"):
            errors.append("Write-capable roles must have non-empty completion requirements")

    return errors


def _validate_pipeline(spec: dict) -> list[str]:
    errors = []

    for key in spec.keys():
        if key not in ALLOWED_TOP_LEVEL_PIPELINE_FIELDS:
            errors.append(f"Unknown field: {key}")

    mode = spec.get("hydration_mode", "full")
    if mode not in PIPELINE_ALLOWED_MODES:
        errors.append(f"hydration_mode must be 'full' or 'incremental', got '{mode}'")

    if "schedule" in spec and not isinstance(spec["schedule"], dict):
        errors.append("schedule must be an object")

    if "ontology" not in spec:
        errors.append("Missing required field: ontology")
    if "steps" not in spec:
        errors.append("Missing required field: steps")
    for i, step in enumerate(spec.get("steps", [])):
        for field in ("name", "api", "class", "uri"):
            if field not in step:
                errors.append(f"steps[{i}]: missing required field '{field}'")
        for j, rel in enumerate(step.get("relationships", [])):
            for field in ("property", "target_class", "target_uri"):
                if field not in rel:
                    errors.append(f"steps[{i}].relationships[{j}]: missing required field '{field}'")
    return errors


def _check_transform_resolvable(spec_str: str, transform_dir: Path) -> str | None:
    """Return an error message if module::function cannot be loaded from transform_dir (or import)."""
    spec_str = (spec_str or "").strip()
    if not spec_str:
        return None
    if "::" in spec_str:
        module_name, func_name = spec_str.split("::", 1)
    else:
        module_name, func_name = spec_str, "transform"
    module_name, func_name = module_name.strip(), func_name.strip()
    if not module_name or not func_name:
        return f"Invalid transform spec '{spec_str}'"

    py_path = transform_dir / f"{module_name}.py"
    try:
        if py_path.is_file():
            spec = importlib.util.spec_from_file_location(module_name, py_path)
            if spec is None or spec.loader is None:
                return f"Transform '{spec_str}': could not load {py_path}"
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        else:
            mod = importlib.import_module(module_name)
    except Exception as e:
        return f"Transform '{spec_str}': {e}"

    if not hasattr(mod, func_name):
        return f"Transform '{spec_str}': function '{func_name}' not found"
    return None


def _resolve_ontology_yaml(
    onto_ref: str,
    ontology_yaml: str | None,
    engine_root: Path | None,
) -> tuple[str | None, list[str]]:
    """Return (yaml_text, errors)."""
    if ontology_yaml is not None and ontology_yaml.strip():
        return ontology_yaml, []
    if engine_root is None:
        return None, [
            f"Ontology '{onto_ref}' is not in Convex and engine_root is unset — "
            "cannot load configs/ontology/{onto_ref}.yaml"
        ]

    # Backwards compatibility: some pipelines reference ontology by engine-relative path,
    # e.g. "configs/ontology/core.yaml". Prefer that if it exists.
    onto_ref_str = (onto_ref or "").strip()
    if onto_ref_str.endswith(".yaml") or "/" in onto_ref_str or "\\" in onto_ref_str:
        candidate = (engine_root / onto_ref_str).resolve()
        try:
            # Ensure the resolved path stays within the engine root.
            candidate.relative_to(engine_root.resolve())
            if candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8"), []
                except OSError as e:
                    return None, [f"Could not read ontology file {candidate}: {e}"]
        except Exception:
            # If it's outside engine_root or can't be resolved, fall back to slug behavior.
            pass

    path = engine_root / "configs" / "ontology" / f"{onto_ref_str}.yaml"
    if not path.is_file():
        fallback = engine_root / "configs" / "ontology" / "core.yaml"
        if fallback.is_file():
            path = fallback
        else:
            return None, [
                f"Ontology '{onto_ref_str}' not found in Convex and no file at {path} "
                f"(or fallback core.yaml)"
            ]
    try:
        return path.read_text(encoding="utf-8"), []
    except OSError as e:
        return None, [f"Could not read ontology file {path}: {e}"]


def validate_pipeline_runnable(
    pipeline_content: str,
    api_yaml_by_slug: dict[str, str],
    *,
    ontology_yaml: str | None,
    engine_root: Path | None = None,
    transform_dir: Path | None = None,
) -> list[str]:
    """
    Structural pipeline validation plus checks that would fail at hydration time:
    referenced API YAMLs exist and are valid, ontology classes/properties match steps,
    foreach source order, transform specs resolvable on disk (when transform_dir is set).
    """
    errors: list[str] = []
    errors.extend(validate("pipeline", pipeline_content))
    if errors:
        return errors

    try:
        pipe = parse(pipeline_content)
    except ValueError as e:
        return [str(e)]

    onto_ref = str(pipe.get("ontology", "core")).strip() or "core"
    onto_text, onto_errs = _resolve_ontology_yaml(onto_ref, ontology_yaml, engine_root)
    errors.extend(onto_errs)
    if onto_text is None:
        return errors

    ont_shape_errors = validate("ontology", onto_text)
    errors.extend(ont_shape_errors)
    if ont_shape_errors:
        return errors

    try:
        onto_spec = parse(onto_text)
    except ValueError as e:
        errors.append(str(e))
        return errors

    class_names = {"Thing", *(c["name"] for c in onto_spec.get("classes", []) if "name" in c)}
    obj_prop_names = {p["name"] for p in onto_spec.get("object_properties", []) if "name" in p}
    data_prop_names = {p["name"] for p in onto_spec.get("data_properties", []) if "name" in p}

    steps = pipe.get("steps", [])
    prior_api_slugs: list[str] = []

    for i, step in enumerate(steps):
        api_slug = step.get("api")
        if not api_slug:
            continue
        raw = api_yaml_by_slug.get(api_slug)
        if raw is None:
            errors.append(
                f"steps[{i}] api '{api_slug}': no API config YAML (missing in Convex or bundle)"
            )
            continue

        errors.extend(validate("api", raw))
        try:
            api_spec = parse(raw)
        except ValueError as e:
            errors.append(f"steps[{i}] api '{api_slug}': {e}")
            prior_api_slugs.append(api_slug)
            continue

        fe = api_spec.get("foreach") or {}
        if fe:
            src = fe.get("source")
            if not src:
                errors.append(f"steps[{i}] api '{api_slug}': foreach.source is required")
            elif src not in prior_api_slugs:
                errors.append(
                    f"steps[{i}] api '{api_slug}': foreach source '{src}' must appear in an "
                    f"earlier pipeline step (prior steps use apis: {prior_api_slugs})"
                )

        prior_api_slugs.append(api_slug)

        cls_name = step.get("class")
        if cls_name and cls_name not in class_names:
            errors.append(
                f"steps[{i}]: class '{cls_name}' is not defined in the ontology "
                f"(available: {sorted(class_names)})"
            )

        for pk in step.get("properties", {}).keys():
            if data_prop_names and pk not in data_prop_names:
                errors.append(
                    f"steps[{i}]: property '{pk}' is not a data property in the ontology"
                )

        for j, rel in enumerate(step.get("relationships", [])):
            pn = rel.get("property")
            if pn and pn not in obj_prop_names:
                errors.append(
                    f"steps[{i}].relationships[{j}]: object property '{pn}' "
                    f"is not defined in the ontology"
                )
            tc = rel.get("target_class")
            if tc and tc not in class_names:
                errors.append(
                    f"steps[{i}].relationships[{j}]: target_class '{tc}' "
                    f"is not defined in the ontology"
                )

        ts = step.get("transform")
        if ts and transform_dir and transform_dir.is_dir():
            msg = _check_transform_resolvable(ts, transform_dir)
            if msg:
                errors.append(f"steps[{i}]: {msg}")

    for k, entry in enumerate(pipe.get("post_hydration_transforms", [])):
        if isinstance(entry, str):
            spec = entry
        else:
            spec = entry.get("spec", "")
        if spec and transform_dir and transform_dir.is_dir():
            msg = _check_transform_resolvable(spec, transform_dir)
            if msg:
                errors.append(f"post_hydration_transforms[{k}]: {msg}")

    return errors
