import timeit
import pandas as pd
import numpy as np

def _apply_fields_orig(df, fields_spec):
    result = {}
    for field in fields_spec:
        if "computed" in field: continue
        source = field["source"]
        alias = field.get("alias", source)
        result[alias] = df[source]

    partial = pd.DataFrame(result)
    for field in fields_spec:
        if "computed" not in field: continue
        alias = field["alias"]
        template = field["computed"]
        result[alias] = partial.apply(
            lambda row, t=template: t.format(**row.to_dict()), axis=1
        )
    return pd.DataFrame(result)

def _apply_fields_new(df, fields_spec):
    result = {}
    for field in fields_spec:
        if "computed" in field: continue
        source = field["source"]
        alias = field.get("alias", source)
        result[alias] = df[source]

    partial = pd.DataFrame(result)
    computed_fields = [f for f in fields_spec if "computed" in f]
    if computed_fields:
        records = partial.to_dict("records")
        for field in computed_fields:
            alias = field["alias"]
            template = field["computed"]
            # Use a list comprehension over the pre-converted records
            result[alias] = [template.format(**row) for row in records]

    return pd.DataFrame(result)

def benchmark():
    num_rows = 1000
    num_cols = 20
    data = {f"col_{i}": [f"val_{i}_{j}" for j in range(num_rows)] for i in range(num_cols)}
    df = pd.DataFrame(data)

    fields_spec = [{"source": f"col_{i}", "alias": f"a_{i}"} for i in range(num_cols)]
    fields_spec += [{"alias": f"comp_{i}", "computed": "Value is {a_0} and {a_1}"} for i in range(5)]

    t_orig = timeit.timeit(lambda: _apply_fields_orig(df, fields_spec), number=10)
    t_new = timeit.timeit(lambda: _apply_fields_new(df, fields_spec), number=10)

    print(f"Apply fields (10 runs, {num_rows} rows, 5 computed fields):")
    print(f"  Original: {t_orig:.4f}s")
    print(f"  New:      {t_new:.4f}s")
    print(f"  Speedup:  {t_orig/t_new:.2f}x")

    # Benchmark iterrows vs to_dict('records')
    def iterrows_loop():
        for _, row in df.iterrows():
            _ = row.to_dict()

    def records_loop():
        for row in df.to_dict('records'):
            pass

    t_iterrows = timeit.timeit(iterrows_loop, number=10)
    t_records = timeit.timeit(records_loop, number=10)
    print(f"\nIteration (10 runs, {num_rows} rows):")
    print(f"  iterrows():         {t_iterrows:.4f}s")
    print(f"  to_dict('records'): {t_records:.4f}s")
    print(f"  Speedup:            {t_iterrows/t_records:.2f}x")

if __name__ == "__main__":
    benchmark()
