import argparse
import csv
import glob
import json
import os
import re
import sqlite3
from datetime import datetime
from urllib import parse, request

from owlready2 import *

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required for config mode. Install with: pip install pyyaml"
    ) from exc


def _slug(value):
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _expand_env(obj):
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    if isinstance(obj, str):
        pattern = r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}"

        def repl(match):
            env_name = match.group(1)
            if env_name not in os.environ:
                raise ValueError(f"Missing required environment variable: {env_name}")
            return os.environ[env_name]

        return re.sub(pattern, repl, obj)
    return obj


def _load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("Config root must be a YAML object.")
    return _expand_env(cfg)


def _validate_config(cfg):
    errors = []
    for key in ["sources", "mapping_sets", "output"]:
        if key not in cfg:
            errors.append(f"Missing top-level key: {key}")

    if "sources" in cfg and not isinstance(cfg["sources"], list):
        errors.append("'sources' must be a list")

    allowed_source_types = {"csv", "excel", "api", "sql"}
    seen_ids = set()
    for i, source in enumerate(cfg.get("sources", [])):
        if not isinstance(source, dict):
            errors.append(f"sources[{i}] must be an object")
            continue

        source_id = source.get("id")
        source_type = source.get("type")
        map_set = source.get("map_set")

        if not source_id:
            errors.append(f"sources[{i}] is missing required key: id")
        elif source_id in seen_ids:
            errors.append(f"Duplicate source id: {source_id}")
        else:
            seen_ids.add(source_id)

        if source_type not in allowed_source_types:
            errors.append(
                f"sources[{i}] has invalid type '{source_type}', expected one of {sorted(allowed_source_types)}"
            )
        if not map_set:
            errors.append(f"sources[{i}] is missing required key: map_set")
        if "extract" not in source:
            errors.append(f"sources[{i}] is missing required key: extract")
        if "normalize" not in source:
            errors.append(f"sources[{i}] is missing required key: normalize")

    for i, source in enumerate(cfg.get("sources", [])):
        if not isinstance(source, dict):
            continue
        map_set = source.get("map_set")
        if map_set and map_set not in cfg.get("mapping_sets", {}):
            errors.append(
                f"sources[{i}] references unknown map_set '{map_set}'"
            )

    for map_name, mapping in cfg.get("mapping_sets", {}).items():
        if not isinstance(mapping, dict):
            errors.append(f"mapping_sets.{map_name} must be an object")
            continue
        if "target_class" not in mapping:
            errors.append(f"mapping_sets.{map_name} missing target_class")
        if "iri_template" not in mapping:
            errors.append(f"mapping_sets.{map_name} missing iri_template")
        if "predicates" not in mapping:
            errors.append(f"mapping_sets.{map_name} missing predicates")

    output = cfg.get("output", {})
    for key in ["ontology_input", "ontology_output", "format"]:
        if key not in output:
            errors.append(f"output missing required key: {key}")

    if errors:
        raise ValueError("Config validation failed:\n- " + "\n- ".join(errors))


def _extract_path(data, expr):
    expr = expr.strip()
    if not expr:
        return None

    if expr.startswith("'") and expr.endswith("'"):
        return expr[1:-1]

    if expr.startswith('"') and expr.endswith('"'):
        return expr[1:-1]

    current = data
    parts = expr.split(".")
    for part in parts:
        key = part
        index = None
        list_mode = False

        if part.endswith("[]"):
            list_mode = True
            key = part[:-2]
        elif "[" in part and part.endswith("]"):
            key, idx_text = part[:-1].split("[", 1)
            if idx_text.isdigit():
                index = int(idx_text)

        if isinstance(current, list):
            values = []
            for item in current:
                if isinstance(item, dict) and key in item:
                    values.append(item[key])
            current = values
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None

        if index is not None:
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]

        if list_mode:
            if current is None:
                current = []
            elif not isinstance(current, list):
                current = [current]

    return current


def _extract_api_rows(extract_cfg, source):
    base_url = extract_cfg.get("base_url", "").rstrip("/")
    endpoint = extract_cfg.get("endpoint", "")
    method = extract_cfg.get("method", "GET").upper()
    params = extract_cfg.get("params", {})
    body = extract_cfg.get("body")
    response_path = extract_cfg.get("response_path")

    url = f"{base_url}{endpoint}"
    if params and method == "GET":
        query = parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    payload = None
    headers = {}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    conn_name = source.get("connection_ref")
    if conn_name:
        headers.update(source.get("resolved_connection_headers", {}))

    req = request.Request(url=url, method=method, data=payload, headers=headers)
    with request.urlopen(req, timeout=30) as resp:
        doc = json.loads(resp.read().decode("utf-8"))

    if not response_path:
        if isinstance(doc, list):
            return doc
        return [doc]

    rows = _extract_path(doc, response_path)
    if rows is None:
        return []
    if isinstance(rows, list):
        return rows
    return [rows]


