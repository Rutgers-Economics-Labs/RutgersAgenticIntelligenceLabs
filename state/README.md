# Platform State

This folder tracks the current implementation state of the RAIL platform against its specifications. It is the canonical answer to "where are we?"

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Done — fully implemented and matches spec |
| 🟡 | Partial — exists but incomplete, diverges from spec, or needs changes |
| ❌ | Not started — spec exists, nothing built |
| 🔵 | Built but not yet specced — exists in the codebase, not in specs |

## Files

- [`layers.md`](layers.md) — State of each architectural layer (Engine, API, Convex, Frontend)
- [`features.md`](features.md) — State of each cross-cutting feature (GitHub sync, connectors, agents, etc.)
- [`gap.md`](gap.md) — Ordered build queue: what to implement next and why

## Quick Summary

The engine, core API, and basic frontend are production-ready for the original NJ economics use case. The new Data OS architecture (Projects, Connectors, GitHub sync, Ontology kernel, Scheduled pipelines, rail-py) is fully specced but not yet implemented. Several features exist in the codebase that are ahead of or different from the current spec.

| Layer | Spec coverage | Implementation |
|-------|--------------|----------------|
| Engine | ✅ Complete | ✅ Complete + extras |
| API | ✅ Complete | 🟡 ~75% — missing GitHub, connectors, schedules |
| Convex schema | ✅ Complete | 🟡 ~60% — missing connector/ontology templates, schedules |
| Frontend | ✅ Complete | 🟡 ~50% — flat nav, missing project-scoped layout |
| Ontology kernel | ✅ Complete | ❌ Not started |
| GitHub sync | ✅ Complete | ❌ Not started |
| rail-py | ✅ Complete | ❌ Not started |
| Scheduled pipelines | ✅ Complete | ❌ Not started |
