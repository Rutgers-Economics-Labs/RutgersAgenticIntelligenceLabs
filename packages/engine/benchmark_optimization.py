import re
import timeit
import pandas as pd
import numpy as np

# --- Current Implementation in pipeline_runner.py ---
_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_\-.]")

def _sanitize(value):
    return _SAFE_CHARS_RE.sub("_", str(value))

_PLACEHOLDER_RE = re.compile(r"\{([^}]+)\}")

def _resolve_new(template, row, sanitize=False):
    def replacer(match):
        key = match.group(1)
        if key in row:
            val = row[key]
            return _sanitize(val) if (sanitize and isinstance(val, str)) else str(val)
        return match.group(0)
    return _PLACEHOLDER_RE.sub(replacer, template)

# --- Original Implementations (to compare) ---
def _sanitize_orig(value):
    return re.sub(r"[^A-Za-z0-9_\-.]", "_", str(value))

def _resolve_orig(template, row, sanitize=False):
    result = template
    for key, val in row.items():
        str_val = _sanitize_orig(val) if (sanitize and isinstance(val, str)) else str(val)
        result = result.replace("{" + key + "}", str_val)
    return result

# --- Benchmark Setup ---
num_cols = 100
num_rows = 1000
data = {f"col_{i}": [f"value_{i}_{j}" for j in range(num_rows)] for i in range(num_cols)}
df = pd.DataFrame(data)
row_dict = df.iloc[0].to_dict()
template = "Template with {col_0}, {col_50}, and {col_99}."

# --- Correctness Test ---
def test_correctness():
    row = {"full-name": "John Doe", "id.value": "123", "normal": "test"}
    tmpl = "{full-name} / {id.value} / {normal}"

    res_orig = _resolve_orig(tmpl, row)
    res_new = _resolve_new(tmpl, row)

    print(f"Template: {tmpl}")
    print(f"Original: {res_orig}")
    print(f"New:      {res_new}")

    assert res_orig == res_new == "John Doe / 123 / test"
    print("Correctness test passed!\n")

# --- Benchmarking ---
def benchmark():
    test_correctness()
    print(f"Benchmarking with {num_cols} columns and {num_rows} rows.\n")

    # 1. _sanitize
    t_orig = timeit.timeit(lambda: _sanitize_orig("Some Value With Spaces!"), number=100000)
    t_new = timeit.timeit(lambda: _sanitize("Some Value With Spaces!"), number=100000)
    print(f"_sanitize (100k calls):")
    print(f"  Original:  {t_orig:.4f}s")
    print(f"  New:       {t_new:.4f}s")
    print(f"  Speedup:   {t_orig/t_new:.2f}x\n")

    # 2. _resolve
    t_orig = timeit.timeit(lambda: _resolve_orig(template, row_dict, sanitize=True), number=10000)
    t_new = timeit.timeit(lambda: _resolve_new(template, row_dict, sanitize=True), number=10000)
    print(f"_resolve (10k calls, {num_cols} columns):")
    print(f"  Original:  {t_orig:.4f}s")
    print(f"  New:       {t_new:.4f}s")
    print(f"  Speedup:   {t_orig/t_new:.2f}x\n")

    # 3. DataFrame iteration
    def iterrows_loop():
        for _, row in df.iterrows():
            _ = row.to_dict()

    def records_loop():
        for row in df.to_dict('records'):
            pass

    t_orig = timeit.timeit(iterrows_loop, number=10)
    t_new = timeit.timeit(records_loop, number=10)
    print(f"DataFrame iteration (10 runs of {num_rows} rows):")
    print(f"  iterrows(): {t_orig:.4f}s")
    print(f"  to_dict('records'): {t_new:.4f}s")
    print(f"  Speedup:    {t_orig/t_new:.2f}x\n")

if __name__ == "__main__":
    benchmark()
