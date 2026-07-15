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
`KRAIL_API_BASE_URL` for server-side API calls. Browser workflow and project mutations use
`NEXT_PUBLIC_KRAIL_API_URL`; its web origin must be present in `RAIL_WEB_ORIGINS`.

## Workspace configuration

Managed projects live below `RAIL_MANAGED_WORKSPACE_ROOT`. Linked directories may be placed anywhere,
but their canonical paths must be below one of the path-separated `RAIL_LINKED_PROJECT_ROOTS`.

```bash
RAIL_LINKED_PROJECT_ROOTS=/Users/me/research:/Volumes/team/projects
```

Operational JSON stores default to `.rail/platform-projects.json` and
`.rail/platform-runs.json`. They never replace KRAIL project truth.

The Control Plane's managed-project form accepts identifiers and KRAIL init options, never a path.
The API derives `<RAIL_MANAGED_WORKSPACE_ROOT>/<slug>`, invokes the pinned KRAIL CLI without a shell,
creates a Git baseline, validates the canonical project, and rolls back its new directory on failure.

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