def _extract_csv_rows(extract_cfg):
    path_pattern = extract_cfg.get("path")
    if not path_pattern:
        raise ValueError("CSV extract.path is required")

    delimiter = extract_cfg.get("delimiter", ",")
    encoding = extract_cfg.get("encoding", "utf-8")
    rows = []

    for file_path in glob.glob(path_pattern):
        with open(file_path, "r", encoding=encoding, newline="") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            rows.extend(reader)

    return rows


def _extract_excel_rows(extract_cfg):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError(
            "Excel extraction requires openpyxl. Install with: pip install openpyxl"
        ) from exc

    path = extract_cfg.get("path")
    if not path:
        raise ValueError("Excel extract.path is required")

    sheet_name = extract_cfg.get("sheet")
    header_row = int(extract_cfg.get("header_row", 1))

    wb = load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    data = list(ws.values)
    headers = [str(x) if x is not None else "" for x in data[header_row - 1]]
    rows = []
    for row in data[header_row:]:
        rows.append({headers[i]: row[i] for i in range(min(len(headers), len(row)))})
    return rows


def _extract_sql_rows(source, extract_cfg, connections):
    conn_ref = source.get("connection_ref")
    db_path = extract_cfg.get("database_path")
    if conn_ref:
        conn_def = connections.get(conn_ref, {})
        if conn_def.get("kind") == "sqlite":
            db_path = conn_def.get("path")

    if not db_path:
        raise ValueError(
            "SQL extraction currently supports sqlite via extract.database_path or a sqlite connection_ref"
        )

    query = extract_cfg.get("query")
    if not query:
        raise ValueError("SQL extract.query is required")

    params = extract_cfg.get("params", {})
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        con.close()


def _apply_cast(value, cast_expr):
    if value is None:
        return None
    if cast_expr == "float":
        return float(value)
    if cast_expr == "int":
        return int(value)
    if cast_expr == "str":
        return str(value)
    if cast_expr.startswith("date:"):
        fmt = cast_expr.split(":", 1)[1]
        dt = datetime.strptime(str(value), fmt)
        return dt.strftime(fmt)
    return value


def _normalize_rows(source_id, rows, normalize_cfg):
    select_cfg = normalize_cfg.get("select", {})
    casts_cfg = normalize_cfg.get("casts", {})
    normalized = []

    for row in rows:
        out = {"source_id": source_id}
        for out_field, selector in select_cfg.items():
            out[out_field] = _extract_path(row, str(selector))

        for field, cast_expr in casts_cfg.items():
            out[field] = _apply_cast(out.get(field), str(cast_expr))

        normalized.append(out)

    return normalized


def _resolve_source_headers(source, connections):
    conn_ref = source.get("connection_ref")
    if not conn_ref:
        return {}

    conn = connections.get(conn_ref, {})
    if conn.get("kind") == "api_key":
        return {conn.get("header", "Authorization"): conn.get("value", "")}
    return {}


def _get_or_create_county(onto, value):
    name = _slug(value)
    county = onto.County(name)
    if not county.geoID:
        county.geoID = [name]
    return county


def _get_or_create_timeperiod(onto, value):
    name = f"time_{_slug(value)}"
    period = onto.TimePeriod(name)
    period.timeID = [str(value)]
    return period


def _get_or_create_source(onto, value):
    name = _slug(value)
    return onto.Source(name)


def _format_iri(template, record):
    return _slug(template.format(**record))


def _validate_required(record, required_fields):
    missing = []
    for key in required_fields:
        if record.get(key) in [None, ""]:
            missing.append(key)
    return missing


