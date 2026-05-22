---
task_id: populate-ontology-pipeline-steps-for-attachable-sources
title: Populate ontology pipeline steps for attachable sources
status: cancelled
assigned_role: data
dependencies: []
acceptance_criteria:
- the default ontology pipeline declares concrete hydration steps for at least one
  attachable soccer source
- each step names a real source config and any required transform or parameterization
- pipeline notes distinguish immediately ingestable sources from manual-ingest-only
  sources
- the project is ready to rerun hydration against non-empty pipeline steps
related_files:
- .ontology/pipelines
- .ontology/sources
- .ontology/transforms
- research_plan
- topics
latest_run_summary: 'Superseded: the corresponding auditor is now `ready` so this
  repair task is no longer needed. Cancelled by archetype-closeout driver.'
runner: codex_cli
---

## Description

Populate ontology pipeline steps for attachable sources. This ontology-first project cannot be treated as complete until hydration succeeds, ontology health is verified, and downstream research is explicitly reopened from the hydrated ontology.
