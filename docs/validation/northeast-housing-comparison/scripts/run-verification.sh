#!/usr/bin/env bash
set -euo pipefail

# Run deterministic checks for the current worker workspace.
python3 scripts/verify_project_state.py