def _hydrate_from_config(cfg):
    output = cfg["output"]
    onto = get_ontology(f"file://{output['ontology_input']}").load()

    run_cfg = cfg.get("run", {})
    fail_policy = run_cfg.get("fail_policy", "continue")
    quality_cfg = cfg.get("quality", {})
    on_missing = quality_cfg.get("on_missing_required", "skip_record")
    on_cast_error = quality_cfg.get("on_cast_error", "skip_record")
    max_errors_per_source = int(quality_cfg.get("max_errors_per_source", 100))

    total_read = 0
    total_written = 0
    total_skipped = 0

    connections = cfg.get("connections", {})

    with onto:
        for source in cfg.get("sources", []):
            if not source.get("enabled", True):
                continue

            source_id = source["id"]
            source_type = source["type"]
            source["resolved_connection_headers"] = _resolve_source_headers(
                source, connections
            )

            source_errors = 0
            try:
                if source_type == "csv":
                    raw_rows = _extract_csv_rows(source["extract"])
                elif source_type == "excel":
                    raw_rows = _extract_excel_rows(source["extract"])
                elif source_type == "api":
                    raw_rows = _extract_api_rows(source["extract"], source)
                elif source_type == "sql":
                    raw_rows = _extract_sql_rows(source, source["extract"], connections)
                else:
                    raise ValueError(f"Unsupported source type: {source_type}")
            except Exception as exc:
                if fail_policy == "fail_fast":
                    raise
                print(f"[WARN] Source '{source_id}' failed extraction: {exc}")
                continue

            total_read += len(raw_rows)

            try:
                records = _normalize_rows(source_id, raw_rows, source["normalize"])
            except Exception as exc:
                if fail_policy == "fail_fast":
                    raise
                print(f"[WARN] Source '{source_id}' failed normalization: {exc}")
                continue

            mapping = cfg["mapping_sets"][source["map_set"]]
            target_class_name = mapping["target_class"]
            iri_template = mapping["iri_template"]
            predicates = mapping["predicates"]
            required = mapping.get("required", [])

            target_cls = getattr(onto, target_class_name, None)
            if target_cls is None:
                msg = f"Target class '{target_class_name}' not found in ontology"
                if fail_policy == "fail_fast":
                    raise ValueError(msg)
                print(f"[WARN] {msg}")
                continue

            for record in records:
                try:
                    missing = _validate_required(record, required)
                    if missing:
                        raise ValueError(f"Missing required fields: {missing}")

                    measure_name = _format_iri(iri_template, record)
                    measure = target_cls(measure_name)

                    for pred_name, field_name in predicates.items():
                        pred = getattr(onto, pred_name, None)
                        if pred is None:
                            raise ValueError(f"Unknown predicate: {pred_name}")

                        value = record.get(field_name)
                        if value is None:
                            continue

                        if pred_name == "measuredFor":
                            pred[measure] = [_get_or_create_county(onto, value)]
                        elif pred_name == "measuredAt":
                            pred[measure] = [_get_or_create_timeperiod(onto, value)]
                        elif pred_name == "fromSource":
                            pred[measure] = [_get_or_create_source(onto, value)]
                        else:
                            pred[measure] = [value]

                    total_written += 1
                except Exception as exc:
                    source_errors += 1
                    total_skipped += 1
                    policy = on_missing if "Missing required" in str(exc) else on_cast_error
                    if policy == "fail" or fail_policy == "fail_fast":
                        raise
                    if source_errors <= max_errors_per_source:
                        print(f"[WARN] Skipping record in '{source_id}': {exc}")

    onto.save(file=output["ontology_output"], format=output["format"])
    print("Hydration complete")
    print(f"records_read={total_read}")
    print(f"records_written={total_written}")
    print(f"records_skipped={total_skipped}")
    print(f"output_file={output['ontology_output']}")


def _run_legacy_demo():
    onto = get_ontology("file://rail_nj_skeleton.owl").load()
    print("Classes in ontology: ")
    for cls in onto.classes():
        print(cls)
    print("\n")
    print("Object properties: ")
    for prop in onto.object_properties():
        print(prop)

    with onto:
        nj_state = onto.State("new_jersey")
        nj_state.geoID = ["34"]
        nj_county = onto.County("essex_county")
        nj_county.geoID = ["34013"]
        nj_county.locatedIn = [nj_state]

        year_2024 = onto.TimePeriod("year_2024")
        year_2024.timeID = ["2024"]

        laus_source = onto.LAUS("laus_source")

        unem_rate = onto.LaborIndicator("essex_unemployment_2024")
        unem_rate.hasValue = [4.2]
        unem_rate.hasUnit = ["Percent"]
        unem_rate.hasTag = ["labor.unemployment.rate"]
        unem_rate.measuredFor = [nj_county]
        unem_rate.fromSource = [laus_source]
        unem_rate.dataVintage = ["2024-01-01"]
        unem_rate.measuredAt = [year_2024]

        electricity = onto.EnergyIndicator("essex_electricity_2024")
        electricity.hasValue = [5000000]
        electricity.hasUnit = ["kWh"]
        electricity.measuredFor = [nj_county]
        electricity.hasTag = ["energy.electricity.consumption_kwh"]
        electricity.fromSource = [laus_source]
        electricity.dataVintage = ["2024-01-01"]
        electricity.measuredAt = [year_2024]

    print("\nLabor indicators:")
    for measure in onto.LaborIndicator.instances():
        for geo in measure.measuredFor:
            print(
                f"{geo.name}: {measure.hasValue[0]} {measure.hasUnit[0]} "
                f"(tag={measure.hasTag[0]}, year={measure.measuredAt[0].timeID[0]})"
            )

    print("\nAll measures:")
    for measure in onto.Measure.instances():
        for geo in measure.measuredFor:
            print(
                f"{geo.name}: {measure.name} = {measure.hasValue[0]} {measure.hasUnit[0]} "
                f"[tag={measure.hasTag[0]}, year={measure.measuredAt[0].timeID[0]}]"
            )

    onto.save(file="rail_nj_populated.owl", format="rdfxml")
    print("\nPopulated ontology saved!")


def main():
    parser = argparse.ArgumentParser(description="Hydrate ontology from configured data sources")
    parser.add_argument("--config", help="Path to YAML hydration config")
    args = parser.parse_args()

    if not args.config:
        print("No --config provided. Running legacy demo hydration.")
        _run_legacy_demo()
        return

    cfg = _load_config(args.config)
    _validate_config(cfg)
    _hydrate_from_config(cfg)


if __name__ == "__main__":
    main()