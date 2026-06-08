import pandas as pd

from engine.config_loader import load_yaml
from engine.ontology_utils import (
    load_ontology,
    get_or_create_county,
    get_or_create_time_period,
    get_or_create_source,
    create_measure,
)

def is_missing(val) -> bool:
    return pd.isna(val)

def validate_mapping_against_registry(mapping: dict, registry: dict):
    ontology_tag = mapping["ontology_tag"]
    if ontology_tag not in registry["measures"]:
        raise ValueError(f"Unknown ontology tag in config: {ontology_tag}")

    expected_class = registry["measures"][ontology_tag]["class"]
    if mapping["measure_class"] != expected_class:
        raise ValueError(
            f"Config mismatch for {ontology_tag}: "
            f"measure_class={mapping['measure_class']} but registry expects {expected_class}"
        )

def hydrate_source(source_config_path: str, output_owl_path: str):
    cfg = load_yaml(source_config_path)
    registry = load_yaml("configs/ontology_registry.yaml")
    onto = load_ontology("ontology/rail_nj_skeleton.owl")

    source_info = cfg["source"]
    geo_info = cfg["geography"]
    time_info = cfg["time"]
    field_mappings = cfg["field_mappings"]
    metadata = cfg.get("metadata", {})

    if source_info["source_type"] != "csv":
        raise NotImplementedError("This v1 currently supports CSV only.")

    df = pd.read_csv(source_info["path"])

    with onto:
        source_obj = get_or_create_source(
            onto,
            source_info["source_id"],
            source_info["owl_class"]
        )

        for _, row in df.iterrows():
            county = get_or_create_county(
                onto,
                row[geo_info["id_column"]],
                row[geo_info["name_column"]]
            )

            time_period = get_or_create_time_period(
                onto,
                time_info["frequency"],
                row[time_info["column"]]
            )

            for raw_col, mapping in field_mappings.items():
                validate_mapping_against_registry(mapping, registry)

                value = row[raw_col]
                if is_missing(value):
                    continue

                ontology_tag = mapping["ontology_tag"]
                measure_class = mapping["measure_class"]
                units = mapping["units"]
                price_basis = mapping.get("price_basis")

                measure_name = (
                    f"{county.name}_{ontology_tag.replace('.', '_')}_{row[time_info['column']]}"
                )

                # avoid duplicate individuals if rerun
                measure = onto[measure_name]
                if measure is None:
                    measure = create_measure(onto, measure_class, measure_name)

                measure.hasValue = [float(value)]
                measure.hasUnit = [units]
                measure.hasTag = [ontology_tag]
                measure.measuredFor = [county]
                measure.fromSource = [source_obj]
                measure.measuredAt = [time_period]
                measure.dataVintage = [metadata.get("data_vintage", "unknown")]
                measure.rawField = [raw_col]
                measure.suppressed = [False]

                if price_basis is not None:
                    measure.priceBasis = [price_basis]

    onto.save(file=output_owl_path, format="rdfxml")
    print(f"Hydrated ontology saved to {output_owl_path}")