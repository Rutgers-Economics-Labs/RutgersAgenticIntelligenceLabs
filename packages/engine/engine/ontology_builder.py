"""
Builds an owlready2 ontology from a YAML schema definition,
or loads an existing .owl file.
"""
import yaml
from pathlib import Path
from owlready2 import Thing, ObjectProperty, DataProperty, FunctionalProperty

_TYPE_MAP = {"str": str, "int": int, "float": float, "bool": bool}


def build_from_yaml(yaml_path, world):
    """
    Parse a YAML ontology schema and create owlready2 classes in the given world.
    Returns (onto, class_map) where class_map is {name: owlready2_class}.
    """
    with open(yaml_path) as f:
        spec = yaml.safe_load(f)

    onto = world.get_ontology(spec["uri"])
    class_map = {"Thing": Thing}

    with onto:
        # --- Classes ---
        for cls_spec in spec.get("classes", []):
            name = cls_spec["name"]
            parent = class_map.get(cls_spec.get("parent", "Thing"), Thing)
            cls = type(name, (parent,), {})
            class_map[name] = cls

        # --- Object properties (first pass — no inverse yet) ---
        inverse_pairs = []  # [(prop_name, inverse_name)]
        for prop_spec in spec.get("object_properties", []):
            name = prop_spec["name"]
            domain = [class_map[d] for d in prop_spec.get("domain", []) if d in class_map]
            range_ = [class_map[r] for r in prop_spec.get("range", []) if r in class_map]
            attrs = {}
            if domain:
                attrs["domain"] = domain
            if range_:
                attrs["range"] = range_
            prop = type(name, (ObjectProperty,), attrs)
            class_map[name] = prop
            if "inverse" in prop_spec:
                inverse_pairs.append((name, prop_spec["inverse"]))

        # --- Object properties (second pass — inverses) ---
        for prop_name, inv_name in inverse_pairs:
            inv = type(inv_name, (ObjectProperty,), {"inverse_property": class_map[prop_name]})
            class_map[inv_name] = inv

        # --- Data properties ---
        for prop_spec in spec.get("data_properties", []):
            name = prop_spec["name"]
            domain = [class_map.get(d, Thing) for d in prop_spec.get("domain", [])]
            range_type = _TYPE_MAP.get(prop_spec.get("range", "str"), str)
            bases = (DataProperty, FunctionalProperty) if prop_spec.get("functional") else (DataProperty,)
            attrs = {"domain": domain, "range": [range_type]}
            prop = type(name, bases, attrs)
            class_map[name] = prop

    return onto, class_map


def load_from_owl(owl_path, world):
    """
    Load an existing .owl file into the given world and return (onto, class_map).
    """
    onto = world.get_ontology(f"file://{Path(owl_path).resolve()}").load()
    class_map = {"Thing": Thing}
    for cls in onto.classes():
        class_map[cls.name] = cls
    for prop in onto.properties():
        class_map[prop.name] = prop
    return onto, class_map


def load_ontology(ontology_config, world):
    """
    Load ontology from a YAML spec or .owl file into the given world.
    Returns (onto, class_map).
    """
    path = Path(ontology_config)
    if path.suffix in (".yaml", ".yml"):
        return build_from_yaml(ontology_config, world)
    elif path.suffix == ".owl":
        return load_from_owl(ontology_config, world)
    else:
        raise ValueError(f"Unknown ontology format: {path.suffix}")
