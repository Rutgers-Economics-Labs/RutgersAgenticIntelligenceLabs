## 2025-05-14 - [Hydration Performance Optimization]
**Learning:** `df.iterrows()` is a significant bottleneck in hydration loops because it boxes rows into Series objects. `_resolve` was O(columns) due to repeated `.replace()` calls on the full dictionary.
**Action:** Use `df.to_dict('records')` for faster iteration and `re.sub` for template resolution to achieve O(template_placeholders) instead of O(columns). Pre-compile regexes for high-frequency string operations.

## 2026-04-05 - [api_runner Performance Optimization]
**Learning:** `pd.DataFrame.apply(axis=1)` and `df.iterrows()` are major bottlenecks for row-wise processing in this engine. Converting to `df.to_dict('records')` *once* and using list comprehensions for field formatting is significantly faster.
**Action:** Always prefer `to_dict('records')` over `iterrows()` or `apply(axis=1)` for row-wise operations. When processing multiple computed fields, generate the record list once to avoid O(fields * rows) conversion overhead.
