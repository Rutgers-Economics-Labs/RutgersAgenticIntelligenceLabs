---
title: Reconcile control-plane drift and stale sessions
status: cancelled
assigned_role: health
runner: codex_cli
dependencies: []
acceptance_criteria:
  - stale runtime sessions are finalized or cancelled from durable session truth
  - duplicate task files, task/session mismatches, stale session audits, running-agent status drift, running-agent role drift, running-agent runner drift, secret policy role drift, and role config alias drift are reconciled
  - session and planner auditors no longer report control-plane blockers after the repair
related_files:
  - research_plan
  - research_plan/state
  - .ontology
latest_run_summary: "Superseded: the corresponding auditor is now `ready` so this repair task is no longer needed. Cancelled by archetype-closeout driver."
---

## Description

Repair persistent control-plane blockers such as stale runtime sessions, duplicate task files, task/session state mismatches, stale or missing post-run audits, non-canonical running-agent session statuses, non-canonical running-agent session roles, non-canonical running-agent session runners, non-canonical secret policy role mappings, or non-canonical role config aliases so autopilot can safely advance from audited truth.
