---
task_id: populate-ontology-pipeline-steps-for-project-sources
title: Populate ontology pipeline steps for project sources
status: done
assigned_role: data
dependencies: []
acceptance_criteria:
- the default ontology pipeline declares concrete hydration steps for at least one
  project-relevant source
- each step names a real source config and any required transform or parameterization
- "at least one source actually fetches data (via api, url, or remote handler) rather\
  \ than registering a local metadata stub as its source \u2014 a source whose only\
  \ data is a single-row catalog CSV does not count"
- pipeline notes distinguish immediately ingestable sources from manual-ingest-only
  sources
- do not introduce unrelated cross-project harnesses, placeholder datasets, smoke-test
  fixtures, or out-of-domain fallback sources just to satisfy hydration
- the project is ready to rerun hydration against non-empty pipeline steps
related_files:
- .ontology/pipelines
- .ontology/sources
- .ontology/transforms
- research_plan
- topics
latest_run_summary: Completed by replacing placeholder source configs with concrete
  USAspending.gov and NSF Awards API steps plus the deterministic artifact builder.
runner: codex_cli
---

## Description

Populate ontology pipeline steps for project sources. This ontology-first project cannot be treated as complete until hydration succeeds, ontology health is verified, and downstream research is explicitly reopened from the hydrated ontology.
