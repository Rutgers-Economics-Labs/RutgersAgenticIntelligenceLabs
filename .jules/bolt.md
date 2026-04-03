## 2025-05-14 - [Hydration Performance Optimization]
**Learning:** `df.iterrows()` is a significant bottleneck in hydration loops because it boxes rows into Series objects. `_resolve` was O(columns) due to repeated `.replace()` calls on the full dictionary.
**Action:** Use `df.to_dict('records')` for faster iteration and `re.sub` for template resolution to achieve O(template_placeholders) instead of O(columns). Pre-compile regexes for high-frequency string operations.

## 2025-05-15 - [DataFrame Iteration in API Runner]
**Learning:** `pd.DataFrame.apply(axis=1)` is ~4-6x slower than iterating over `df.to_dict('records')` because of Series boxing overhead. Calling `to_dict('records')` inside a loop over columns causes redundant $O(C \times R)$ conversions.
**Action:** Move `records = df.to_dict('records')` outside loops when processing multiple computed fields or transformations. Use `pd.Series(list_of_values, index=df.index)` to preserve the index when assigning the result back to the DataFrame.
