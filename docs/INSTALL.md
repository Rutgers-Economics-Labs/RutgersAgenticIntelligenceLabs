# Local installation

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- [uv](https://docs.astral.sh/uv/)
- Git

## Install and run

```bash
make install
cp .env.example .env
make run
```

`make run` starts `app.main_krail:app` on port 8000 and Next.js on port 3000. The web server uses
`KRAIL_API_BASE_URL` for server-side API calls.

## Workspace configuration

Managed projects live below `RAIL_MANAGED_WORKSPACE_ROOT`. Linked directories may be placed anywhere,
but their canonical paths must be below one of the path-separated `RAIL_LINKED_PROJECT_ROOTS`.

```bash
RAIL_LINKED_PROJECT_ROOTS=/Users/me/research:/Volumes/team/projects
```

Operational JSON stores default to `.rail/platform-projects.json` and
`.rail/platform-runs.json`. They never replace KRAIL project truth.

## Execution configuration

Dry-run workflows use the restricted profile by default. To permit explicit non-dry runs:

```bash
RAIL_FULL_ACCESS_ENABLED=true
```

Only set this for trusted local projects. `RAIL_RUN_MAX_WORKERS` controls the bounded local worker
pool (1–32). Unsupported restricted sandbox hosts fail closed.

## Verification

```bash
make test
make build
```
