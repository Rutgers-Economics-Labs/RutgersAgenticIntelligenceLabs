# RAIL Repo Audit And Setup Guide

This guide answers two practical questions:

1. What parts of the repository are durable and worth keeping?
2. What parts are local runtime exhaust, generated output, or candidates to shorten, archive, or delete?

It also gives a clean setup path for a fresh machine.

## Short answer

RAIL is not a small app repo. It is a monorepo plus a project workspace:

- `apps/web` is the operator UI
- `packages/api` is the FastAPI control plane
- `packages/rail-py` is the user-facing Python CLI
- `packages/engine` is the hydration / ontology engine
- `packages/mcp-server` is the MCP layer
- `generated_projects/` is a collection of repo-native project workspaces, many of which are nested git repos

The repo is useful, but it accumulates a lot of local state quickly. The biggest cleanup win is to separate:

- durable source code and docs
- durable project artifacts
- disposable runtime residue

## Keep, shorten, or delete

### Keep as core source of truth

These should stay and be reviewed carefully before changing:

- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/apps`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/packages`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/scripts`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/README.md`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/Makefile`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/docs/INSTALL.md`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/docs/DISTRIBUTION.md`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/AGENTS.md`

These are the platform’s real implementation and operator documentation.

### Keep, but treat as project-owned data

These are often large and noisy, but they are part of the product model:

- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/generated_projects`
- `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/docs/validation`

Important nuance:

- many directories under `generated_projects/` are nested git repos
- cleanup inside those projects should usually happen inside the nested repo, not the top-level repo

### Keep, but shorten over time

These are useful, but they can sprawl:

- `research_plan/decisions.md`
- `research_plan/task_board.md`
- `research_plan/current_plan.md`
- `research_plan/audits/`
- `research_plan/state/*candidates*.json`
- `research_plan/state/control_plane_snapshot.json`

Recommendations:

- move obsolete decisions into dated archive files
- keep only the current working plan in `current_plan.md`
- cap long audit directories with periodic summaries
- avoid committing ephemeral runner traces unless they are part of an intentional certification fixture

### Usually safe to delete locally

These are local runtime byproducts, not durable source:

- `*.pid`
- `backend.log`
- `frontend.log`
- `nextjs.log`
- `api_debug.log`
- `apps/web/.screenshots/`
- `.pytest_cache/`
- `__pycache__/`
- local cache folders used only for reruns

These should not be used as a source of truth.

### Usually safe to ignore, but be careful before deleting

- `uploaded_key`
  - this looks like a large local secret/materialized key artifact
  - it should stay untracked and should usually be removed or stored elsewhere, but only after confirming it is not still needed
- `.venv/`
  - safe to recreate, but expensive to rebuild
- `dist/`
  - safe to recreate if it is only local build output

### Do not bulk-delete blindly

Do not wipe these without checking whether they are intentionally tracked in a nested project:

- `generated_projects/**/.ontology`
- `generated_projects/**/research_plan/state`
- `generated_projects/**/artifacts`
- `generated_projects/**/topics`
- `generated_projects/**/scripts`
- `generated_projects/**/research_plan/tasks`

Inside project repos, these are often the actual deliverables.

## Safe cleanup policy

### Top-level repo

Safe default cleanup:

```bash
rm -f api.pid packages/api.pid web.pid web_restart.pid
rm -f backend.log frontend.log nextjs.log api_debug.log
rm -rf .pytest_cache __pycache__ apps/web/.screenshots
```

Use caution before removing:

```bash
rm -f uploaded_key
rm -rf dist cache logs
```

Only do that if you do not need those local artifacts anymore.

### Nested generated project repos

For a project repo under `generated_projects/<slug>`:

1. Run `git status` inside the nested repo.
2. Keep committed:
   - `research_plan/state`
   - `research_plan/tasks`
   - intentional `artifacts/`
   - intentional `scripts/`
   - intentional `topics/`
3. Usually discard or ignore:
   - session runtime directories
   - approval scratch files
   - transient dispatch logs
   - stale `.runner` traces

## Fresh setup

### Requirements

- Python 3.11+
- Node 18+
- git
- Convex URL and deploy key for cloud mode

Optional:

- FRED API key and any other provider keys used by project pipelines

### Install

```bash
git clone https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git
cd RutgersAgenticIntelligenceLabs
./scripts/install-rail.sh
cp .env.example .env
```

Edit `.env` and set at least:

```bash
CONVEX_URL=...
CONVEX_DEPLOY_KEY=...
FRED_API_KEY=...
```

### Start

```bash
make run
```

Services:

- UI: `http://localhost:3000`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

### Install optional agent CLIs

```bash
./scripts/install-agent-clis.sh
```

### Verify

```bash
rail --help
curl -s http://localhost:8000/health
```

## Working model

The best mental model for RAIL now is:

- the platform repo contains the engine and operator surfaces
- each generated project is closer to a self-contained research workspace
- repo-backed truth should win over stale runtime state
- Convex should be treated as coordination and cloud state, not the only durable truth

## Branching and merge guidance

### Safe

- commit and push scoped platform fixes on feature branches
- commit and push scoped project closeout changes inside the nested project repo
- merge when the target branch is close enough to fast-forward or produces a small, understandable conflict set

### Not safe to do blindly

Merging `feat/kill-switch-and-followups` into `future` is currently not a trivial merge. It has meaningful conflicts across:

- planner and goal-mode UI
- runner contracts and enforcement
- control-plane services
- project routers
- certification tests

That merge should be treated as a real integration task, not a housekeeping step.

## Recommended next cleanup pass

1. Remove top-level local runtime residue regularly.
2. Add a small script for local cleanup if this remains annoying.
3. Archive oversized project audit logs periodically.
4. Normalize nested project policies:
   - what to track
   - what to ignore
   - what to archive
5. Perform the `future` merge as a dedicated conflict-resolution branch with tests, not from a dirty working tree.
