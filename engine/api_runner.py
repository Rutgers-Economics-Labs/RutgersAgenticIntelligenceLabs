"""
Generic API/CSV runner that reads configs/apis/*.yaml and returns DataFrames.
No domain knowledge — all field names, endpoints, and transforms come from YAML.
"""
import json
import os
import re
from pathlib import Path

import pandas as pd
import requests
import yaml

CACHE_DIR = Path("cache")
API_CONFIG_DIR = Path("configs/apis")


def _load_spec(api_name):
    path = API_CONFIG_DIR / f"{api_name}.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f)
    return _resolve_env_vars(raw)


def _resolve_env_vars(obj):
    """Recursively replace ${VAR_NAME} in string values with environment variables."""
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    if isinstance(obj, str):
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    return obj


def _cache_path(key):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _http_fetch(spec, extra_params=None):
    """Fetch one API call, with caching keyed on name + extra_params."""
    params = dict(spec.get("params", {}))
    if extra_params:
        params.update(extra_params)

    # Build a stable cache key
    cache_key = spec["name"]
    if extra_params:
        suffix = "_".join(f"{k}_{v}" for k, v in sorted(extra_params.items()))
        cache_key = f"{cache_key}_{suffix}"
    cache_key = cache_key.replace(":", "_").replace(" ", "_").replace("*", "all")

    cp = _cache_path(cache_key)
    if cp.exists() and spec.get("cache", True):
        print(f"  [cache] {cache_key}")
        with open(cp) as f:
            return json.load(f)

    print(f"  [fetch] {spec['url']} params={params}")
    resp = requests.get(spec["url"], params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    with open(cp, "w") as f:
        json.dump(data, f)

    return data


def _to_dataframe(raw, response_format, response_path=None):
    """Normalize raw API response to a DataFrame."""
    if response_path:
        raw = raw[response_path]
    if response_format == "census_array":
        return pd.DataFrame(raw[1:], columns=raw[0])
    if response_format == "json":
        if isinstance(raw, list):
            return pd.DataFrame(raw)
        return pd.DataFrame([raw])
    return pd.DataFrame(raw)


def _apply_fields(df, fields_spec):
    """
    Rename + cast + compute columns according to the fields spec.
    Two passes: (1) source→alias renames/casts, (2) computed fields using aliases.
    """
    result = {}

    # Pass 1: source fields
    for field in fields_spec:
        if "computed" in field:
            continue
        source = field["source"]
        alias = field.get("alias", source)
        cast = field.get("cast")
        if source not in df.columns:
            print(f"  Warning: column '{source}' not found, skipping")
            continue
        col = df[source]
        if cast in ("int", "float"):
            # pd.to_numeric coerces "." and other non-numeric FRED values to NaN
            col = pd.to_numeric(col, errors="coerce")
            if cast == "int":
                col = col.round().astype("Int64")
        elif cast == "str":
            col = col.astype(str)
        result[alias] = col

    partial = pd.DataFrame(result)

    # Pass 2: computed fields (can reference aliases from pass 1)
    for field in fields_spec:
        if "computed" not in field:
            continue
        alias = field["alias"]
        template = field["computed"]
        result[alias] = partial.apply(
            lambda row, t=template: t.format(**row.to_dict()), axis=1
        )

    return pd.DataFrame(result)


def fetch_api(api_name, resolved_data=None):
    """
    Fetch and normalize data for a named API config.

    resolved_data: dict of {api_name: DataFrame} for foreach lookups.
    Returns a DataFrame with aliased columns.
    """
    spec = _load_spec(api_name)
    resolved_data = resolved_data or {}
    src_type = spec.get("type", "api")

    # --- CSV / Excel sources ---
    if src_type == "csv":
        df = pd.read_csv(spec["path"])
        if "fields" in spec:
            df = _apply_fields(df, spec["fields"])
        return df

    if src_type == "excel":
        df = pd.read_excel(spec["path"])
        if "fields" in spec:
            df = _apply_fields(df, spec["fields"])
        return df

    # --- API sources ---
    foreach = spec.get("foreach")
    response_format = spec.get("response_format", "json")
    response_path = spec.get("response_path")

    if foreach:
        source_name = foreach["source"]
        field = foreach["field"]
        filter_expr = foreach.get("filter")
        inject_param = foreach.get("inject_param")
        inject_template = foreach.get("inject_template", "{" + field + "}")

        if source_name not in resolved_data:
            raise ValueError(
                f"foreach source '{source_name}' not yet resolved. "
                "Check pipeline step order."
            )

        parent_df = resolved_data[source_name].copy()
        if filter_expr:
            parent_df = parent_df.query(filter_expr)

        inject_fields = foreach.get("inject_fields", [])

        frames = []
        for _, row in parent_df.iterrows():
            row_dict = row.to_dict()
            extra = {}
            if inject_param:
                extra[inject_param] = inject_template.format(**row_dict)
            try:
                raw = _http_fetch(spec, extra_params=extra)
            except Exception as e:
                label = inject_template.format(**row_dict) if inject_param else str(row_dict.get(field, "?"))
                print(f"  [skip] {label}: {e}")
                continue
            chunk = _to_dataframe(raw, response_format, response_path)
            for f in inject_fields:
                if f in row_dict:
                    chunk[f] = str(row_dict[f])
            frames.append(chunk)

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
    else:
        raw = _http_fetch(spec)
        df = _to_dataframe(raw, response_format, response_path)

    if "fields" in spec:
        df = _apply_fields(df, spec["fields"])

    if spec.get("drop_na"):
        df = df.dropna()

    return df
