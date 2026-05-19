#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_PATH="${1:-$ROOT_DIR/docs/validation/ontology-first-public}"

echo "[smoke] project: $PROJECT_PATH"
if [[ ! -d "$PROJECT_PATH" ]]; then
  echo "[smoke] project directory not found: $PROJECT_PATH" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_PATH/rail.yaml" ]]; then
  echo "[smoke] rail.yaml missing in project path" >&2
  exit 1
fi

echo "[smoke] loading manifest"
python - <<'PY' "$PROJECT_PATH"
from pathlib import Path
import sys
from rail.manifest import load_manifest
root = Path(sys.argv[1]).resolve()
manifest = load_manifest(root)
print(f"[smoke] manifest project slug: {manifest.project.slug}")
print(f"[smoke] research_burst enabled={manifest.research_burst.enabled} max_parallel={manifest.research_burst.max_parallel}")
PY

echo "[smoke] verifying integrity files"
for rel in "research_plan/state/assumptions.json" "research_plan/state/sources.json" "research_plan/state/claims.json"; do
  if [[ ! -f "$PROJECT_PATH/$rel" ]]; then
    echo "[smoke] missing required file $rel" >&2
    exit 1
  fi
done

for rel in "research_plan/state/hypotheses.json" "research_plan/state/conflicts.json" "research_plan/state/claim_candidates.json"; do
  if [[ ! -f "$PROJECT_PATH/$rel" ]]; then
    echo "[smoke] initializing missing optional file $rel"
    mkdir -p "$(dirname "$PROJECT_PATH/$rel")"
    printf "[]\n" > "$PROJECT_PATH/$rel"
  fi
done

echo "[smoke] running verification script if present"
if [[ -x "$PROJECT_PATH/scripts/run-verification.sh" ]]; then
  (cd "$PROJECT_PATH" && ./scripts/run-verification.sh)
else
  echo "[smoke] no executable scripts/run-verification.sh, skipping"
fi

echo "[smoke] complete"
