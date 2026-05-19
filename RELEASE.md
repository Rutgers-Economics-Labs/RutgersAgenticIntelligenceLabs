# Releasing RAIL on GitHub

## One-time setup (maintainers)

1. Merge `.github/workflows/release.yml` and `scripts/release/` to your default branch.
2. In GitHub → **Settings → Actions → General**, allow workflows to create releases.
3. Optional PyPI: add secret `PYPI_API_TOKEN` and variable `PUBLISH_PYPI=true`.

## Publish a release

**Option A — git tag (recommended)**

```bash
git tag v0.1.0
git push origin v0.1.0
```

**Option B — manual workflow**

GitHub → **Actions** → **Release** → **Run workflow** → enter version `0.1.0`.

## User install URL (after release exists)

```bash
curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
```

See [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md) for desktop binaries and Docker roadmap.
