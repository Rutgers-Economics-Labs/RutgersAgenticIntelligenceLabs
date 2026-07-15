# KRAIL Migration Cleanup Manifest

Status: removal gates passed; legacy runtime removed on `krail`
Branch: `krail`
Architecture: `docs/KRAIL_MIGRATION_PLAN.md`

This manifest protects the KRAIL migration from two failure modes: deleting useful UI/platform code
before its replacement exists, and preserving duplicate runtime code after KRAIL owns the same
capability.

## Baseline recorded on 2026-07-15

The baseline was taken before deleting any runtime package:

| Check | Result | Interpretation |
| --- | --- | --- |
| `python -m pytest packages/rail-py/tests packages/mcp-server/tests -q` | 257 passed, 36 failed | Existing SDK/MCP integrity API drift; these packages are migration removals |
| `python -m pytest packages/api/tests -q --tb=no` | Interrupted after 204.59s with 206 passed, 1 failed | Existing failure in `test_reconcile_project_reality_returns_consolidated_summary`; suite contains slow integration tests |
| `npm run build` in `apps/web` | Not run successfully: `next` not found | Frontend dependencies are not installed in this checkout |
| `git diff --check` | Passed | Cleanup/plan patch has no whitespace errors |

These failures are pre-existing migration baseline results. A child task must not broaden its scope
to fix a legacy package scheduled for deletion unless that behavior is needed by the new KRAIL
adapter or visual platform.

## Keep and evolve

| Path | Disposition | Reason |
| --- | --- | --- |
| `apps/web` | Keep and redesign | Becomes the RAIL visual platform |
| `packages/api` | Keep package boundary; replace internals | Becomes the thin control-plane and KRAIL adapter API |
| `examples/krail-project` | Keep | Deterministic published-KRAIL contract fixture |
| `SECURITY.md` | Rewrite | Must describe linked paths, permission profiles, isolated workers, and secrets |
| `.github/workflows` | Rewrite | Must test the new two-package system and pinned KRAIL contract |
| `README.md`, `AGENTS.md`, `CONTRIBUTING.md` | Rewrite | Must describe RAIL-as-platform and KRAIL-as-runtime |
| `LICENSE` | Keep | Project license |

## Removed after replacement gates passed

| Removed path or subsystem | Verified replacement |
| --- | --- |
| `packages/engine` | Published KRAIL adapter and explicit capability states |
| `packages/rail-py` | Published KRAIL resolves as the sole `rail` import and M1 contract tests pass |
| `packages/mcp-server` | Documentation points agent clients to KRAIL's MCP server |
| Legacy API ontology/integrity/workflow services | Corresponding M3/M4 routes pass integration tests through `KrailRuntime` |
| Convex client and mirrored project state | Local project registry and run metadata store pass M2/M4 tests |
| Planner/autopilot swarm | KRAIL workflows and RAIL run service cover approved product behavior |
| Legacy runner adapters | Isolated KRAIL worker and permission profiles pass lifecycle/security tests |
| One-off repair/seed/monitor scripts | No supported install, fixture, or migration flow references them |
| Old specs, goals, state notes, and historical planning docs | Final architecture/API/UI docs contain any still-relevant contract |
| Windows/release convenience scripts | `uv`, npm, Make, Docker, and CI local-platform flow |

The legacy web `/projects/**` command center, its API/type client, old component closure, historical
specifications, goals/state notes, and stale release scripts were removed at the same gate. The
supported tree now builds successfully with `make build`, and its focused backend suite passes with
`make test`.

## Removed in the baseline cleanup

- `.claude/commands/**`;
- `.jules/**`;
- `claude-buddy.md`;
- `run_jules_agents.py`;
- tracked files under `generated_projects/rel-partner-sourcing/**`.

Ignored local project data was deliberately not deleted. In particular, the approximately 20 GB
working checkout contains ignored generated projects, caches, databases, and artifacts that may be
operator-owned.

## Removal rules

1. Delete code only in the integration task after its replacement gate passes.
2. Search imports, environment variables, Make targets, scripts, CI, docs, and frontend calls before
   removing a subsystem.
3. Do not delete or clean ignored operator data as part of source cleanup.
4. Do not keep compatibility wrappers that reimplement KRAIL behavior.
5. If KRAIL lacks a required capability, record a capability gap and address it upstream or adapt
   the product behavior; do not silently restore a second runtime.
6. Every removal commit must leave the supported fresh-install and verification paths working.
