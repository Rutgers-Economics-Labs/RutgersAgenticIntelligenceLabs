# Local release checklist

## Source and dependency boundary

- [ ] Only `apps/web`, `packages/api`, and the deterministic KRAIL fixture remain as product code.
- [ ] `krail` resolves from PyPI and the adapter namespace-origin contract passes.
- [ ] No module outside `app/krail_runtime` imports `rail`.
- [ ] No HTTP route writes KRAIL project files directly.
- [ ] `uv lock --project packages/api --check` passes.
- [ ] `npm ci` succeeds from the committed lockfile.

## Verification

- [ ] `make test` passes.
- [ ] `make build` passes.
- [ ] A clean fixture can be registered through the project API.
- [ ] Explore/Evidence, Analyze, Workflows, and Control Plane render at desktop and 390px mobile.
- [ ] A fixture dry run reaches a durable terminal state and its SSE stream reconnects.
- [ ] Cancellation, read-only projects, disabled full access, path escape, and restricted sandbox tests fail closed.
- [ ] Restart reconciliation preserves the run audit trail.

## Security and operations

- [ ] `.env`, `.rail`, local projects, worktrees, run stores, databases, and screenshots are untracked.
- [ ] Full access is disabled by default and clearly marked in the UI.
- [ ] Linked roots and managed workspace root are explicit.
- [ ] No secret values appear in API/OpenAPI/browser contracts.
- [ ] The API binds to loopback in the supported local run command.
- [ ] Linux/hosted sandboxing is not claimed by the local release.

## Documentation

- [ ] README quick start works from a fresh clone.
- [ ] INSTALL variables match the composition root.
- [ ] SECURITY describes the actual local trust model.
- [ ] The migration plan and cleanup manifest match the shipped tree.
