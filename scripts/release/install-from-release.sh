#!/usr/bin/env bash
# One-line installer for GitHub Releases.
# Usage:
#   curl -fsSL https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs/releases/latest/download/install.sh | bash
#   RAIL_VERSION=v0.2.0 bash install.sh
set -euo pipefail

REPO="${RAIL_REPO:-Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs}"
VERSION="${RAIL_VERSION:-}"
INSTALL_DIR="${RAIL_INSTALL_DIR:-$HOME/rail-platform}"

resolve_version() {
  if [[ -n "$VERSION" ]]; then
    echo "${VERSION#v}"
    return
  fi
  if command -v gh >/dev/null 2>&1; then
    gh release view --repo "$REPO" --json tagName -q .tagName 2>/dev/null | sed 's/^v//' && return
  fi
  curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'].lstrip('v'))"
}

VERSION_TAG="v$(resolve_version)"
BASE="https://github.com/$REPO/releases/download/$VERSION_TAG"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "RAIL installer — $REPO $VERSION_TAG → $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"
curl -fsSL "$BASE/rail-${VERSION_TAG#v}-src.tar.gz" -o "$TMP/src.tar.gz"
tar -xzf "$TMP/src.tar.gz" -C "$INSTALL_DIR" --strip-components=0 2>/dev/null || tar -xzf "$TMP/src.tar.gz" -C "$INSTALL_DIR"

# tarball root is repo root; find rail.yaml or Makefile
ROOT="$INSTALL_DIR"
if [[ ! -f "$ROOT/Makefile" ]]; then
  ROOT="$(find "$INSTALL_DIR" -maxdepth 2 -name Makefile -print -quit | xargs dirname 2>/dev/null || true)"
fi
if [[ -z "$ROOT" || ! -f "$ROOT/Makefile" ]]; then
  echo "Could not locate RAIL repo root under $INSTALL_DIR" >&2
  exit 1
fi

export RAIL_INSTALL_DIR="$ROOT"
bash "$ROOT/scripts/install-rail.sh"

echo ""
echo "Installed to: $ROOT"
echo "  cd $ROOT && cp .env.example .env && make run"
echo "  Web UI: http://localhost:3000"
