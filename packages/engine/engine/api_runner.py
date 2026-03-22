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
from bs4 import BeautifulSoup

CACHE_DIR = Path(os.environ.get("RAIL_CACHE_DIR", "cache"))
API_CONFIG_DIR = Path(os.environ.get("RAIL_API_CONFIG_DIR", "configs/apis"))


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


# --- Source Handlers ---

def _handle_csv(api_name, spec, resolved_data):
    df = pd.read_csv(spec["path"])
    if "fields" in spec:
        df = _apply_fields(df, spec["fields"])
    return df


def _handle_excel(api_name, spec, resolved_data):
    df = pd.read_excel(spec["path"])
    if "fields" in spec:
        df = _apply_fields(df, spec["fields"])
    return df


def _handle_uploaded(api_name, spec, resolved_data):
    # 'path' must be resolved by the hydration worker from the storage_key
    path = spec.get("path")
    if not path:
        raise ValueError(f"Uploaded source '{api_name}' has no resolved path.")
    
    path = Path(path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix in (".xls", ".xlsx"):
        df = pd.read_excel(path)
    elif path.suffix == ".json":
        df = pd.read_json(path)
    else:
        raise ValueError(f"Unsupported file format for uploaded data: {path.suffix}")

    if "fields" in spec:
        df = _apply_fields(df, spec["fields"])
    return df


def _handle_scrape(api_name, spec, resolved_data):
    response = requests.get(spec["url"], timeout=30)
    response.raise_for_status()
    if spec.get("encoding"):
        response.encoding = spec["encoding"]

    df = _extract_table_from_html(response.text, spec.get("table_selector"))

    if "fields" in spec:
        df = _apply_fields(df, spec["fields"])
    return df


def _handle_api(api_name, spec, resolved_data):
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

    return df


SOURCE_HANDLERS = {
    "api": _handle_api,
    "csv": _handle_csv,
    "excel": _handle_excel,
    "uploaded": _handle_uploaded,
    "scrape": _handle_scrape,
}


def fetch_api(api_name, resolved_data=None):
    """
    Fetch and normalize data for a named API config.

    resolved_data: dict of {api_name: DataFrame} for foreach lookups.
    Returns a DataFrame with aliased columns.
    """
    spec = _load_spec(api_name)
    resolved_data = resolved_data or {}
    src_type = spec.get("type", "api")

    handler = SOURCE_HANDLERS.get(src_type)
    if not handler:
        raise ValueError(f"Unknown source type '{src_type}' for API '{api_name}'")

    df = handler(api_name, spec, resolved_data)

    if "fields" in spec and src_type == "api":
        # CSV/Excel/Uploaded handlers already applied fields if present
        df = _apply_fields(df, spec["fields"])

    if spec.get("drop_na"):
        df = df.dropna()

    return df


def _extract_table_from_html(html, table_selector=None):
    soup = BeautifulSoup(html, "html.parser")

    if table_selector:
        table = soup.select_one(table_selector)
        if table is None:
            raise ValueError(f"No table found for selector '{table_selector}'")
        return _table_to_dataframe(table)

    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No HTML tables found on page")

    table = max(tables, key=lambda current: len(current.find_all("tr")))
    return _table_to_dataframe(table)


def _table_to_dataframe(table):
    rows = []
    headers = []

    for tr in table.find_all("tr"):
        if not headers:
            header_cells = tr.find_all("th")
            if header_cells:
                headers = [_cell_text(cell) for cell in header_cells]
                continue

        cells = tr.find_all(["td", "th"])
        if cells:
            rows.append([_cell_text(cell) for cell in cells])

    if not rows and headers:
        return pd.DataFrame(columns=headers)
    if not rows:
        raise ValueError("Selected table is empty")

    width = max(len(row) for row in rows)
    if not headers:
        headers = [f"column_{i + 1}" for i in range(width)]
    elif len(headers) < width:
        headers.extend(f"column_{i + 1}" for i in range(len(headers), width))

    normalized = [row + [""] * (len(headers) - len(row)) for row in rows]
    return pd.DataFrame(normalized, columns=headers)


def _cell_text(cell):
    return " ".join(cell.get_text(" ", strip=True).split())
