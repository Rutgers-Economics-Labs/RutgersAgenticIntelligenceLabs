# RutgersAgenticIntelligenceLabs

Ontology and AI-enhanced framework for economic analysis.

## Config-Driven Hydration (Phase 1 started)

The hydration engine now supports a YAML configuration format so data can be read from multiple source types and mapped into ontology individuals/properties.

Supported source types in the initial implementation:
- `csv`
- `api` (JSON response)
- `sql` (SQLite in the current implementation)
- `excel` (requires `openpyxl`)

### Run the engine

Use the legacy demo mode:

```bash
python hydration.py
```

Use config-driven mode:

```bash
python hydration.py --config configs/hydration.example.yaml
```

### Install dependencies

```bash
pip install owlready2 pyyaml openpyxl
```

### Config structure

Top-level keys:
- `version`
- `run`
- `connections`
- `sources`
- `mapping_sets`
- `output`
- `quality`

Each source includes:
- `id`, `type`, `enabled`
- `extract` block (connector-specific)
- `normalize` block (`select` and optional `casts`)
- `map_set` reference

Each mapping set includes:
- `target_class`
- `iri_template`
- `predicates`
- `required` fields

Output includes:
- `ontology_input`
- `ontology_output`
- `format`

### Example files

- `configs/hydration.example.yaml`: valid starter config
- `configs/hydration.invalid.yaml`: intentionally invalid config for validator checks

### Notes on normalization selectors

`normalize.select` supports:
- direct field names, e.g. `county`
- dotted paths, e.g. `results.county`
- array expansion path suffix `[]`, e.g. `data[]`
- indexed arrays, e.g. `footnotes[0].text`
- string literals wrapped in quotes, e.g. `'UnemploymentRate'`

### Environment variable substitution

Config values can reference env vars using:

```yaml
value: ${ENV:API_KEY_NAME}
```

The run will fail if a referenced environment variable is missing.
