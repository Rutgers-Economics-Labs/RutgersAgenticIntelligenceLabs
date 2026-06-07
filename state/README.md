# Platform State

This folder answers "where are we?" for RAIL. Treat this README as the current
high-level status; the older layer and feature ledgers are useful historical
snapshots, but they can lag the code during active platform work.

## Current Verdict

RAIL is a working operator-assisted research platform. It is not yet complete as
an unattended autonomous platform because the final claim still needs live,
repeatable proof across multiple fresh project archetypes.

| Area | Current status | Notes |
| --- | --- | --- |
| Engine and hydration | Working | Core API/CSV/Excel fetch, ontology build, transforms, DuckDB export, and hydration jobs exist. |
| Project UI | Working | The active app uses project-scoped pages under `apps/web/app/projects/[slug]/`. |
| GitHub sync | Partial | Publish, webhook sync, link, and status routes exist. Status now reports `unknown`, `in_sync`, or `diverged` instead of assuming success. |
| `rail-py` | Working | Local/cloud client, manifest validation, integrity, completion gate, and tests exist. |
| Autopilot | Partial | Local `local:*` autopilot ticks can complete from repo truth without Convex. Live cloud-backed runs still need backend availability. |
| Validation | Partial | `validate_local_project.py` and a fresh local autopilot tick pass for `docs/validation/fresh-goal-mode-completion`; the remaining bar is live multi-archetype validation. |
| State docs | Simplifying | Prefer this README plus validation results over maintaining several overlapping progress ledgers. |

## Completion Bar

Do not call the platform "complete" until a new project can move from brief to
closeout through the live autopilot path with:

- no mocked Convex/session layer
- no manual promotion of task, session, hydration, or integrity state
- no post-hoc provenance backfill
- GitHub status that can prove `in_sync` or honestly report `unknown`
- closeout auditors green from repo truth

## Next Build Queue

1. Exercise local autopilot on a fresh project that still has unfinished work,
   not only an already closeout-ready project.
2. Rerun a fresh validation project through live `autopilot_service` once Convex
   is available.
3. Remove or archive obsolete state claims from `layers.md`, `features.md`, and
   `gap.md` once the new validation result is captured.
4. Keep reducing duplicated "truth" surfaces into one project reality snapshot.

## Latest Fresh-Project Run

`docs/validation/fresh-goal-mode-completion` was created as a new
research-first project. Local validation passes with:

```bash
packages/api/.venv/bin/python packages/api/scripts/validate_local_project.py \
  --root docs/validation/fresh-goal-mode-completion
```

The project reaches `LOCAL_VALIDATION_READY=True`, including closeout. A bounded
local autopilot tick also completes without Convex:

```bash
RAIL_PROJECTS_DIR=docs/validation \
  packages/api/.venv/bin/python packages/api/scripts/run_autopilot_tick.py \
  --slug fresh-goal-mode-completion --iterations 1
```

The configured Convex deployment is still disabled by plan limits, so live
cloud-backed validation remains blocked until that backend is available.
