#!/usr/bin/env bash
# Build release artifacts under dist/release/ (called from CI or locally).
set -euo pipefail

VERSION="${1:?Usage: make-portable-bundle.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/dist/release"
STAGING="$OUT/staging-rail-$VERSION"

rm -rf "$OUT"
mkdir -p "$OUT"
rm -rf "$STAGING"
mkdir -p "$STAGING"

echo "→ Staging source tree (rail-$VERSION)"
# Keep the bundle small enough for GitHub Releases (≤2 GB/asset; target <100 MB).
tar -C "$ROOT" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.venv' \
  --exclude='**/.venv' \
  --exclude='**/.pytest_cache' \
  --exclude='cache' \
  --exclude='dist' \
  --exclude='apps/web/.next' \
  --exclude='apps/web/node_modules' \
  --exclude='apps/web/.screenshots' \
  --exclude='generated_projects' \
  --exclude='docs/validation' \
  --exclude='packages/engine/cache' \
  --exclude='**/__pycache__' \
  --exclude='**/*.duckdb' \
  --exclude='**/.ontology' \
  --exclude='**/*.log' \
  --exclude='api.pid' \
  -czf "$OUT/rail-${VERSION}-src.tar.gz" .

cp "$ROOT/scripts/install-rail.sh" "$OUT/install-rail.sh"
cp "$ROOT/scripts/install-agent-clis.sh" "$OUT/install-agent-clis.sh"
cp "$ROOT/scripts/release/install-from-release.sh" "$OUT/install.sh"

chmod +x "$OUT/install-rail.sh" "$OUT/install-agent-clis.sh" "$OUT/install.sh"

cat > "$OUT/README-release.txt" <<EOF
RAIL Platform $VERSION
======================

Quick install (macOS / Linux / WSL):
  curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/download/v${VERSION}/install.sh | bash

Or download install.sh from this release and run: bash install.sh

After install:
  cd RutgersAgenticIntelligenceLabs   # or your clone path
  cp .env.example .env && edit secrets
  make run

CLI only (Python 3.11+):
  pip install rail-${VERSION}-py3-none-any.whl   # if wheel attached

Agent CLIs (optional): bash install-agent-clis.sh
EOF

echo "→ Release artifacts in $OUT"
ls -la "$OUT"
