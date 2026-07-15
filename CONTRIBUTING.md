# Contributing

Contributions should strengthen the KRAIL-backed platform boundary rather than recreate runtime
features in RAIL.

1. Install with `make install`.
2. Keep changes within the API adapter/control plane or a focused web workspace.
3. Add contract tests for backend behavior and visually verify user-facing changes.
4. Run `make test` and `make build`.
5. Explain permission, migration, and capability changes in the pull request.

Do not commit secrets, `.rail` operational stores, private project directories, generated outputs,
databases, or agent worktrees. Public fixtures must remain small and deterministic.
