"""
YAML config validation and parsing.
Validates that a YAML string conforms to the expected shape for its config type.
"""
import yaml
from typing import Literal


ConfigType = Literal["api", "ontology", "pipeline"]


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
        errors.extend(_validate_ontology(spec))
    elif config_type == "pipeline":
        errors.extend(_validate_pipeline(spec))

    return errors


def _validate_api(spec: dict) -> list[str]:
    errors = []
    if "name" not in spec:
        errors.append("Missing required field: name")
    if "type" not in spec:
        errors.append("Missing required field: type")
    elif spec["type"] not in ("api", "csv", "excel"):
        errors.append(f"Invalid type '{spec['type']}': must be api, csv, or excel")

    if spec.get("type") == "api":
        if "url" not in spec:
            errors.append("Missing required field: url (required for type: api)")
        if "response_format" not in spec:
            errors.append("Missing required field: response_format (required for type: api)")
        elif spec["response_format"] not in ("json", "census_array"):
            errors.append(f"Invalid response_format '{spec['response_format']}': must be json or census_array")
        foreach = spec.get("foreach")
        if foreach:
            if "source" not in foreach:
                errors.append("foreach.source is required")
            if "field" not in foreach:
                errors.append("foreach.field is required")

    if spec.get("type") in ("csv", "excel"):
        if "path" not in spec:
            errors.append(f"Missing required field: path (required for type: {spec['type']})")

    for i, field in enumerate(spec.get("fields", [])):
        if "computed" not in field and "source" not in field:
            errors.append(f"fields[{i}]: must have either 'source' or 'computed'")
        if "computed" in field and "alias" not in field:
            errors.append(f"fields[{i}]: computed fields require an 'alias'")
        if "cast" in field and field["cast"] not in ("int", "float", "str"):
            errors.append(f"fields[{i}]: invalid cast '{field['cast']}': must be int, float, or str")

    return errors


def _validate_ontology(spec: dict) -> list[str]:
    errors = []
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
        if "range" in prop and prop["range"] not in ("str", "int", "float", "bool"):
            errors.append(f"data_properties[{i}]: invalid range '{prop['range']}'")
    return errors


def _validate_pipeline(spec: dict) -> list[str]:
    errors = []
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
