"""
Discovers and runs analysis functions from the analysis/ directory.

Each .py file in analysis/ that exports analyze(onto, **kwargs) -> dict
is treated as an analysis plugin.

Result dict schema:
    {
        "title": str,
        "sections": [
            {"type": "metrics", "items": [{"label": str, "value": any}, ...]},
            {"type": "table",   "title": str,  "data": pd.DataFrame},
            {"type": "chart",   "title": str,  "data": pd.DataFrame, "x": col, "y": col},
            {"type": "text",    "content": str},   # markdown
            {"type": "divider"},
        ]
    }
"""
import importlib.util
from pathlib import Path

ANALYSIS_DIR = Path("analysis")


def discover():
    """
    Return dict of {module_stem: module} for all analysis plugins.
    Modules that fail to load are skipped with a warning.
    """
    found = {}
    if not ANALYSIS_DIR.exists():
        return found

    for py_file in sorted(ANALYSIS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name = py_file.stem
        try:
            spec = importlib.util.spec_from_file_location(name, py_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "analyze"):
                found[name] = mod
        except Exception as exc:
            print(f"  [analysis] Warning: could not load '{py_file.name}': {exc}")

    return found


def run(module_name, onto, config=None):
    """Run a single named analysis module against the ontology."""
    mods = discover()
    if module_name not in mods:
        raise ValueError(f"Analysis module '{module_name}' not found in {ANALYSIS_DIR}/")
    return mods[module_name].analyze(onto, **(config or {}))
