"""
Pipeline runner: reads a pipeline YAML and drives ontology hydration.
No domain knowledge — all mapping is declared in the YAML.
"""
import os
import re
import yaml


_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_\-.]")
FunctionalProperty = None

def _sanitize(value):
    """Make a string safe to use as an OWL local name (no spaces, etc.)."""
    return _SAFE_CHARS_RE.sub("_", str(value))


_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")

def _resolve(template, row, sanitize=False):
    """Replace {field} placeholders with row values. Set sanitize=True for URIs."""
    def replacer(match):
        key = match.group(1)
        if key in row:
            val = row[key]
            return _sanitize(val) if (sanitize and isinstance(val, str)) else str(val)
        return match.group(0)

    return _PLACEHOLDER_RE.sub(replacer, template)


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

    if FunctionalProperty is not None and issubclass(prop, FunctionalProperty):
        setattr(individual, prop_name, value)
    else:
        current = getattr(individual, prop_name, []) or []
        if value not in current:
            setattr(individual, prop_name, current + [value])


def _set_object_property(individual, prop_name, prop, target):
    """Set an object property (list or scalar depending on functional)."""
    if FunctionalProperty is not None and issubclass(prop, FunctionalProperty):
        setattr(individual, prop_name, target)
    else:
        current = getattr(individual, prop_name, []) or []
        if target not in current:
            setattr(individual, prop_name, current + [target])


def _get_or_create(onto, onto_class, uri, cache):
    """Find an existing individual by URI local name, or create it. Uses cache to avoid repeat DB queries."""
    if uri in cache:
        return cache[uri], False
    existing = onto.search_one(iri=f"*#{uri}")
    if existing is not None:
        cache[uri] = existing
        return existing, False
    ind = onto_class(uri)
    cache[uri] = ind
    return ind, True


