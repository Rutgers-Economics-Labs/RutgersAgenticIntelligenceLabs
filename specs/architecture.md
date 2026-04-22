# Platform Architecture

This document is a lightweight transition note.

The active target architecture for RAIL now lives in:

- `specs/future-architecture.md`
- `specs/future-repo-contract.md`
- `specs/future-agents.md`
- `specs/future-runners.md`
- `specs/future-database.md`
- `specs/future-frontend.md`

## Active Direction

RAIL is moving toward a planner-first, Git-native research platform where:

- Git is the source of truth for project content
- `.ontology/` is the source of truth for hydration inputs
- `rail.yaml` defines the repo contract and runtime defaults
- the database stores lightweight operational metadata only
- one worker agent runs at a time in V1
- the planner is the only human-facing role
- worker runs execute through runner adapters such as Jules

## Core Packages Kept

```text
packages/
  engine/      Python hydration engine and ontology tooling
  api/         FastAPI orchestration and service layer
  rail-py/     Python client package and local project tooling
scripts/
  ...          bootstrap and migration helpers
```

## Removed Direction

The previous `packages/web/` Next.js application is no longer the active implementation target and has been removed as part of the greenfield UI reset.

## Notes

- use `specs/api.md` for the current FastAPI surface
- use `specs/engine.md` and `specs/ontology-kernel.md` for the hydration/kernel model
- use `specs/future-*.md` for product direction and rebuild planning
