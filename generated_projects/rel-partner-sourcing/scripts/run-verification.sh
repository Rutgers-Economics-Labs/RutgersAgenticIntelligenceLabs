#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_files=(
  "rail.yaml"
  "agents/config.yaml"
  "agents/research.yaml"
  "research_plan/current_plan.md"
  "research_plan/tasks/discover-net-new-organizations.md"
  "research_plan/tasks/verify-contact-route-and-draft-email.md"
  "artifacts/emails/first-contact-template.md"
  "topics/brief.md"
  "specs/research_question.yaml"
  "research_plan/state/assumptions.json"
  "research_plan/state/sources.json"
  "research_plan/state/claims.json"
)

for rel in "${required_files[@]}"; do
  if [[ ! -f "$ROOT_DIR/$rel" ]]; then
    echo "missing required file: $rel" >&2
    exit 1
  fi
done

if ! grep -qi "draft email" "$ROOT_DIR/research_plan/tasks/verify-contact-route-and-draft-email.md"; then
  echo "contact workflow task does not require a draft email" >&2
  exit 1
fi

if ! grep -qi "next step" "$ROOT_DIR/research_plan/tasks/verify-contact-route-and-draft-email.md"; then
  echo "contact workflow task does not require a next step" >&2
  exit 1
fi

if ! grep -qi "gpt-5.4" "$ROOT_DIR/agents/config.yaml"; then
  echo "agent config is not pinned to gpt-5.4" >&2
  exit 1
fi

if ! grep -qi "codex_cli" "$ROOT_DIR/rail.yaml"; then
  echo "project is not configured for codex_cli" >&2
  exit 1
fi

python - <<'PY' "$ROOT_DIR"
from pathlib import Path
import json
import sys

root = Path(sys.argv[1])
for rel in [
    "research_plan/state/assumptions.json",
    "research_plan/state/sources.json",
    "research_plan/state/claims.json",
]:
    path = root / rel
    with path.open() as fh:
        json.load(fh)
print("state json ok")
PY

echo "verification ok"
