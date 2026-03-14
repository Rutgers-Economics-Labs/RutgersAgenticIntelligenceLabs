# Architecture

RAIL is a YAML-driven ontology hydration engine. No domain knowledge exists in the Python engine — all field names, API endpoints, class mappings, and relationship wiring come from YAML configuration files.

> **Monorepo context.** This engine lives at `packages/engine/` in a larger monorepo. It is wrapped by a FastAPI service (`packages/api/`) and a Next.js frontend (`packages/web/`). See `specs/architecture.md` at the repo root for the full platform data flow.

## Directory Layout

```
packages/engine/
hydrate.py                        CLI entry point (standalone, bypasses FastAPI)
app.py                            Streamlit explorer (standalone, for local use)
engine/
  api_runner.py                   Fetch and normalize data from any source
  ontology_builder.py             Build or load OWL ontologies
  pipeline_runner.py              Orchestrate hydration steps
  pipeline_runner_cli.py          Thin CLI wrapper called by the FastAPI worker
  transform_runner.py             Load and run transform plugins
  analysis_runner.py              Discover and run analysis plugins
configs/
  ontology/core.yaml              Ontology schema (classes, properties)
  apis/*.yaml                     Data source definitions
  pipelines/*.yaml                Pipeline definitions
transforms/                       DataFrame and ontology transform plugins
analysis/                         Analysis plugins (auto-discovered)
sources/                          Local CSV and Excel data files
cache/                            HTTP response cache (git-ignored)
ontology/                         Generated outputs (git-ignored)
  onto.db                         SQLite quadstore (owlready2 backend)
  populated_ontology.owl          RDF/XML export
```

## Data Flow

```
python hydrate.py [--pipeline PATH]
        │
        ▼
pipeline_runner.run_pipeline(pipeline_path)
        │
        ├─ Delete stale onto.db and onto.db-journal
        ├─ World().set_backend(filename=db_path)
        ├─ load_ontology(pipeline["ontology"], world)
        │       └─ build_from_yaml or load_from_owl
        │
        └─ For each step (in order):
                ├─ api_runner.fetch_api(api_name, resolved_data)
                │       ├─ Load configs/apis/{api_name}.yaml
                │       ├─ Resolve ${VAR_NAME} env tokens
                │       ├─ Execute HTTP / CSV / Excel source
                │       ├─ foreach: one request per parent row
                │       └─ Apply field mapping → DataFrame
                │
                ├─ run_dataframe_transform(spec, df, config)  [optional]
                │
                ├─ resolved[api_name] = df
                │
                └─ For each row:
                        ├─ Resolve URI template (sanitized)
                        ├─ _get_or_create(onto, class, uri, cache)
                        ├─ Set data properties
                        └─ Resolve and set object property relationships

        └─ run_ontology_transform(spec, onto, config)  [post_hydration_transforms]

        └─ onto.save(format="rdfxml") + world.save()
```

## Generated Outputs

| File | Description |
|------|-------------|
| `ontology/onto.db` | SQLite quadstore; owlready2 backend; deleted and rebuilt on every `hydrate.py` run |
| `ontology/populated_ontology.owl` | RDF/XML export of the populated ontology |
| `cache/*.json` | Per-request HTTP response cache; keyed by API name + injected params |
| `graph.html` | 1-hop relationship graph for the selected entity (Streamlit Explorer tab only) |
| `graph_full.html` | Full filtered graph (Streamlit Graph Explorer tab only) |

## Key Design Decisions

**Fresh World() per run.** `pipeline_runner` creates `World()` rather than using owlready2's `default_world`. The default world is pre-populated by owlready2 imports and causes "Cannot save existent quadstore" if a DB file already exists.

**URI cache.** `_cache = {}` maps URI strings to owlready2 individuals inside `run_pipeline`. This avoids repeated `onto.search_one()` SQLite queries for the same individual during a single hydration run.

**Step ordering is load-bearing.** Each step's result is stored in `resolved[api_name]`. A `foreach` source must resolve to a key that was stored by an earlier step, or an error is raised.

**Environment variable substitution.** `${VAR_NAME}` tokens in any YAML string value are replaced with `os.environ.get(VAR_NAME)` at load time. Unresolved tokens are left as-is (e.g., `${FRED_API_KEY}` if the variable is not set).
