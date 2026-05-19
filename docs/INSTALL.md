# Installing RAIL

RAIL is a monorepo: FastAPI backend, Next.js operator UI, Python engine, `rail` CLI, and optional MCP server.

## Quick start (end users — GitHub Release)

No clone required:

```bash
curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
```

Then `cd ~/rail-platform` (or the path printed by the installer), configure `.env`, and `make run`.

See [DISTRIBUTION.md](./DISTRIBUTION.md) for tagging releases and optional PyPI publishing.

## Quick start (developers)

**Requirements:** Python 3.11+, Node 18+, git. Convex URL for cloud mode (or local project folders).

```bash
git clone https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git
cd RutgersAgenticIntelligenceLabs
./scripts/install-rail.sh
cp .env.example .env   # if install did not create .env
# Edit .env: CONVEX_URL, CONVEX_DEPLOY_KEY, FRED_API_KEY, etc.
make run
```

Open **http://localhost:3000** — Mission Control for your project.

Equivalent to the script:

```bash
make setup
```

## One-button data pipeline (UI)

On **Overview** or **Ontology**, use **Fetch data & hydrate**. It:

1. Reconciles control-plane drift (tasks, sessions, integrity).
2. Queues the project hydration job (FRED/registry fetch → transforms → DuckDB ontology).

API: `POST /api/v1/projects/{slug}/pipeline/run?reconcile=true`

## Agent CLIs (optional)

Workers can call external agent tools when configured. RAIL does **not** redistribute proprietary installers.

```bash
./scripts/install-agent-clis.sh
```

| Tool | Install | Notes |
|------|---------|--------|
| Codex | `npm i -g @openai/codex` | OpenAI Codex CLI |
| Claude Code | [install script](https://docs.anthropic.com/en/docs/claude-code) | `claude` in PATH |
| Gemini CLI | `npm i -g @google/gemini-cli` | `gemini` in PATH |
| Cursor | [cursor.com/download](https://cursor.com/download) | Desktop IDE; agents run in-app |
| Copilot | VS Code / Cursor extension | No standalone CLI |
| `rail` | `pip install -e packages/cli` | Included in `install-rail.sh` |
| `rail-mcp` | `pip install -e packages/mcp-server` | MCP for Cursor / Claude Desktop |

## Local project mode (no Convex)

```bash
export RAIL_LOCAL=1
export RAIL_PATH=/path/to/project/with/rail.yaml
rail-mcp
```

See [AGENTS.md](../AGENTS.md) for MCP tool reference.

## Windows

- Use **WSL2** and run `install-rail.sh` inside Ubuntu, or
- Install Python + Node manually, then `make install` from PowerShell.

Native Windows installers are planned; see [DISTRIBUTION.md](./DISTRIBUTION.md).

## Troubleshooting

| Issue | Fix |
|-------|-----|
| API 404 on pipeline | Ensure API is on `future` branch with `POST .../pipeline/run` |
| Hydration stuck | Check `GET /api/v1/jobs/{jobId}` and API logs |
| Empty ontology | Run fetch & hydrate; confirm `FRED_API_KEY` in project secrets |
| Web cannot reach API | `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` in `apps/web/.env.local` |
