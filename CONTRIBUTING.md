# Contributing to RAIL

Thanks for helping make RAIL more useful. The project is still early, so small, well-explained changes are especially valuable.

## Good first contributions

- Fix install or setup issues.
- Improve docs that were confusing during your first run.
- Add focused tests around `packages/rail-py`, `packages/mcp-server`, `packages/engine`, or `packages/api`.
- Add small connector templates for public datasets.
- Add compact example projects under `examples/`.
- Improve error messages, validation, or project integrity checks.

## Repository hygiene

RAIL produces a lot of local state. Please keep public commits focused on source code, docs, tests, and small examples.

Do not commit:

- `.env` files or provider keys
- private keys, deploy keys, API tokens, or webhook secrets
- generated ontology databases such as `*.duckdb`
- runtime sessions, audit traces, local runner directories, or cache folders
- large generated research outputs, PDFs, NDJSON dumps, or private project workspaces

Use `generated_projects/` and `docs/validation/` for local work. Use `examples/` for curated public fixtures.

## Development setup

```bash
./scripts/install-rail.sh
cp .env.example .env
make run
```

Frontend only:

```bash
cd apps/web
npm install
npm run dev
```

## Tests

Run the smallest relevant test set before opening a pull request:

```bash
python -m pytest packages/rail-py/tests packages/mcp-server/tests
python -m pytest packages/engine/tests
python -m pytest packages/api/tests
cd apps/web && npm test
```

If a test requires cloud credentials, document that in the pull request and include the local tests you did run.

## Pull request expectations

- Keep changes scoped.
- Explain the user-facing behavior change.
- Include tests for behavior changes when practical.
- Mention any migration or configuration changes.
- Avoid unrelated formatting churn.

## Public examples

Public examples should be small, reproducible, and based on public or synthetic data. Prefer a clear README plus tiny source files over large generated outputs.
