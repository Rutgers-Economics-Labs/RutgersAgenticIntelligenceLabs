import timeit
import pandas as pd
import numpy as np

# --- Current Implementation in api_runner.py (as of start) ---

def _apply_fields_orig(df, fields_spec):
    result = {}
    for field in fields_spec:
        if "computed" in field:
            continue
        source = field["source"]
        alias = field.get("alias", source)
        cast = field.get("cast")
        if source not in df.columns:
            continue
        col = df[source]
        if cast in ("int", "float"):
            col = pd.to_numeric(col, errors="coerce")
            if cast == "int":
                col = col.round().astype("Int64")
        elif cast == "str":
            col = col.astype(str)
        result[alias] = col

    partial = pd.DataFrame(result)

    for field in fields_spec:
        if "computed" not in field:
            continue
        alias = field["alias"]
        template = field["computed"]
        result[alias] = partial.apply(
            lambda row, t=template: t.format(**row.to_dict()), axis=1
        )
    return pd.DataFrame(result)

def _handle_api_loop_orig(df):
    results = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        # Simulate some work like template formatting
        _ = "{col_0} - {col_1}".format(**row_dict)
        results.append(row_dict)
    return results

# --- Optimized Implementation (Candidate) ---

def _apply_fields_new(df, fields_spec):
    result_cols = {}
    for field in fields_spec:
        if "computed" in field:
            continue
        source = field["source"]
        alias = field.get("alias", source)
        cast = field.get("cast")
        if source not in df.columns:
            continue
        col = df[source]
        if cast in ("int", "float"):
            col = pd.to_numeric(col, errors="coerce")
            if cast == "int":
                col = col.round().astype("Int64")
        elif cast == "str":
            col = col.astype(str)
        result_cols[alias] = col

    partial = pd.DataFrame(result_cols)

    computed_fields = [f for f in fields_spec if "computed" in f]
    if computed_fields:
        records = partial.to_dict('records')
        for field in computed_fields:
            alias = field["alias"]
            template = field["computed"]
            result_cols[alias] = [template.format(**r) for r in records]

    return pd.DataFrame(result_cols)

def _handle_api_loop_new(df):
    results = []
    for row_dict in df.to_dict('records'):
        # Simulate some work like template formatting
        _ = "{col_0} - {col_1}".format(**row_dict)
        results.append(row_dict)
    return results

# --- Benchmark Setup ---
num_rows = 5000
data = {f"col_{i}": [f"val_{i}_{j}" for j in range(num_rows)] for i in range(10)}
df = pd.DataFrame(data)

fields_spec = [
    {"source": "col_0", "alias": "id"},
    {"source": "col_1", "alias": "name"},
    {"alias": "display", "computed": "ID: {id}, Name: {name}"},
    {"alias": "upper_name", "computed": "{name}"} # Just to have another computed field
]

def benchmark():
    print(f"Benchmarking with {num_rows} rows.\n")

    # 1. _apply_fields
    t_orig = timeit.timeit(lambda: _apply_fields_orig(df, fields_spec), number=10)
    t_new = timeit.timeit(lambda: _apply_fields_new(df, fields_spec), number=10)
    print(f"_apply_fields (10 runs):")
    print(f"  Original:  {t_orig:.4f}s")
    print(f"  New:       {t_new:.4f}s")
    print(f"  Speedup:   {t_orig/t_new:.2f}x\n")

    # 2. _handle_api loop
    t_orig = timeit.timeit(lambda: _handle_api_loop_orig(df), number=10)
    t_new = timeit.timeit(lambda: _handle_api_loop_new(df), number=10)
    print(f"_handle_api loop (10 runs):")
    print(f"  Original:  {t_orig:.4f}s")
    print(f"  New:       {t_new:.4f}s")
    print(f"  Speedup:   {t_orig/t_new:.2f}x\n")

if __name__ == "__main__":
    benchmark()
