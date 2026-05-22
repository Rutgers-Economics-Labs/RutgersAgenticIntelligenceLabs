---
task_id: verify-hydrated-ontology-health-before-research
title: Verify hydrated ontology health before research
status: cancelled
assigned_role: health
dependencies:
- hydrate-project-ontology-and-register-active-artifacts
acceptance_criteria:
- project-scoped ontology endpoints return success for classes or graph queries
- core domain entity classes and/or hydrated tables are present and non-empty
- health notes record any remaining hydration or lineage risks
- the task remains blocked or needs_changes if ontology-backed research is still impossible
related_files:
- research_plan
- .ontology
- artifacts
latest_run_summary: 'Superseded: the corresponding auditor is now `ready` so this
  repair task is no longer needed. Cancelled by archetype-closeout driver.'
runner: codex_cli
---

## Description

Verify hydrated ontology health before research. This ontology-first project cannot be treated as complete until hydration succeeds, ontology health is verified, and downstream research is explicitly reopened from the hydrated ontology.
