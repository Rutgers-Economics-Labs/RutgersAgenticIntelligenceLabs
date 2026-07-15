# RAIL

RAIL is a local-first visual and operational control plane for
[KRAIL](https://pypi.org/project/krail/) projects. KRAIL project directories are the source of
truth for ontologies, documents, evidence, integrity records, workflows, and approvals. RAIL adds
project registration, Git/workspace policy, execution supervision, live events, and a web UI without
mirroring that knowledge into another database.

## What is included

- `packages/api`: a thin FastAPI boundary around the published `krail` package;
- `apps/web`: the Next.js visual platform;
- `examples/krail-project`: a deterministic fixture used by contracts and browser tests;
- `docs/KRAIL_MIGRATION_PLAN.md`: architecture, ownership rules, and implementation history.

The previous in-repository engine, Python SDK, MCP server, Convex mirror, planner swarm, and legacy
command center have been removed. Agent clients should use KRAIL's published CLI/Python/MCP
surfaces directly; RAIL is the operator-facing platform.

## Quick start

Requirements: Python 3.11+, Node.js 20+, `uv`, and Git.

```bash
make install
cp .env.example .env
make run
```

Open:

- web platform: <http://127.0.0.1:3000>
- API documentation: <http://127.0.0.1:8000/docs>

To register the included fixture, configure the repository's `examples` directory as an approved
linked root, then call the project API:

```bash
export RAIL_LINKED_PROJECT_ROOTS="$(pwd)/examples"
curl -X POST http://127.0.0.1:8000/api/v1/projects \
  -H 'content-type: application/json' \
  -d "{\"projectId\":\"fixture\",\"displayName\":\"KRAIL Fixture\",\"path\":\"$(pwd)/examples/krail-project\",\"workspaceMode\":\"linked_local\"}"
```

## Security defaults

- linked directories must be below an operator-approved root;
- dirty or non-Git linked projects are read-only;
- workflow launches default to dry-run;
- non-dry execution requires the `full-access` profile and `RAIL_FULL_ACCESS_ENABLED=true`;
- restricted commands fail closed unless an enforcing OS sandbox is available;
- RAIL run/project JSON stores contain operational metadata only.

See [INSTALL](docs/INSTALL.md), [SECURITY](SECURITY.md), and the
[migration plan](docs/KRAIL_MIGRATION_PLAN.md) for details.

## Verification

```bash
make test
make build
```

## License

MIT. See [LICENSE](LICENSE).
