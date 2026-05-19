# Distributing RAIL (desktop & binaries)

Today RAIL is installed from source via `make setup` / `scripts/install-rail.sh`, or from **GitHub Releases** (recommended for end users).

## GitHub Releases (click / one-line install)

### Maintainers: ship a version

1. Bump versions in `packages/rail-py/pyproject.toml` and `packages/mcp-server/pyproject.toml` if needed.
2. Tag and push:

```bash
git tag v0.1.0
git push origin v0.1.0
```

3. The [Release workflow](../.github/workflows/release.yml) runs automatically and attaches:
   - `install.sh` — one-line installer script
   - `install-rail.sh` / `install-agent-clis.sh`
   - `rail-<version>-src.tar.gz` — portable source bundle
   - `rail-*.whl`, `rail_mcp-*.whl` — Python wheels

Optional PyPI upload: set repository variable `PUBLISH_PYPI=true` and secret `PYPI_API_TOKEN`.

### Users: install from latest release

**macOS / Linux / WSL:**

```bash
curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
```

Pin a version:

```bash
RAIL_VERSION=v0.1.0 curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/download/v0.1.0/install.sh | bash
```

**From the Releases page:** open [Releases](https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases), pick a version, download `install.sh`, run `bash install.sh`.

**CLI only (wheel):** download `rail-*.whl` from the release assets, then:

```bash
pip install rail-0.1.0-*.whl
pip install rail_mcp-0.1.0-*.whl   # optional MCP server
```

### What “click to install” means on GitHub

| User expectation | What we ship today | Next step |
|------------------|-------------------|-----------|
| Download `.dmg` / `.exe` on Releases | Not yet | Tauri desktop job in workflow |
| Run one command in terminal | `install.sh` | ✅ |
| `pip install rail` | Wheels on release; PyPI optional | Enable `PUBLISH_PYPI` |
| Docker “Run” button | Not yet | `docker-compose` + `ghcr.io` job |

Native desktop installers require a separate build matrix (macOS + Windows runners, code signing). The release workflow is structured so you can add those jobs later without changing the install script contract.

---

## Other channels

This document also covers **one-click installs** on macOS, Windows, and Linux without bundling third-party agent products you do not license.

## What we can ship

| Artifact | Contents | Platforms |
|----------|----------|-----------|
| **RAIL Desktop** (recommended) | Embedded API + web UI + local Convex/PGLite or remote Convex | macOS `.dmg`, Windows `.msi`/`.exe`, Linux `.AppImage` |
| **`rail` CLI wheel / binary** | Query, hydrate, integrity, MCP stdio | PyPI + PyInstaller one-file per OS |
| **Docker Compose** | API + web + optional engine | Any host with Docker |

## What we cannot ship in one EXE

- **Cursor, VS Code, Copilot** — proprietary IDEs/extensions; link to official downloads only.
- **Claude Code / Codex / Gemini** — install via vendor CLIs (`install-agent-clis.sh` documents commands).
- **API keys** — user supplies via project secrets vault.

## Recommended desktop stack: Tauri 2

1. **Shell:** Tauri wraps the Next.js static export or loads `localhost` sidecar.
2. **Sidecar:** PyInstaller-built `rail-api` binary started on app launch (or bundled Node + uvicorn).
3. **Updates:** Tauri updater channel per release.

Rough build pipeline:

```text
make web-build → out/
pyinstaller packages/api/entry.py → rail-api-{os}
tauri build → RAIL_{version}_{arch}.dmg / .msi / .deb
```

## Alternative: Electron

Heavier but familiar; same sidecar pattern. Use only if team already maintains Electron tooling.

## CLI-only distribution

For headless / agent machines:

```bash
pip install rail-platform   # future PyPI name
# or
curl -fsSL https://rail.example/install.sh | bash
```

Ship `rail-mcp` as console script entry point in the same package.

## Installer checklist (per release)

- [ ] Code-signed macOS app (Apple Developer ID)
- [ ] Windows Authenticode signing
- [ ] Linux GPG-signed `.deb` / AppImage
- [ ] Bundled default `rail.yaml` template project
- [ ] First-run wizard: Convex URL or local-only mode
- [ ] Link to `install-agent-clis.sh` from Settings in UI

## Makefile targets (planned)

```makefile
make dist-cli      # PyInstaller rail + rail-mcp
make dist-desktop  # Tauri release (requires platform SDKs)
```

Until those targets exist, use **Docker** or **install-rail.sh** for reproducible environments.