def run_pipeline(pipeline_path):
    global FunctionalProperty
    from owlready2 import World, FunctionalProperty as OwlreadyFunctionalProperty
    from engine.ontology_builder import load_ontology
    from engine.api_runner import fetch_api
    from engine.transform_runner import run_dataframe_transform, run_ontology_transform
    import duckdb
    import pandas as pd

    FunctionalProperty = OwlreadyFunctionalProperty
    print(f"[pipeline] Loading pipeline YAML: {pipeline_path}")
    with open(pipeline_path) as f:
        pipeline = yaml.safe_load(f)

    db_path = pipeline.get("db", "ontology/onto.db")
    output_owl = pipeline.get("output_owl", "ontology/populated_ontology.owl")
    steps = pipeline.get("steps") or []
    print(
        f"[pipeline] {len(steps)} step(s); ontology schema file: {pipeline.get('ontology')}; "
        f"quadstore: {db_path}; OWL export: {output_owl}"
    )

    hydration_mode = os.environ.get("RAIL_HYDRATION_MODE", "full")

    # Remove stale DB so we always start clean, UNLESS incremental mode
    if hydration_mode != "incremental":
        for stale in [db_path, db_path + "-journal"]:
            if os.path.exists(stale):
                os.remove(stale)

    # Use a fresh World() — default_world is pre-populated by owlready2 imports
    # and would cause "Cannot save existent quadstore" if the DB file exists.
    world = World(filename=db_path)

    # Load / build ontology schema
    print(f"[pipeline] Loading ontology from {pipeline['ontology']!r} …")
    onto, class_map = load_ontology(pipeline["ontology"], world=world)
    print(f"[pipeline] Ontology ready ({len(class_map)} symbols in map, including properties)")

    resolved = {}  # {api_name: DataFrame} — for foreach resolution
    _cache = {}    # {uri: individual} — avoids repeat SQLite searches

    for step in pipeline["steps"]:
        step_name = step["name"]
        api_name = step["api"]
        class_name = step["class"]
        uri_template = step["uri"]
        properties = step.get("properties", {})
        relationships = step.get("relationships", [])

        print(f"\n[step] {step_name}: {class_name} <- {api_name}")

        df = fetch_api(api_name, resolved_data=resolved)
        cols = list(df.columns)
        col_preview = ", ".join(str(c) for c in cols[:12])
        if len(cols) > 12:
            col_preview += f", … (+{len(cols) - 12} more)"
        print(f"  [data] {len(df)} rows, {len(cols)} columns: {col_preview}")

        # Optional DataFrame transform (pre-ontology mapping)
        transform_spec = step.get("transform")
        if transform_spec:
            transform_cfg = step.get("transform_config", {})
            print(f"  [transform] {transform_spec}")
            df = run_dataframe_transform(transform_spec, df, config=transform_cfg)

        resolved[api_name] = df

        limit = step.get("limit")
        if limit:
            df = df.head(int(limit))

        onto_class = class_map.get(class_name)
        if onto_class is None:
            raise ValueError(f"Class '{class_name}' not found in ontology. Check ontology YAML.")

        count = 0
        with onto:
            # Iterating over dicts is faster than iterrows() + Series.to_dict()
            for row_dict in df.to_dict("records"):
                # Skip internal columns
                row_dict = {k: v for k, v in row_dict.items() if not str(k).startswith("_")}

                uri = _resolve(uri_template, row_dict, sanitize=True)
                individual, created = _get_or_create(onto, onto_class, uri, _cache)

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

                    if create_if_missing:
                        target, target_created = _get_or_create(
                            onto, class_map.get(target_class_name), target_uri, _cache
                        )
                    else:
                        target = _cache.get(target_uri) or onto.search_one(iri=f"*#{target_uri}")
                        if target and target_uri not in _cache:
                            _cache[target_uri] = target
                        target_created = False

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

    # Post-hydration ontology transforms
    for entry in pipeline.get("post_hydration_transforms", []):
        if isinstance(entry, str):
            spec, cfg = entry, {}
        else:
            spec, cfg = entry["spec"], entry.get("config", {})
        print(f"\n[post-transform] {spec}")
        with onto:
            run_ontology_transform(spec, onto, config=cfg)

    # Optional DuckDB Relational Export
    duckdb_path = pipeline.get("duckdb")
    if duckdb_path:
        _export_to_duckdb(world, onto, duckdb_path)

    onto.save(file=output_owl, format="rdfxml")
    world.save()

    # Release the exclusive SQLite lock so the DB can be reopened by other processes/tests
    if hasattr(world, "graph") and hasattr(world.graph, "db"):
        world.graph.db.close()

    print(f"\nDone. Saved to {output_owl} and quadstore {db_path}")


def _export_to_duckdb(world, onto, duckdb_path):
    """
    Generate a relational DuckDB mirror of the OWL individuals.
    Creates one table per class, with columns for each data property.
    This enables high-performance analytical queries and GIS spatial joins.
    """
    print(f"\n[export] Mirroring to DuckDB: {duckdb_path}")
    if os.path.exists(duckdb_path):
        os.remove(duckdb_path)

    duckdb_dir = os.path.dirname(duckdb_path)
    if duckdb_dir:
        os.makedirs(duckdb_dir, exist_ok=True)

    con = duckdb.connect(duckdb_path)
    try:
        for cls in onto.classes():
            instances = list(cls.instances())
            if not instances:
                continue

            data = []
            for inst in instances:
                row = {"_id": inst.name}
                # Capture all data properties
                for prop in inst.get_properties():
                    try:
                        val = prop[inst]
                        if isinstance(val, list):
                            val = val[0] if val else None
                        
                        # Only include data properties (skip object property URIs)
                        if hasattr(val, "iri"):
                            continue
                        
                        row[prop.python_name] = val
                    except Exception:
                        pass
                data.append(row)

            if data:
                df = pd.DataFrame(data)
                # Ensure _id is first column
                cols = ["_id"] + [c for c in df.columns if c != "_id"]
                df = df[cols]
                
                table_name = cls.name
                con.execute(f'CREATE TABLE "{table_name}" AS SELECT * FROM df')
                print(f"  -> Exported {len(df)} {table_name} individuals")

    finally:
        con.close()
