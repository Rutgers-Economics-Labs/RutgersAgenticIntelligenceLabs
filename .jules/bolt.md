## 2025-05-14 - [Hydration Performance Optimization]
**Learning:** `df.iterrows()` is a significant bottleneck in hydration loops because it boxes rows into Series objects. `_resolve` was O(columns) due to repeated `.replace()` calls on the full dictionary.
**Action:** Use `df.to_dict('records')` for faster iteration and `re.sub` for template resolution to achieve O(template_placeholders) instead of O(columns). Pre-compile regexes for high-frequency string operations.

## 2025-05-15 - [API Runner Performance Optimization]
**Learning:** `pd.DataFrame.apply(axis=1)` for string formatting in `_apply_fields` and `df.iterrows()` in `_handle_api` were confirmed to be major bottlenecks. String formatting via list comprehension on `to_dict('records')` is ~30x faster than `.apply(axis=1)`.
**Action:** Always prefer `df.to_dict('records')` over `iterrows()` or `apply(axis=1)` for row-wise transformations or logic in the Python backend.
