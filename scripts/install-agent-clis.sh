#!/usr/bin/env bash
# Detect or install optional agent / coding CLIs used with RAIL workers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"

status() {
  if command -v "$1" >/dev/null 2>&1; then
    printf "  ✓ %-18s %s\n" "$1" "$(command -v "$1")"
  else
    printf "  · %-18s not installed\n" "$1"
  fi
}

echo "Agent / IDE CLI status ($OS)"
echo ""

status codex
status claude
status gemini
status cursor
status gh
status rail

echo ""
echo "Install hints (pick what you use):"
echo "  Codex CLI       npm i -g @openai/codex   — https://developers.openai.com/codex/cli"
echo "  Claude Code     curl -fsSL https://claude.ai/install.sh | bash"
echo "  Gemini CLI      npm i -g @google/gemini-cli"
echo "  GitHub CLI      https://cli.github.com/"
echo "  Cursor          https://cursor.com/download (desktop app; CLI optional)"
echo "  GitHub Copilot  ships inside VS Code / JetBrains / Cursor — no standalone CLI"
echo ""
echo "RAIL platform:   $ROOT/scripts/install-rail.sh"
echo ""

if [[ "$OS" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  read -r -p "Install gh via Homebrew if missing? [y/N] " ans || true
  if [[ "${ans:-}" =~ ^[Yy]$ ]]; then
    command -v gh >/dev/null || brew install gh
  fi
fi
