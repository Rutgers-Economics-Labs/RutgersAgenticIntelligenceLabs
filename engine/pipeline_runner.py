"""
Pipeline runner: reads a pipeline YAML and drives ontology hydration.
No domain knowledge — all mapping is declared in the YAML.
"""
import os
import re
import yaml
from owlready2 import World, FunctionalProperty

from engine.ontology_builder import load_ontology
from engine.api_runner import fetch_api


def _sanitize(value):
    """Make a string safe to use as an OWL local name (no spaces, etc.)."""
    return re.sub(r"[^A-Za-z0-9_\-.]", "_", str(value))


def _resolve(template, row, sanitize=False):
    """Replace {field} placeholders with row values. Set sanitize=True for URIs."""
    result = template
    for key, val in row.items():
        str_val = _sanitize(val) if (sanitize and isinstance(val, str)) else str(val)
        result = result.replace("{" + key + "}", str_val)
    return result


def _set_data_property(individual, prop_name, prop, raw_value):
    """Set a data property, casting to the declared range type."""
    try:
        range_type = prop.range[0] if prop.range else str
        if range_type == int:
            value = int(float(str(raw_value)))
        elif range_type == float:
            value = float(raw_value)
        else:
            value = str(raw_value)
    except (ValueError, TypeError):
        value = str(raw_value)

    if issubclass(prop, FunctionalProperty):
        setattr(individual, prop_name, value)
    else:
        current = getattr(individual, prop_name, []) or []
        if value not in current:
            setattr(individual, prop_name, current + [value])


def _set_object_property(individual, prop_name, prop, target):
    """Set an object property (list or scalar depending on functional)."""
    if issubclass(prop, FunctionalProperty):
        setattr(individual, prop_name, target)
    else:
        current = getattr(individual, prop_name, []) or []
        if target not in current:
            setattr(individual, prop_name, current + [target])


def _get_or_create(onto, onto_class, uri):
    """Find an existing individual by URI local name, or create it."""
    existing = onto.search_one(iri=f"*#{uri}")
    if existing is not None:
        return existing, False
    return onto_class(uri), True


def run_pipeline(pipeline_path):
    with open(pipeline_path) as f:
        pipeline = yaml.safe_load(f)

    db_path = pipeline.get("db", "ontology/onto.db")
    output_owl = pipeline.get("output_owl", "ontology/populated_ontology.owl")

    # Remove stale DB so we always start clean (hydration rebuilds from scratch)
    for stale in [db_path, db_path + "-journal"]:
        if os.path.exists(stale):
            os.remove(stale)

    # Use a fresh World() — default_world is pre-populated by owlready2 imports
    # and would cause "Cannot save existent quadstore" if the DB file exists.
    world = World()
    world.set_backend(filename=db_path)

    # Load / build ontology schema
    onto, class_map = load_ontology(pipeline["ontology"], world=world)

    resolved = {}  # {api_name: DataFrame} — for foreach resolution

    for step in pipeline["steps"]:
        step_name = step["name"]
        api_name = step["api"]
        class_name = step["class"]
        uri_template = step["uri"]
        properties = step.get("properties", {})
        relationships = step.get("relationships", [])

        print(f"\n[step] {step_name}: {class_name} <- {api_name}")

        df = fetch_api(api_name, resolved_data=resolved)
        resolved[api_name] = df

        onto_class = class_map.get(class_name)
        if onto_class is None:
            raise ValueError(f"Class '{class_name}' not found in ontology. Check ontology YAML.")

        count = 0
        with onto:
            for _, row in df.iterrows():
                row_dict = {k: v for k, v in row.to_dict().items() if not str(k).startswith("_")}

                uri = _resolve(uri_template, row_dict, sanitize=True)
                individual, created = _get_or_create(onto, onto_class, uri)

                # Data properties
                for prop_name, template in properties.items():
                    prop = class_map.get(prop_name)
                    if prop is None:
                        print(f"  Warning: property '{prop_name}' not found, skipping")
                        continue
                    raw_value = _resolve(template, row_dict)  # no sanitize — keep real values
                    _set_data_property(individual, prop_name, prop, raw_value)

                # Relationships
                for rel in relationships:
                    prop_name = rel["property"]
                    target_class_name = rel["target_class"]
                    target_uri = _resolve(rel["target_uri"], row_dict, sanitize=True)
                    create_if_missing = rel.get("create_if_missing", False)
                    create_with = rel.get("create_with_properties", {})

                    target, target_created = _get_or_create(
                        onto,
                        class_map.get(target_class_name),
                        target_uri,
                    ) if create_if_missing else (onto.search_one(iri=f"*#{target_uri}"), False)

                    if target is None:
                        continue

                    # Optionally set properties on newly created target
                    if target_created and create_with:
                        for p_name, p_template in create_with.items():
                            p = class_map.get(p_name)
                            if p:
                                _set_data_property(target, p_name, p, _resolve(p_template, row_dict))

                    prop = class_map.get(prop_name)
                    if prop:
                        _set_object_property(individual, prop_name, prop, target)

                count += 1

        print(f"  -> {count} {class_name} individuals processed")

    onto.save(file=output_owl, format="rdfxml")
    world.save()
    print(f"\nDone. Saved to {output_owl} and quadstore {db_path}")
