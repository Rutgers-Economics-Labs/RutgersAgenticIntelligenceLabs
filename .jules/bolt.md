## 2025-05-14 - [Hydration Performance Optimization]
**Learning:** `df.iterrows()` is a significant bottleneck in hydration loops because it boxes rows into Series objects. `_resolve` was O(columns) due to repeated `.replace()` calls on the full dictionary.
**Action:** Use `df.to_dict('records')` for faster iteration and `re.sub` for template resolution to achieve O(template_placeholders) instead of O(columns). Pre-compile regexes for high-frequency string operations.
