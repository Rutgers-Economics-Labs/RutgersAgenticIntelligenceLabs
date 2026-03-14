"""
Loads and runs transform functions.

Transform functions live in the transforms/ directory (or anywhere on sys.path).
Reference them in pipeline YAML as "module_name::function_name".

Two types:
  DataFrame transform  — receives a DataFrame, must return a DataFrame
  Ontology transform   — receives the onto object, modifies in-place, returns None
"""
import importlib.util
import os
from pathlib import Path

TRANSFORM_DIR = Path(os.environ.get("RAIL_TRANSFORM_DIR", "transforms"))


def _load_fn(spec_str):
    """
    Load a function from 'module_name::function_name' notation.
    Searches transforms/ first, then falls back to standard import.
    """
    if "::" in spec_str:
        module_name, func_name = spec_str.split("::", 1)
    else:
        module_name, func_name = spec_str, "transform"

    path = TRANSFORM_DIR / f"{module_name}.py"
    if path.exists():
        spec = importlib.util.spec_from_file_location(module_name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(module_name)

    if not hasattr(mod, func_name):
        raise AttributeError(f"Function '{func_name}' not found in '{module_name}'")

    return getattr(mod, func_name)


def run_dataframe_transform(spec_str, df, config=None):
    """
    Run a DataFrame transform. The function receives (df, **config) and must
    return the transformed DataFrame.
    """
    fn = _load_fn(spec_str)
    result = fn(df, **(config or {}))
    if result is None:
        raise ValueError(
            f"Transform '{spec_str}' returned None — it must return a DataFrame."
        )
    return result


def run_ontology_transform(spec_str, onto, config=None):
    """
    Run an ontology transform. The function receives (onto, **config) and
    modifies the ontology in-place.
    """
    fn = _load_fn(spec_str)
    fn(onto, **(config or {}))
