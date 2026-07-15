# RAIL Agent Guide

RAIL is a platform around the published `krail` distribution. Preserve this boundary:

- KRAIL project files are canonical knowledge and workflow state.
- Only `packages/api/app/krail_runtime/**` may import the Python namespace `rail`.
- API routes call the typed runtime boundary; they do not parse or edit KRAIL files directly.
- RAIL persistence is limited to project registration, permission snapshots, run metadata, and
  event streams.
- Browser code calls versioned `/api/v1` contracts and never reads local project paths directly.

## Supported code

```text
apps/web/app/krail-*                 product workspaces
apps/web/components/krail-*          workspace components
apps/web/lib/krail/**                browser/server API boundaries
packages/api/app/krail_runtime/**    sole KRAIL adapter
packages/api/app/projects/**         workspace registry and path policy
packages/api/app/execution/**        operational execution control
packages/api/app/api/v1/**           versioned HTTP DTOs/routes
packages/api/app/main_krail.py       composition root
```

Do not restore the removed engine, SDK, MCP server, Convex services, planner/autopilot, or legacy
web routes. When KRAIL lacks a capability, return a typed unavailable state and record the gap
instead of creating a second implementation.

## Development

```bash
make install
make test
make build
```

Use `examples/krail-project` for deterministic integration tests. Keep full-access execution
disabled unless a test explicitly opts into it. Never commit `.env`, run stores, project registries,
worktrees, generated artifacts, or secrets.
