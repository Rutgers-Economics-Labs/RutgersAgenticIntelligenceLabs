# NJ Labor Market Literature Review

Validation archetype: **document-heavy literature** (integrity + artifacts, no DuckDB ontology).

## Autopilot closeout

From `packages/api/`:

```bash
python scripts/run_archetype_autopilot.py \
  --root ../../docs/validation/document-heavy-literature \
  --iterations 10
```

Requires Convex registration, seeded `claims.json` / `sources.json`, and a final artifact under `artifacts/`. The ontology auditor should report `ready` with `state: not_applicable` (`project.mode: research_first`).
