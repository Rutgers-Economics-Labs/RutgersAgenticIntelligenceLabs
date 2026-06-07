# RAIL

RAIL is an open-source platform for repo-native, agent-assisted research. It turns a Git repository into the system of record for research plans, data source definitions, ontology schemas, hydration pipelines, analysis artifacts, and integrity checks.

The project started at Rutgers Economics Labs, with an initial focus on economic and policy research. The core pattern is broader: keep research state in files, expose it through a CLI/API/MCP server, and give agents a structured workspace they can inspect, modify, verify, and hand back to humans.

## Why RAIL exists

Most data research workflows split across notebooks, dashboards, chat transcripts, local files, and undocumented API calls. That makes it hard to answer basic questions later:

- What data source produced this number?
- Which assumptions were active when the analysis ran?
- What changed between one research run and the next?
- Can an agent safely continue the work without inventing project context?

RAIL answers those questions by making the repository the contract.

## What you get

- **Repo-native research projects**: `rail.yaml`, plans, tasks, source notes, artifacts, and verification state live together.
- **Declarative data hydration**: YAML connector and pipeline definitions pull public data into project state.
- **Ontology-backed analysis**: project entities, series, sources, claims, and artifacts can be queried through structured APIs.
- **Agent-friendly surfaces**: a Python SDK, `rail` CLI, MCP server, and HTTP API expose the same project model.
- **Operator UI**: a Next.js command center for projects, runs, planner state, sources, ontology exploration, and artifacts.
- **Integrity layer**: assumptions, sources, empirical claims, rerun plans, and verification records are first-class project objects.

## Monorepo layout

```text
.
├── apps/web                 # Next.js command center UI
├── packages/api             # FastAPI control plane and project services
├── packages/engine          # Hydration, ontology, transform, and analysis engine
├── packages/rail-py         # Python SDK and rail CLI
├── packages/mcp-server      # MCP tools for agent clients
├── scripts                  # Install, release, seed, and maintenance scripts
├── docs                     # Installation, distribution, architecture, and design notes
├── examples                 # Small public sample projects
└── generated_projects       # Local generated workspaces, ignored by default
```

Large generated projects and validation runs are intentionally ignored in the public repository. Keep durable examples in `examples/`; keep local or private research workspaces in `generated_projects/` or `docs/validation/`.

## Requirements

| Tool | Version |
| --- | --- |
| Python | 3.11+ |
| Node.js | 18+ |
| git | any recent version |

Cloud mode also needs a Convex deployment URL and deploy key. Local mode can run against a project folder with `rail.yaml`.

Optional provider keys, such as `FRED_API_KEY`, are only needed for pipelines that call those services.

## Quick start

```bash
git clone https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git
cd RutgersAgenticIntelligenceLabs
./scripts/install-rail.sh
cp .env.example .env
```

Edit `.env` with your local settings. For cloud mode, set:

```bash
CONVEX_URL=https://your-deployment.convex.cloud
CONVEX_DEPLOY_KEY=your_deploy_key
```

Start the platform:

```bash
make run
```

| Service | URL |
| --- | --- |
| Command Center | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

Verify the CLI:

```bash
make install-rail
rail --help
curl -s http://localhost:8000/health
```

See [docs/INSTALL.md](docs/INSTALL.md) for fuller setup instructions.

## Local project mode

Use local mode when you want to work directly against a repo folder instead of a cloud control plane:

```bash
export RAIL_LOCAL=1
export RAIL_PATH=/path/to/project-with-rail-yaml
rail query classes
```

Python clients can do the same:

```python
import rail

project = rail.local("./examples/minimal-project")
print(project.slug)
```

## MCP for agents

RAIL can expose a project to MCP-compatible clients:

```bash
pip install -e packages/mcp-server
RAIL_LOCAL=1 RAIL_PATH=./examples/minimal-project rail-mcp
```

The MCP server gives agents tools for ontology inspection, SQL queries, data hydration, integrity checks, and safe project updates. See [AGENTS.md](AGENTS.md) for the full tool reference.

## Development

Install everything:

```bash
make setup
```

Run backend and frontend:

```bash
make run
```

Run focused tests:

```bash
python -m pytest packages/rail-py/tests packages/mcp-server/tests
python -m pytest packages/api/tests
cd apps/web && npm test
```

If a test requires cloud credentials, document that in the pull request and include the local tests you did run.

Frontend-only development:

```bash
cd apps/web
npm install
npm run dev
```

## Public data and secrets policy

Do not commit `.env`, deploy keys, private keys, local caches, generated ontology databases, or large research outputs. The repository includes `.env.example` for configuration shape only.

Before publishing a fork or release, run:

```bash
git status --short
git grep -n -I -E 'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_]{20,}|PRIVATE KEY' -- ':!apps/web/package-lock.json'
```

See [SECURITY.md](SECURITY.md) for vulnerability and secret-handling guidance.

## Distribution

Current release path:

```bash
curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
```

Release and packaging notes live in [RELEASE.md](RELEASE.md) and [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).

## Contributing

RAIL is early and still moving quickly. The best contributions are scoped fixes, docs that make the platform easier to run, small public examples, connector templates, and tests around project integrity behavior.

Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

RAIL is released under the [MIT License](LICENSE).
